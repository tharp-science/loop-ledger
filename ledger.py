#!/usr/bin/env python3
"""loop-ledger: validate and score a claims ledger produced by a research loop.

A ledger is a JSON Lines file, one claim per line. The scorer does not judge
whether claims are true. It checks whether each claim says what it rests on,
and whether disagreements were kept or collapsed.

    python ledger.py validate claims.jsonl
    python ledger.py score claims.jsonl [--archive path/to/eglab-buildday-dataset]
    python ledger.py schema

No dependencies beyond the standard library (Python 3.9+).
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import Counter

SCHEMA = {
    "id":            "string, unique within the ledger",
    "claim":         "string, the assertion in one sentence",
    "author":        "string, which loop or agent emitted it",
    "instrument":    "string, the measure the claim rests on (e.g. structural_k, operational_k); 'none' if the claim is not about a measured quantity",
    "run_set":       "object {n: int, filter: string} - how many runs and how they were selected",
    "attribution":   "list of engine-provenance classes the run set spans (e.g. match_head_class, match_other_commit, match_pre_git, untested, unmatched)",
    "mixed":         "bool, REQUIRED true when attribution has more than one class",
    "evidence":      "list of strings - files, columns, scripts, or claim ids the claim was derived from",
    "status":        "one of: asserted | contested | unresolved | null | withdrawn",
    "conflicts_with": "optional list of claim ids this claim disagrees with",
    "resolves":      "optional list of claim ids this claim claims to settle",
    "method":        "required when 'resolves' is present: test | vote | average | judgement",
    "criterion":     "required when method == test: the pre-stated test that decided it",
    "note":          "optional free text",
}

STATUSES = {"asserted", "contested", "unresolved", "null", "withdrawn"}
METHODS = {"test", "vote", "average", "judgement"}
KNOWN_ATTRIBUTION = {"match_head_class", "match_other_commit", "match_pre_git", "untested", "unmatched"}


def load(path: str) -> tuple[list[dict], list[str]]:
    claims, errors = [], []
    with open(path, encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                errors.append(f"line {lineno}: not JSON ({e.msg})")
                continue
            if not isinstance(obj, dict):
                errors.append(f"line {lineno}: not an object")
                continue
            obj["_line"] = lineno
            claims.append(obj)
    return claims, errors


def validate(claims: list[dict]) -> list[str]:
    """Structural errors only. A claim with errors is still scored, as failing."""
    errors: list[str] = []
    ids = Counter(c.get("id") for c in claims)
    for c in claims:
        tag = f"line {c['_line']} ({c.get('id', '?')})"
        for key in ("id", "claim", "author", "instrument", "run_set", "attribution", "evidence", "status"):
            if key not in c:
                errors.append(f"{tag}: missing '{key}'")
        if ids[c.get("id")] > 1:
            errors.append(f"{tag}: duplicate id")
        if c.get("status") not in STATUSES:
            errors.append(f"{tag}: status must be one of {sorted(STATUSES)}")
        rs = c.get("run_set")
        if not (isinstance(rs, dict) and isinstance(rs.get("n"), int) and isinstance(rs.get("filter"), str)):
            errors.append(f"{tag}: run_set must be {{n: int, filter: str}}")
        attr = c.get("attribution")
        if not (isinstance(attr, list) and attr and all(isinstance(a, str) for a in attr)):
            errors.append(f"{tag}: attribution must be a non-empty list of strings")
        elif len(set(attr)) > 1 and c.get("mixed") is not True:
            errors.append(f"{tag}: attribution spans {len(set(attr))} classes but 'mixed' is not true")
        ev = c.get("evidence")
        if not (isinstance(ev, list) and ev):
            errors.append(f"{tag}: evidence must be a non-empty list")
        if "resolves" in c:
            if c.get("method") not in METHODS:
                errors.append(f"{tag}: 'resolves' present but method not one of {sorted(METHODS)}")
            if c.get("method") == "test" and not c.get("criterion"):
                errors.append(f"{tag}: method is 'test' but no 'criterion' stated")
        for ref_key in ("conflicts_with", "resolves"):
            for ref in c.get(ref_key, []) or []:
                if ref not in ids:
                    errors.append(f"{tag}: {ref_key} refers to unknown claim '{ref}'")
    return errors


def provenanced(c: dict) -> bool:
    rs = c.get("run_set") or {}
    attr = c.get("attribution") or []
    return (
        isinstance(c.get("instrument"), str) and c["instrument"] != ""
        and isinstance(rs.get("n"), int) and bool(rs.get("filter"))
        and bool(attr) and (len(set(attr)) == 1 or c.get("mixed") is True)
        and bool(c.get("evidence"))
    )


def score(claims: list[dict], archive: str | None = None) -> dict:
    by_id = {c.get("id"): c for c in claims}
    live = [c for c in claims if c.get("status") != "withdrawn"]

    n_prov = sum(provenanced(c) for c in live)
    mixed_unmarked = [c["id"] for c in live if len(set(c.get("attribution") or [])) > 1 and c.get("mixed") is not True]
    nulls = [c["id"] for c in live if c.get("status") == "null"]
    unresolved = [c["id"] for c in live if c.get("status") == "unresolved"]

    # Conflicts: an unordered pair linked by conflicts_with on either side.
    pairs = set()
    for c in live:
        for other in c.get("conflicts_with", []) or []:
            if other in by_id:
                pairs.add(tuple(sorted((c["id"], other))))
    preserved, collapsed = [], []
    for a, b in pairs:
        ca, cb = by_id[a], by_id[b]
        both_stand = ca.get("status") != "withdrawn" and cb.get("status") != "withdrawn"
        # A pair is collapsed if some claim resolves one side by vote/average/judgement.
        collapsed_by = [
            r["id"] for r in live
            if any(x in (a, b) for x in (r.get("resolves") or [])) and r.get("method") in {"vote", "average", "judgement"}
        ]
        if both_stand and not collapsed_by:
            preserved.append((a, b))
        else:
            collapsed.append((a, b, collapsed_by))

    resolutions = [c for c in live if c.get("resolves")]
    by_test = [c["id"] for c in resolutions if c.get("method") == "test" and c.get("criterion")]
    by_fiat = [c["id"] for c in resolutions if c.get("method") in {"vote", "average", "judgement"}]

    # Instrument declaration on the archive's known contested quantity.
    instruments = Counter(c.get("instrument") for c in live)

    report = {
        "claims_total": len(claims),
        "claims_live": len(live),
        "claims_withdrawn": len(claims) - len(live),
        "fully_provenanced": n_prov,
        "provenance_rate": round(n_prov / len(live), 3) if live else None,
        "mixed_attribution_unmarked": mixed_unmarked,
        "null_results_recorded": len(nulls),
        "unresolved_kept": len(unresolved),
        "conflicts_declared": len(pairs),
        "conflicts_preserved": len(preserved),
        "conflicts_collapsed": [{"pair": [a, b], "by": by} for a, b, by in collapsed],
        "resolutions_by_test": by_test,
        "resolutions_by_fiat": by_fiat,
        "instruments_used": dict(instruments),
    }
    if archive:
        report["archive_checks"] = archive_checks(live, archive)
    return report


def archive_checks(live: list[dict], archive: str) -> dict:
    """Light consistency checks against the eglab build-day dataset, if present."""
    out: dict = {}
    runs_path = os.path.join(archive, "tables", "runs.csv")
    if not os.path.exists(runs_path):
        return {"error": f"{runs_path} not found"}
    with open(runs_path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    total = len(rows)
    attr_counts = Counter(r.get("attribution") for r in rows)
    out["archive_runs"] = total
    out["archive_attribution"] = dict(attr_counts)
    bad_n = [c["id"] for c in live if isinstance((c.get("run_set") or {}).get("n"), int) and c["run_set"]["n"] > total]
    unknown_attr = {c["id"]: sorted(set(c.get("attribution") or []) - set(attr_counts)) for c in live}
    unknown_attr = {k: v for k, v in unknown_attr.items() if v}
    out["run_set_larger_than_archive"] = bad_n
    out["attribution_classes_not_in_archive"] = unknown_attr
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate", help="check structure; exit 1 on any error")
    v.add_argument("ledger")
    s = sub.add_parser("score", help="print the score report as JSON")
    s.add_argument("ledger")
    s.add_argument("--archive", help="path to an extracted eglab-buildday-dataset, for consistency checks")
    sub.add_parser("schema", help="print the field reference")
    args = ap.parse_args(argv)

    if args.cmd == "schema":
        width = max(len(k) for k in SCHEMA)
        for k, desc in SCHEMA.items():
            print(f"{k.ljust(width)}  {desc}")
        return 0

    claims, errors = load(args.ledger)
    errors += validate(claims)
    if args.cmd == "validate":
        if errors:
            print("\n".join(errors))
            print(f"\n{len(errors)} error(s) in {len(claims)} claim(s)")
            return 1
        print(f"ok: {len(claims)} claim(s), no structural errors")
        return 0

    report = score(claims, args.archive)
    report["structural_errors"] = errors
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
