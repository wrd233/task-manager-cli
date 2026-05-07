# Project Lifecycle

本页是 Project Lifecycle 完整闭环的设计铺垫，不是本轮完整实现。当前代码只新增只读 raw evidence 能力和命令语义文档，不做 project create、自动重构、自动移动块或 Agent apply。

## Lifecycle Map

```text
Create Project
Capture into Project
Project Inbox / Unplaced
Clarify Unplaced
Agent Restructure Pack
Restructure Proposal
Phased Apply
Project Review
```

## Create Project

未来命令：

```bash
tm project create <name>
```

语义：创建一个 Logseq Project Page 的 proposal，包含最小 PARA marker 和初始 inbox。默认不直接写真实 graph，必须 preview / accept / apply。

## Capture Into Project

未来命令：

```bash
tm project capture --project <project> "content"
tm project inbox --project <project>
```

语义：把任务、想法、资源、备注捕获到项目内。第一落点优先是 `[项目收件箱]` / `project_inbox`，避免提前决定结构。

## Project Inbox / Unplaced

轻量语义常量：

```text
project_inbox
unplaced
project_capture
restructure_candidate
project_result
```

这些分类用于未来 query / Agent pack，不代表当前 schema 已经完整升级。

## Clarify Unplaced

未来命令：

```bash
tm project clarify <project>
```

语义：只针对 project inbox / unplaced 条目做澄清，输出 membership、marker、capture 或 restructure proposal。Clarify 仍然只收集证据和建议，不直接移动块。

## Agent Restructure Pack

未来命令：

```bash
tm agent project-restructure-pack <project>
tm agent project-node <node-id> --raw --context
```

本轮已实现 `tm agent project-node <node-id> --raw --context`。它输出 node metadata、ancestor context、raw subtree、source location、project id/name，并保持 no writeback。`--format json` 可用于机器读取。

`project-restructure-pack` 未来应组合 project tree、project inbox、unplaced items、recent results、open tasks、node raw evidence 和风险提示。

## Restructure Proposal

未来命令：

```bash
tm project restructure <project>
```

语义：生成 proposal，而不是直接改页。Proposal 必须描述建议移动/归并/新增节点的理由、证据、风险和阶段。

## Phased Apply

未来命令：

```bash
tm project restructure apply <proposal> --phase <n>
```

语义：分阶段 apply。每个阶段都必须可 preview、可备份、可 rollback。高风险操作默认需要显式确认。

## Project Review

未来命令：

```bash
tm project review <project>
```

语义：定期检查项目 inbox、waiting、open tasks、成果、无成果、反思和 unplaced 条目，生成 review session 和低风险建议。

## Current Non-Goals

本轮不实现完整 project create，不做 project inbox 写回闭环，不做自动移动/删除/合并/重排 Logseq block，不做 Agent 直接 apply，不做复杂 TUI，不清理真实 graph。
