# Project Tree

项目语义树是对 Logseq Project Page 的只读理解。它不是新的项目编辑器，也不是复杂图数据库，也不是
项目页全文 AST。

`tree` 只展示识别出的结构化项目节点；`show` 负责展示当前对象或任意 semantic node 下面的完整 Logseq 原始子树。
系统不会强迫所有项目都有树，也不会强迫项目 OKR 化。

## Semantic Tree vs Raw Block Tree

系统内部区分两类视图：

- semantic project tree：只包含被 marker 识别出的项目结构节点，用于 `tree`、`ls nodes`、Agent
  project-tree 和项目质量报告。
- raw block subtree：保留 Logseq 原始块、普通备注、TODO 子块、properties 和缩进，用于
  `show <node>`、mini context `show`、object context `show` 和 Agent raw evidence 视图。

没有匹配项目结构规则的普通 block 默认不会进入 semantic tree，也不会显示成 `[未识别]`。这些内容仍保留在
raw block subtree 中，因此不会丢失。

## Source

正式 Project 通常对应 Logseq 项目页，并倾向包含：

```text
PARA:: [[PARA/Project]]
```

项目树主要来自该页面的 Logseq 原始缩进层级。引用和 relation 只是补充。

## Supported Markers

项目树识别这些 marker：

```text
**[目标]**
**[价值层]**
**[目标层]**
**[里程碑]**
**[工作流]**
**[小任务]**
**[具体事务]**
**[资源]**
**[项目收件箱]**
**[成果]**
**[无成果]**
**[想法]**
**[反思]**
**[注]**
**[AI注]**
**[待澄清]**
```

同时支持非加粗变体，例如 `[目标]`、`[小任务]`、`[资源]`，并兼容 `Goal`、`Milestone`、
`Workflow`、`Tasks`、`Resources`、`Results`、`Ideas`、`Inbox`、`Reflection` 等英文行首 marker。
推荐格式仍是加粗形式，因为它在 Logseq 中更醒目，也更容易与普通行首文本区分。

## Node Semantics

- `[目标]` ：项目想达成的方向或结果，不强制 OKR。
- `[价值层]` / `[目标层]` ：更高层的价值和目标分区。
- `[里程碑]` ：阶段性节点。
- `[工作流]` ：持续推进的一类工作线。
- `[小任务]` ：轻量多步骤事务。
- `[具体事务]` ：Action Item 或 Action Item 组。
- `[资源]` ：Reference / Resource，不进入行动流。
- `[项目收件箱]` ：项目内暂存区。
- `[成果]` ：结果标记。
- `[无成果]` ：明确表示无需沉淀成果。
- `[想法]` ：Idea。
- `[反思]` ：复盘和经验。
- `[注]` ：用户注。
- `[AI注]` ：AI 注。
- `[待澄清]` ：Clarify 候选。

## Commands

```bash
tm project tree 项目-韩国旅行
tm project tree 项目-韩国旅行 --detail
tm project tree 项目-韩国旅行 --no-color
tm project tree 项目-韩国旅行 --format json
tm view project-tree 项目-韩国旅行
tm agent project-tree 项目-韩国旅行 --format json
tm agent project-node <node-id> --raw --context
```

Brief human view 默认不展示完整 metadata 或 source location。`--detail` 会包含 node id、type、line
和 children count 等定位信息。默认渲染会在顶层节点之间加空行，并在支持 ANSI 的终端中用黄色加粗显示
marker；`--no-color`、非 TTY 或 `NO_COLOR=1` 会禁用 ANSI。

JSON / Agent 视图包含 source、location、node type、object id、idea / resource / result /
annotation 分类，但默认不塞入完整项目页原文，也不会把 raw subtree 全部塞进 semantic tree。

普通 TODO 默认不进入 `tree`。它会继续作为行动对象出现在 `ls tasks` / inventory 中；如果需要查看某个节点下
的 TODO 和普通备注，进入该节点后使用 `show`。

