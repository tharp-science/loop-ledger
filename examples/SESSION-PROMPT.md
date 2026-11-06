# SESSION-PROMPT — eglab disagreement loop

Standing instruction for one iteration. Start a session with:

    /loop read @SESSION-PROMPT.md and follow the instructions in it

or set the goal once and let it run:

    /goal ledger.py validate passes on claims.jsonl; ledger.py score shows conflicts_preserved >= 1 and resolutions_by_fiat empty; the artefact claim is in the ledger with status asserted; JOURNAL.md records every run and every exchange

## The problem

How do independent research agents surface conflicting assumptions without a central
reconciler, keeping the disagreement and the provenance rather than collapsing them?

The data: `eglab-buildday-dataset/` (705 simulation runs; README section 1 lists three
kinds of disagreement already in it). Load with `from load import load; d = load()`.
Criteria for a passing result: issue #1 on the dataset repo. They say what counts, not
what you will find.

## Files that hold state

- `TASKS.md` — the live queue, one task per line, blockers first.
- `JOURNAL.md` — chronological: every run, every result, every surprise, every exchange with a human.
- `claims.jsonl` — the ledger. Every claim the loop makes goes here, in the loop-ledger format
  (`python ledger.py schema`). Nothing goes into a report that isn't in the ledger first.
- `SESSION-PROMPT.md` — this file. Update it if the method changes, with a dated note.

## One iteration

1. Read `TASKS.md`. Take the first unblocked task.
2. Run each atomic step in its own subagent. A subagent that answers a question about the data
   must state: instrument, run set (n and filter), attribution classes spanned, evidence
   (files and columns). If it can't, the answer is not a claim yet.
3. Append the result to `claims.jsonl`. If it disagrees with an existing claim, set both to
   `contested` and link them with `conflicts_with`. Do not pick one. If the evidence doesn't
   decide it, `unresolved`. If you looked and found nothing, `null`.
4. Run `python ledger.py validate claims.jsonl`. Fix structural errors before anything else.
5. Run `python ledger.py score claims.jsonl --archive eglab-buildday-dataset`. Paste the
   report into `JOURNAL.md` with the time.
6. Update `TASKS.md`. Commit.

## Rules

- A conflict may be resolved only with `method: test` and a `criterion` written **before** the
  test runs. Vote, average and judgement are allowed in the ledger and will be scored as
  collapse.
- The artefact-detection task is blind. The subagent working on it gets `tables/metrics.csv`
  and nothing else: no README, no `example.py`, no hint from a human. Record in `JOURNAL.md`
  exactly what it was given.
- Mixed attribution is not an error. Unmarked mixed attribution is.
- Don't impute. The 4 aborted runs, 5 `untested` and 1 `unmatched` stay as they are.

## First tasks (seed for TASKS.md)

- [ ] Load the archive; confirm 705 runs, 701 completed. Journal the counts.
- [ ] Agent A: answer "does eligibility_overlap drive single-centre collapse?" using `structural_k` only. Claim with provenance.
- [ ] Agent B: same question, `operational_k` only. Claim with provenance. Link A and B if they disagree.
- [ ] Agent C (blind): given `tables/metrics.csv` only — are any labelled columns a function of another column? Claim or null.
- [ ] Agent D: for configurations with >=3 completed runs landing in >1 basin, is the split explained by anything in config or scalar metrics? One claim per configuration examined; `unresolved` where it isn't.
- [ ] Score. Journal. Decide the next task from what the score says is weakest.
