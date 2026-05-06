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

Round 3.5 同时支持非加粗变体，例如 `[目标]`、`[小任务]`、`[资源]`。推荐格式仍是加粗形式，
因为它在 Logseq 中更醒目，也更容易与普通行首文本区分。

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

Round 3.5 的大样本验证把以下情况标为 suspicious，而不是自动修复：

- 空项目页；
- 没有结构化 marker 的项目页；
- 深度超过 8 层的节点；
- unknown 但看起来像行动的节点；
- resource 节点带 task 状态；
- source/location 与 definition record 不一致；
- duplicate node id。

这些报告用于人工判断是否需要整理项目页，不会触发自动移动、删除、合并或重排。

## Source / Location

Project Tree node 的 `source_item_id` 来自 Logseq block uuid；没有 uuid 时使用相对文件路径、行号和内容 hash。
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