`show` 支持所有 semantic project node：目标、价值层、目标层、里程碑、工作流、具体事务、小任务、资源、
成果、无成果、想法、反思、项目收件箱、待澄清、注、AI注。输出包含节点标题、项目、source location、
节点类型、简洁 ancestor context 和当前 raw subtree；detail 模式包含 source line / node id / object id。
重复标题节点依赖 stable node id / source location 定位。

人类可读输出会对 TODO / DOING / WAITING / DONE / CANCELED 使用偏深色 ANSI。`NO_COLOR=1`、非 TTY、
`--no-color`、`tree plain` 或 `tree no-color` 会输出纯文本；JSON / Agent structured 输出不带 ANSI。

## Empty Or Simple Projects

没有结构化 marker 的 Project Page 不会再默认展示完整原始层级，也不会生成 `[未识别]` 节点。`tree`
会提示没有可展示的结构化节点；需要看原始内容时使用 `show` 或后续 raw/debug 视图。系统不会要求用户重构项目页。

Round 3.5 的大样本验证把以下情况标为 suspicious，而不是自动修复：

- 空项目页；
- 没有结构化 marker 的项目页；
- 深度超过 8 层的节点；
- 没有结构化 marker 的项目页；
- resource 节点带 task 状态；
- source/location 与 definition record 不一致；
- duplicate node id。

这些报告用于人工判断是否需要整理项目页，不会触发自动移动、删除、合并或重排。

## Source / Location

Project Tree node 的 `source_item_id` 来自 Logseq block uuid；没有 uuid 时使用相对文件路径和行号。
child Action Item 的 canonical location 以自己的 definition block 为准，不继承父节点 location。
Daily Log 中的纯 block ref 只作为 exposure，不复制成新的 task definition。

## Quality Report

```bash
tm report project-tree-quality
tm report project-tree-quality --format json
tm project tree-quality
```

报告覆盖 scanned / recognized project pages、node type distribution、mini project/resource/idea/result 计数、
source/location mismatch、duplicate node id、parse warnings 和 suspicious node examples。

## Readonly Boundary

Round 3 不做：

- 移动块。
- 删除块。
- 合并块。
- 重排项目页。
- 大规模项目树重写。
- 自动改项目标题。
- 自动把项目整理成 OKR。

所有写回仍必须来自 Proposal，并走 preview / accept / apply / rollback。

## Real Graph Fix: Tab Indentation

真实 Logseq graph 常用 Tab 缩进。parser 现在按以下语义计算层级：

```text
indent = tab_count + space_count // 4
```

因此空格缩进、Tab 缩进和 mixed Tab+space 都能恢复 parent / children。block properties（例如 `id:: ...`）会挂到父 block，不作为普通树节点展示。

Project Tree node 的 `source_item_id` 来自 Logseq block uuid；没有 uuid 时使用相对文件路径和行号，不再包含内容 hash。这修复了真实项目页里 `tree` 全部平铺，以及标题 / task marker 变化导致树节点身份变化的问题。

## Tree / Show Split

在 Human Shell 中：

```text
cd /projects/项目-韩国旅行
tree          # semantic project tree
cd 整理打车攻略
tree          # 当前节点下的 semantic subtree
show          # 当前节点的完整 raw Logseq subtree
tree raw      # 在 project node context 下等价查看 raw subtree
tree detail   # 临时显示 node id / type / line / children count
tree plain    # 禁用 ANSI 颜色
```

如果当前节点下没有结构化子节点，`tree` 会提示使用 `show` 查看完整 Logseq 子树。

## Marker Aliases

Project Tree 会把历史项目模板 alias 归一到当前模型：

- `[具体目标]` 识别为 objective。
- `[资源列表]` 识别为 resource。
- `[头脑风暴]` 和 `[随想]` 识别为 idea。
- `[心得]`、`[复盘]`、`[经验]` 识别为 reflection。
- `[产出]`、`[交付物]` 识别为 result。

空 section header 保留为 tree node，但不会被抽取成 fake action object。
