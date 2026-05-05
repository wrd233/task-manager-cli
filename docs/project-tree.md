# Project Tree

项目语义树是对 Logseq Project Page 的只读理解。它不是新的项目编辑器，也不是复杂图数据库。

本轮目标是先看懂项目页里的结构化区域，并输出人类视图和 Agent 视图。系统不会强迫所有项目都有树，
也不会强迫项目 OKR 化。

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
**[里程碑]**
**[工作流]**
**[小任务]**
**[具体事务]**
**[资源]**
**[成果]**
**[无成果]**
**[想法]**
**[注]**
**[AI注]**
**[待澄清]**
```

## Node Semantics

- `[目标]` ：项目想达成的方向或结果，不强制 OKR。
- `[里程碑]` ：阶段性节点。
- `[工作流]` ：持续推进的一类工作线。
- `[小任务]` ：轻量多步骤事务。
- `[具体事务]` ：Action Item 或 Action Item 组。
- `[资源]` ：Reference / Resource，不进入行动流。
- `[成果]` ：结果标记。
- `[无成果]` ：明确表示无需沉淀成果。
- `[想法]` ：Idea。
- `[注]` ：用户注。
- `[AI注]` ：AI 注。
- `[待澄清]` ：Clarify 候选。

## Commands

```bash
tm project tree 项目-韩国旅行
tm project tree 项目-韩国旅行 --detail
tm project tree 项目-韩国旅行 --format json
tm view project-tree 项目-韩国旅行
tm agent project-tree 项目-韩国旅行 --format json
```

Brief human view 默认不展示完整 metadata。`--detail` 会包含 node id、line 等定位信息。JSON / Agent
视图包含 source、location、node type、object id、action / idea / resource / result / annotation
分类，但默认不塞入完整项目页原文。

## Empty Or Simple Projects

没有结构化 marker 的 Project Page 仍可以展示原始层级，并标注为未识别结构。系统不会要求用户重构项目页。

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
