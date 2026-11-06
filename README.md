# loop-ledger

A file format and a scorer for claims produced by a research loop. It does not judge
whether a claim is true. It checks whether each claim says what it rests on, and whether
disagreements between claims were kept or collapsed.

One file, no dependencies: `ledger.py`, Python 3.9+.

```
python ledger.py schema                      # the fields
python ledger.py validate claims.jsonl       # structure; exit 1 on any error
python ledger.py score claims.jsonl          # the report, as JSON
python ledger.py score claims.jsonl --archive path/to/eglab-buildday-dataset
```

## Why

A loop that can only record findings will manufacture them. A loop that resolves every
disagreement by voting or averaging will produce confident agreement where the evidence
holds two answers. This ledger makes both failure modes visible as numbers, so a build-day
team can say what their loop did without anyone having to adjudicate what it found.

Four things a claim has to carry, taken from the eglab build-day criteria:

1. **Instrument.** Which measure the claim rests on. Two instruments can disagree about the
   same quantity; a claim that doesn't name its instrument can't be compared with one that does.
2. **Run set.** How many runs and how they were selected.
3. **Attribution.** Which engine-provenance classes the run set spans. A claim resting on runs
   with mixed provenance must say so (`"mixed": true`).
4. **Evidence.** Files, columns, scripts or other claims it was derived from.

And three things the ledger is allowed to hold that most loops throw away:

- a **conflict** between two claims, both of which stand (`status: contested`, linked by `conflicts_with`);
- an **unresolved** case, kept open with the evidence examined (`status: unresolved`);
- a **null** result (`status: null`): the loop looked and found nothing.

A claim may resolve a conflict, but only by saying how. `method: test` with a stated
`criterion` counts as a resolution. `vote`, `average` and `judgement` are recorded, and
scored as the conflict having been collapsed.

## The format

JSON Lines, one claim per line. Lines starting with `#` are ignored.

| field | required | meaning |
|---|---|---|
| `id` | yes | unique within the ledger |
| `claim` | yes | the assertion, one sentence |
| `author` | yes | which loop or agent emitted it |
| `instrument` | yes | the measure it rests on; `none` if not about a measured quantity |
| `run_set` | yes | `{"n": int, "filter": "how the runs were selected"}` |
| `attribution` | yes | list of provenance classes the run set spans |
| `mixed` | when attribution has >1 class | must be `true` |
| `evidence` | yes | list: files, columns, scripts, claim ids |
| `status` | yes | `asserted` · `contested` · `unresolved` · `null` · `withdrawn` |
| `conflicts_with` | optional | claim ids this one disagrees with |
| `resolves` | optional | claim ids this one claims to settle |
| `method` | with `resolves` | `test` · `vote` · `average` · `judgement` |
| `criterion` | with `method: test` | the pre-stated test that decided it |
| `note` | optional | free text |

## The score

`score` prints one JSON object:

| key | what it counts |
|---|---|
| `fully_provenanced`, `provenance_rate` | claims carrying instrument, run set, attribution (marked if mixed) and evidence |
| `mixed_attribution_unmarked` | claims spanning several provenance classes without `mixed: true` — a silent provenance claim |
| `null_results_recorded` | claims with `status: null` |
| `unresolved_kept` | claims with `status: unresolved` |
| `conflicts_declared` / `conflicts_preserved` | pairs linked by `conflicts_with`; preserved if both sides stand and nothing resolved them by fiat |
| `conflicts_collapsed` | pairs where a claim resolved one side by vote, average or judgement, with the resolver's id |
| `resolutions_by_test` / `resolutions_by_fiat` | resolving claims, by method |
| `instruments_used` | which instruments the ledger's claims rest on |
| `archive_checks` | with `--archive`: run-set sizes and attribution classes checked against the dataset's `runs.csv` |

Nothing in the score says a claim is correct. A ledger can score perfectly and be wrong
about everything. That is deliberate: the score measures whether the loop's output can be
checked, not whether it has been.

## Worked example

`examples/eglab-overlap.jsonl` is a seven-claim ledger against the
[eglab build-day dataset](https://github.com/tharp-science/eglab-buildday-dataset): two loops
answer the same question with different instruments, a third keeps a replicate split open, a
fourth records a null, a fifth averages the two instruments into a single answer, and one
claim fails provenance.

```
$ python ledger.py validate examples/eglab-overlap.jsonl
line 11 (E1): attribution spans 2 classes but 'mixed' is not true

$ python ledger.py score examples/eglab-overlap.jsonl
  "fully_provenanced": 6,  "provenance_rate": 0.857,
  "mixed_attribution_unmarked": ["E1"],
  "null_results_recorded": 1,  "unresolved_kept": 1,
  "conflicts_declared": 1,  "conflicts_preserved": 0,
  "conflicts_collapsed": [{"pair": ["A1", "B1"], "by": ["D1"]}],
  "resolutions_by_fiat": ["D1"],
```

Remove D1 and the conflict is preserved. Replace D1's `method` with `test` and a `criterion`
and it is a resolution the ledger accepts. That difference is the whole point.

## Relation to CML

This is the smallest thing that does what the
[Context Mediation Layer](https://github.com/tharp-science/context-mediation-layer) does:
keep claims, their provenance and their disagreements on record, and refuse to collapse them
without a stated test. CML does it for people and agents over time, with intents, roles and
supersession history. This does it for one loop, in one file, in one day. If the ledger is
useful, that is the next step.

## Licence

MIT. THARP — Thyke Applied Research & Prototyping, https://tharp.science.
