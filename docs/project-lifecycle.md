# Project Lifecycle

本页描述当前已实现的 Project Lifecycle 最小完整闭环。系统支持创建项目页、项目内捕获、项目 inbox/unplaced、clarify 生成 Proposal、Agent project pack、Agent restructure pack、Agent output 转 Proposal、安全 apply/rollback、project health 和 dashboard 集成。

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

```bash
tm project create "项目名"
tm project create "项目名" --template minimal|standard
tm project create "项目名" --goal "形成第一版成果"
tm project create "项目名" --enter
```

语义：创建 `pages/<项目名>.md`，不覆盖已有页面，写入 PARA project properties 和项目模板，并创建内部 Project object。`--preview` 只输出 diff。Human Shell 支持 `project create "项目名"` 和 `new project "项目名"`，最近一次创建可用 `undo` 删除新建页。

## Capture Into Project

Human Shell 在项目上下文内支持：

```text
todo "..."
idea "..."
resource "..."
result "..."
note "..."
mini "..."
```

默认落点：`todo` 到 `[项目收件箱]`，`idea` 到 `[想法]`，`resource` 到 `[资源]`，`result` 到 `[成果]`，`note` 到 `[反思]`，`mini` 到 `[小任务]`。这些写回都是 append-only，并进入 operation history，可预览、备份、撤销。

## Project Inbox / Unplaced

轻量语义常量：

```text
project_inbox
unplaced
project_capture
restructure_candidate
project_result
```

命令：

```bash
tm project inbox <project>
tm project unplaced <project>
```

Shell：

```text
ls inbox
ls unplaced
cd inbox
```

Unplaced 表示对象属于项目，但尚未归位到具体 semantic node。它不会进入 `tree` 的结构节点，但仍会出现在 `ls tasks` / `ls ideas` / `ls resources` 等对象列表里。

## Clarify Unplaced

```bash
tm project clarify <project> --target unplaced --mode quick|standard|deep|ai
tm project clarify <project> --target inbox
```

Shell：

```text
clarify unplaced
clarify inbox
clarify project
```

Clarify 输出 Proposal，不直接写回。当前支持生成 `link_object_to_node`、`convert_idea_to_task`、`promote_to_mini_project` 等候选。

## Agent Restructure Pack

```bash
tm agent project-pack <project> --format json|markdown
tm agent project-restructure-pack <project>
tm agent project-node <node-id> --raw --context
```

`project-pack` 包含项目 metadata、semantic tree、project inbox、unplaced objects、tasks、ideas、resources、results、mini projects、recent records、project health、constraints 和 available operations。

`project-restructure-pack` 面向结构调整，包含 semantic tree、unplaced objects、health、node summaries、raw evidence command、proposal schema、allowed proposal types、forbidden operations 和 expected output schema。默认不 dump 完整项目页原文；需要 raw evidence 时使用 `tm agent project-node <node-id> --project <project>`。

## Restructure Proposal

```bash
tm project restructure <project> --from-agent-output output.json
tm project restructure <project> --provider mock --dry-run
```

Agent output schema:

```json
{
  "summary": "",
  "questions_for_user": [],
  "proposed_nodes": [],
  "object_mappings": [],
  "proposal_candidates": [],
  "risks": [],
  "unplaced_remaining": []
}
```

合法输出会转为 Proposal，例如 `create_project_node`、`link_object_to_node`、`append_block_ref_to_node`、`promote_to_mini_project`、`convert_idea_to_task`、`mark_object_as_result`。无效 JSON 或缺字段会被拒绝，且不会写回 Logseq。

## Phased Apply

```bash
tm proposal show <id> --preview
tm proposal accept <id>
tm proposal apply <id> --yes
tm proposal rollback <id>
```

当前可 apply 的安全类型：`create_project`、`create_project_node`、`link_object_to_node`、`append_block_ref_to_node`、`promote_to_mini_project`、`mark_object_as_result`。高风险类型如 `move_original_block`、`delete_block`、`merge_blocks`、`mass_reorder` 不提供直接 apply。

## Project Review

```bash
tm report project-health <project>
```

Shell:

```text
quality project
quality health
```

指标包括 active tasks、waiting、unplaced、ideas、resources、results、done without result、pending proposals、open reviews、tree depth/node count、last activity 和 health score。

## Dashboard Integration

`/dashboard` 增加 Projects Needing Attention 和 Unplaced Items。Shell 支持：

```text
cd /dashboard
ls quality
ls unplaced
ls project-health
```

## Workspace Flow

Project lifecycle work can be kept in one persistent terminal workspace:

```text
cd /projects/<project>
layout on
tree
ls tasks
show <node>
focus <task>
insert line
view health
proposals
preview 1
apply 1
undo
```

`layout on` keeps project context, current view, focus, actionable list, last message, and sync status visible. Project capture commands (`todo` / `idea` / `resource` / `result` / `note` / `mini`) refresh the current view instead of switching away from it. Proposal and health work have dedicated views so Agent output does not flood the project tree or show view.

## Safety Boundary

Agent / Provider 不能直接修改 Logseq。结构变更必须先生成 Proposal。系统不自动删除、移动、合并、重排原始 Logseq 块。所有 Logseq 写回都要求 preview、backup 和 rollback；无法安全实现的高风险操作只允许停留在 Proposal 层。

## Physical Restructure Migration

真实 graph 的历史项目大量使用旧模板 section：`[具体目标]`、`[资源列表]`、`[头脑风暴]`。当前模型会将它们收敛为：

- `[具体目标] -> [目标]`
- `[资源列表] -> [资源]`
- `[头脑风暴]` / `[随想] -> [想法]`
- `[心得]` / `[复盘]` / `[经验] -> [反思]`
- `[产出]` / `[交付物] -> [成果]`

物理迁移只做保守写回：标准化 section 名、补缺失标准 section、保留原始 TODO / id:: / 链接 / 子块。无法判断的内容留在原处或项目收件箱，不做删除、合并或重排。
