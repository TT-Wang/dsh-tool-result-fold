# dsh-tool-result-fold

In-turn folding of tool results for the [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) **stock agent loop**. A standalone plugin: no custom loop, no session tape. Mount it next to the default `AgentLoop` and large tool results enter the model's context condensed, while the durable session log keeps every byte.

## Why

Under a prefix-cached pricing model (DeepSeek: a cache hit costs 1/30 of a miss) an append-only transcript is already the cheapest context for short sessions. What still grows the bill is every large tool result being paid once at miss price and then carried at hit price on every later step. Condensing results **as they enter** removes those bytes without ever rewriting the prefix.

## How it works

- On every `agent/pre-step` the plugin looks at the tool results that landed since the previous step and condenses them by content type — the routing borrowed from [Headroom](https://github.com/chopratejas/headroom):
  - **code** (by path or shape) and **search** (grep/glob) results are never touched;
  - **logs / build / test output** keep every error, failure and warning line with surrounding context, stack traces and summary lines, similar lines de-duplicated;
  - **documents / data** keep the first and last lines and every structured line (`key = value`, `key: value`, headings, section markers), with same-shaped appendix blocks kept only up to a cap; single lines longer than 1500 characters are cut to head and tail;
  - small results, and results that would not shrink by at least 45%, are left alone.
- The condensed view shadows the original through a `tool/result` **surface replacement** event that cites the shadowed node — the same mechanism the harness's own compaction pruner uses, and one the session invariant explicitly allows. The original stays in the durable log, the model's context stays append-only, and the loop's request-reconstruction invariant (`request == session.deriveMessages()`) keeps holding.
- The view's first line names the way back: `expand_result({"turn": t, "step": s, "call": n})` returns the full result verbatim.
- A `<fold>` section in the system prompt tells the model what it is looking at and that a whole-file read costs no more context than its condensed view.

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
| `digest.minChars` | 1500 | data results below this are never condensed |
| `digest.headLines` / `tailLines` | 10 / 4 | lines kept at both ends of a data result |
| `digest.maxKeepRatio` | 0.55 | give up when the view would keep more than this share of the original |
| `digest.structuredBlockCap` / `structuredBlockMin` | 12 / 3 | structured lines kept per block outside the head |
| `digest.logMinChars` / `logMaxErrors` / `logContextLines` | 512 / 10 / 3 | log rules |
| `digest.maxLineChars` / `lineHeadChars` / `lineTailChars` | 1500 / 700 / 300 | over-long single lines in data results |

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
