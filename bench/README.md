# fold bench

Six scenarios whose tool output is large *by nature of the task*, one per condensation rule, each with a
deterministic generator (`setup.py`), turn prompts (`prompts.json`), an exact verifier (`verify.py`) and an
oracle (`oracle.py`) that writes the correct answer so the verifier itself can be checked
(`python3 bench/selfcheck.py`). Follow-up turns ask for facts that the condensed views must still support.

| scenario | shape | rule exercised |
|---|---|---|
| f1_log_triage | 6 service logs, ~670K chars, one root-cause chain and a red herring; per-code counts, first-seen timestamps, the WARN lines before the first error | logs: error-first with context |
| f2_api_reconcile | paginated JSON CLI, 20 pages × 100 orders + refunds; exact set of failed high-value unrefunded orders | JSON: items, error items pinned |
| f3_test_suite_fix | 400 tests, 5 planted bugs, every verbose run prints hundreds of lines; fix to green, then list the initially failing tests | logs/test output |
| f4_grep_rename | one identifier used ~350× across ~80 files with look-alike decoys; exact rename, suite green, original counts | search: per-file quota |
| f5_diff_review | a ~1500-line branch diff: signature changes, deleted file, TODOs, config keys, biggest file | unified diffs |
| f6_csv_reconcile | two 8K-row inventory exports that disagree on ~280 SKUs; per-category totals, mismatch list, worst SKU | data: head/tail, long rows |

Run a pair with the runner in `dsh-slice-agent-loop`:

```bash
SCEN_ROOT=~/code/dsh-tool-result-fold/bench/scenarios results/batch-scripts/arm.sh <ledger-dir> f1_log_triage transcript --effort low --tools full
SCEN_ROOT=~/code/dsh-tool-result-fold/bench/scenarios results/batch-scripts/arm.sh <ledger-dir> f1_log_triage transcript-fold --effort low --tools full
```
