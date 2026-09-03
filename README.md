# dsh-tool-result-fold

In-turn folding of tool results for the [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) **stock agent loop**. A standalone plugin: no custom loop, no session tape. Mount it next to the default `AgentLoop` and large tool results enter the model's context condensed, while the durable session log keeps every byte.

## Why

Under a prefix-cached pricing model (DeepSeek: a cache hit costs 1/30 of a miss) an append-only transcript is already the cheapest context for short sessions. What still grows the bill is every large tool result being paid once at miss price and then carried at hit price on every later step. Condensing results **as they enter** removes those bytes without ever rewriting the prefix.

## How it works

- On every `agent/pre-step` the plugin looks at the tool results that landed since the previous step and condenses them by content type — the routing borrowed from [Headroom](https://github.com/chopratejas/headroom):
  - **code** (by path or shape) and **search** (grep/glob) results are never touched;
  - **logs / build / test output** keep every error, failure and warning line with surrounding context, stack traces and summary lines, similar lines de-duplicated;
  - **documents / data** keep the first and last lines and every structured line (`key = value`, `key: value`, headings, section markers), with same-shaped appendix blocks kept only up to a cap; single lines longer than 1500 characters are cut to head and tail;
  - **JSON** results (arrays, objects with a large array field, JSONL) are condensed by item: the first 30% and last 15% of 15 kept items, error-looking items pinned, identical items de-duplicated, and a marker naming the omitted count and the fields;
  - **grep/glob** output above 120 matches or 10K chars keeps at most 5 matches per file (first and last always), 60 in total;
  - **unified diffs** of 50+ lines keep headers and changes with 2 context lines, at most 10 hunks per file;
  - small results (data below 6000 chars, logs below 512), and results that would not shrink by at least 45%, are left alone.
- The condensed view shadows the original through a `tool/result` **surface replacement** event that cites the shadowed node — the same mechanism the harness's own compaction pruner uses, and one the session invariant explicitly allows. The original stays in the durable log, the model's context stays append-only, and the loop's request-reconstruction invariant (`request == session.deriveMessages()`) keeps holding.
- The view's first line names the way back: `expand_result({"turn": t, "step": s, "call": n})` returns the full result verbatim.
- A `<fold>` section in the system prompt tells the model what it is looking at and that a whole-file read costs no more context than its condensed view.

### Safeguards learned the hard way

- **Pinned early steps** (`pinSteps`, default 2): results landing in the first steps of a turn are never condensed — a task's rules and spec are almost always read first. Folding a 3.7K rules file once cut its nine rules and every write went to the wrong directory (0/45 vs 45/45 for the plain loop); with the threshold at 6000 chars and the first steps pinned the same run passes 45/45 at a tenth of the cost.
- **Expansion back-off** (`backoffAfterExpansions`, default 2): if the model calls `expand_result` on a tool's condensed results twice and the expansion rate is at least a half, that tool's results are no longer condensed in this session. On a task that needs the middle of every blob the model expanded all 64 folds and the run cost more than the plain loop.

Two routes that do **not** work, for the record: appending the replacement from a `session/event` listener (the session forbids re-entrant appends), and replacing content in `tools/post-execute` (the durable log would then only hold the condensed text).

## Install

```bash
dsh plugin add github:TT-Wang/dsh-tool-result-fold
```

or, in code:

```ts
import ToolResultFold from '@dsh-external/dsh-tool-result-fold'

await ctx.plugin(ToolResultFold, {
  digest: { minChars: 1500, headLines: 10, tailLines: 4, maxLineChars: 1500 },   // all optional
})
```

Do not mount it together with a loop that already folds (such as `dsh-slice-agent-loop`); it is meant for the stock loop.

### Config

| key | default | meaning |
|---|---|---|
| `enabled` | `true` | `false` registers only `expand_result` |
| `pinSteps` | 2 | results landing in the first N steps of a turn are not condensed (unless larger than `pinMaxChars`) |
| `pinMaxChars` | 8000 | a result this large is condensed even in a pinned step (rules/spec files are a few K; a fetched page or a test run is not one) |
| `backoffAfterExpansions` | 2 | stop condensing a tool's results after this many `expand_result` calls on them (with expansion rate ≥ ½) |
| `digest.minChars` | 6000 | data results below this are never condensed |
| `digest.headLines` / `tailLines` | 10 / 4 | lines kept at both ends of a data result |
| `digest.maxKeepRatio` | 0.55 | give up when the view would keep more than this share of the original |
| `digest.structuredBlockCap` / `structuredBlockMin` | 12 / 3 | structured lines kept per block outside the head |
| `digest.logMinChars` / `logMaxErrors` / `logContextLines` | 512 / 10 / 3 | log rules |
| `digest.maxLineChars` / `lineHeadChars` / `lineTailChars` | 1500 / 700 / 300 | over-long single lines in data results |
| `digest.jsonMinItems` / `jsonKeepItems` | 5 / 15 | JSON arrays: minimum size to condense, items kept |
| `digest.searchMinMatches` / `searchMinChars` / `searchMaxPerFile` / `searchMaxTotal` | 120 / 10000 / 5 / 60 | grep/glob caps |
| `digest.diffMinLines` / `diffContextLines` / `diffMaxHunksPerFile` | 50 / 2 / 10 | unified diffs |

## Results

Same-day A/B on deepseek-v4-flash: the stock loop alone against the stock loop with this plugin, same code, same
runner, same conditions, exact verifiers. 21 scenarios, 47 runs. Costs in USD at DeepSeek's off-peak list price
(miss $0.22/M, cache hit $0.007/M, output $0.66/M); single runs move by about ±30%, so only the large differences
mean anything.

**Where it pays: results the agent has to take whole**

| scenario | shape | stock loop | + fold | condensed | verdict |
|---|---|---|---|---|---|
| l1 chained migration | 46 `read`s of 18K-char node files, fields on top, long dossier below | $0.135 | **$0.023** (−83%) | 46 results, 817K → 54K chars; peak context 331K → 43K tokens | 45/45 both |
| l2 ledger state | 45 `read`s of records + a 3.7K rules file | $0.216 | **$0.024** (−89%) | 45 results, 826K → 59K | 45/45 both (the first run scored 0/45 — see cons) |
| f9 documentation research | 9 pages taken whole through `fetch_page`, facts in tables, lists and prose | $0.0080 | $0.0068 (−15%) | 7 pages, 80K → 32K; the model expanded 3 of them | 8/8 answers both |

**Where it is neutral: long memory sessions (little to condense)**

| scenario | stock loop | + fold | notes |
|---|---|---|---|
| s10 compaction-loss probes, 76 turns | $0.509 | $0.538 / $0.411 | first run: every one of 64 condensed reads was expanded (the task needs the middle of each blob); second run: nothing condensed |
| s13 / s14b / s15b / s15c memory ladders | $0.017 / $0.020 / $0.023 / $0.050 | $0.020 / $0.030 / $0.022 / $0.052 | 0–9 condensations; all probes hold in both arms |
| n1 / n2 / n3 | $0.016 / $0.015 / $0.021 | $0.018 / $0.016 / $0.021 | nothing condensed |

**Where it is neutral: compute-style tasks (the agent filters its own output)**

| scenario | stock loop | + fold | condensed |
|---|---|---|---|
| s2 ten-turn coding loop | $0.071 | $0.087 | 0 — code and grep are never condensed |
| f1 log triage (670K chars of logs) | $0.0070 | $0.0065 | 0 — the agent used `grep`, never read the logs |
| f2 paginated JSON reconciliation | $0.0021 | $0.0040 | 0 — `jq`/python |
| f3 test-suite fix, f8 verbose test suite (170K chars per run) | $0.0085, $0.0136 | $0.0057, $0.0050 | 1, 2 — the agent ran `pytest \| tail -50` |
| f4 grep-driven rename, f5 branch-diff review | $0.0142, $0.0100 | $0.0077, $0.0082 | 0 |
| f6 CSV reconciliation | $0.0015 (failed to write its files) | $0.0022 (correct) | 0 |
| f7 verbose build fix (85K chars per run) | $0.0112 | $0.0038 | 1 — `build.py \| head -100`, `\| grep '^ERROR'` |
| f10 database investigation via `db_query` | $0.0035 | $0.0048 | 0 — the agent wrote aggregate SQL |

All verdicts identical in both arms (except f6, where the plain loop did not write its output files). The cost
differences in these two groups are run noise.

## Pros and cons

**Pros**

- On tasks that take large results whole, it removes 80–90% of the cost and cuts the peak context by an order of
  magnitude, with every check still passing (l1, l2). On whole-page documentation reads it saves a little (f9).
- It costs the prefix cache nothing: the condensed view replaces the original before the model ever sees it, the
  context stays append-only, and the durable log keeps every byte — `expand_result` returns any result verbatim.
- It is a plugin on the stock loop: no custom loop, no session tape, mount and unmount.
- Across 21 scenarios and 47 runs it never made a verdict worse once the safeguards below were in place.

**Cons**

- On most tasks it never triggers. A capable agent filters its own output — `\| head`, `\| grep ERROR`, `\| tail -50`,
  `jq`, aggregate SQL — so nothing large reaches the context. In 18 compute-style runs it condensed five results.
- Condensing the wrong thing breaks the task. The first l2 run condensed a 3.7K rules file and lost its nine rules:
  every posting went to the wrong directory (0/45). Three safeguards now cover that class (documents below 6000 chars
  are never condensed; results in the first two steps of a turn are not, unless larger than 8000 chars; rule-style
  keys, table rows and list items count as structured lines), but a heuristic cannot know which line is a rule.
- Condensing what the model needs is worse than not condensing: it costs a step and the full text comes back anyway.
  On s10 the model expanded all 64 condensed reads and the run cost 6% more. Expansion back-off (stop condensing a
  tool after two expansions) limits the damage; it cannot foresee it.
- Facts inside prose sentences cannot be kept by any rule. What survives condensation is structure: key/value lines,
  headings, tables, lists, error lines with context. On f9 the three remaining expansions were all for facts in
  sentences.
- Every content type needs its own rules, and each rule was added after a shape that had gone wrong: over-long lines,
  JSON items, search caps, diff hunks, tables, lists.

**When to mount it**: whenever tools return large results the agent cannot pipe — document reads, page fetches,
MCP or database tools — and in long sessions, where every condensed byte is paid again at cache price on each later
step. **When it is idle**: short coding sessions (code and search results are never condensed) and tasks where the
agent computes over data instead of reading it.

## Development

```bash
npm install
npm run link:dsh     # symlinks the harness peer packages from ~/.dsh/source/current
npm test
npm run build        # lib/ is committed: `dsh plugin add github:…` installs from git without building
```

The contract tests mount the real stock loop with the request-reconstruction invariant and check: a large data result is condensed before the next step and expanded on demand; code and error results are never touched; the durable log keeps the original and the replacement citing it.

## Origin

Extracted from the in-turn fold of [dsh-slice-agent-loop](https://github.com/TT-Wang/dsh-slice-agent-loop), where it was the one saving that never needed the loop's session tape. Chinese notes: [README.zh.md](README.zh.md).
