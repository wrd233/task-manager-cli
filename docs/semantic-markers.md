# Semantic Markers

Logseq adapter 只识别明确的行首语义标记，不把 `[[想法]]` 或普通“想法”二字误抽为 Idea。

## Line Prefix Markers

- `**[想法]**` ：Idea。可以是设计型对象，也可能孕育行动。
- `**[待澄清]**` ：需要 Clarify。当前记录为 semantic marker，后续 Clarify 会生成问题流。
- `**[注]**` ：用户注。进入 record metadata / child role，不等同于 Proposal。
- `**[AI注]**` ：AI 注。与用户注区分，写回属于中风险。
- `**[成果]**` ：结果标记预留。
- `**[无成果]**` ：无成果标记预留。
- `**[目标]**` ：项目树目标节点。
- `**[里程碑]**` ：项目树阶段节点。
- `**[工作流]**` ：项目树工作线节点。
- `**[小任务]**` ：Mini Project / 轻量多步骤事务。
- `**[具体事务]**` ：项目树中的具体事务。
- `**[资源]**` ：Reference / Resource，不进入行动流。

内部 metadata 使用无括号的归一化值，例如 `semantic_marker: "AI注"` 。

## Tags

行末标签会写入 `semantic_tags` ：

- `#inbox`
- `#someday`
- `#waiting`
- `#reference`

内部存储为无 `#` 小写值，例如 `reference` 。带 `#reference` 的 block 不进入 Action Item / Idea
行动流转。

## Task Markers

支持：

- `TODO`
- `DOING`
- `DONE`
- `WAITING`

对象状态在数据库中使用小写值： `todo` 、 `doing` 、 `done` 、 `waiting` 。

## Boundaries

- `[[想法]]` 是页面链接，不是 Idea marker。
- 普通文本中的“想法”不是 Idea marker。
- Reference / Resource 是资源，不应直接当成 Action Item。
- Annotation 是笔记或说明，Proposal 是可审核、可应用、可回滚的结构化变更。
