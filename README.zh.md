# dsh-tool-result-fold

给 [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) **原生 agent loop** 加"轮内折叠"的独立插件:不换 loop、不要磁带。挂在默认 `AgentLoop` 旁边,大的工具结果进入模型上下文时就被折成紧凑视图,而会话日志保留每一个字节。

## 为什么

在前缀缓存计价下(DeepSeek 命中价是未命中的 1/30),只追加的 transcript 对短会话已经是最便宜的上下文。还在涨账单的是每条大工具结果:先按未命中价付一次,之后每一步按命中价再带一遍。**在进入时**就折叠,把这些字节去掉,而且永不改写前缀。

## 机制

- 每个 `agent/pre-step`,插件看上一步之后落盘的工具结果,按内容类型折叠(路由思路来自 [Headroom](https://github.com/chopratejas/headroom)):
  - **代码**(按路径或形态)与 **搜索**(grep/glob)结果从不折;
  - **日志 / 构建 / 测试输出** 留每条错误、失败、警告行及前后上下文、栈帧与摘要行,相似行去重;
  - **文档 / 数据** 留头尾行与每条结构行(`key = value`、`key: value`、标题、段标记),同形附录块只留到上限;超过 1500 字符的单行按字符头尾截断;
  - 小结果,以及折了省不到 45% 的结果,原样放行。
- 折叠视图通过 `tool/result` **surface 替换事件** 遮蔽原节点,并引用被遮蔽的 seq——这是 harness 自带 compaction pruner 的同一机制,会话不变量明确允许。原文留在日志里,模型的上下文只追加不改写,原生 loop 的请求重建不变量(`request == session.deriveMessages()`)始终成立。
- 视图首行写明回去的路:`expand_result({"turn": t, "step": s, "call": n})` 逐字返回原文。
- 系统提示词里加一段 `<fold>`,告诉模型它看到的是什么,以及整读一个文件不比折叠视图多占上下文。

两条走不通的路,记在这里:在 `session/event` 回调里追加替换事件(会话禁止重入追加);在 `tools/post-execute` 里替换内容(日志里就只剩折后文本)。

## 安装

```bash
dsh plugin add github:TT-Wang/dsh-tool-result-fold
```

或在代码里:

```ts
import ToolResultFold from '@dsh-external/dsh-tool-result-fold'

await ctx.plugin(ToolResultFold, {
  digest: { minChars: 1500, headLines: 10, tailLines: 4, maxLineChars: 1500 },   // 全部可选
})
```

不要和已经自带折叠的 loop(如 `dsh-slice-agent-loop`)同挂;它是给原生 loop 用的。

### 配置

| 键 | 默认 | 含义 |
|---|---|---|
| `enabled` | `true` | `false` 时只注册 `expand_result` |
| `digest.minChars` | 1500 | data 类低于此字符数不折 |
| `digest.headLines` / `tailLines` | 10 / 4 | data 类头尾各留几行 |
| `digest.maxKeepRatio` | 0.55 | 折后仍超过原文这个比例就放弃 |
| `digest.structuredBlockCap` / `structuredBlockMin` | 12 / 3 | 头部区外每个结构块最多/至少留几行 |
| `digest.logMinChars` / `logMaxErrors` / `logContextLines` | 512 / 10 / 3 | 日志规则 |
| `digest.maxLineChars` / `lineHeadChars` / `lineTailChars` | 1500 / 700 / 300 | data 类超长单行 |

## 开发

```bash
npm install
npm run link:dsh     # 从 ~/.dsh/source/current 软链 harness 的 peer 包
npm test
npm run build        # lib/ 是提交的:`dsh plugin add github:…` 从 git 安装,不会构建
```

契约测试挂真实的原生 loop 加请求重建不变量,验证:大的数据结果在下一步前被折叠、可按需展开;代码与错误结果从不动;日志保留原文与引用它的替换事件。

## 来源

从 [dsh-slice-agent-loop](https://github.com/TT-Wang/dsh-slice-agent-loop) 的轮内折叠里抽出来的——那是全部实验里唯一不需要磁带的收益。
