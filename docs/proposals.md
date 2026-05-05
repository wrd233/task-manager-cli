# Proposals

Proposal 是结构化变更建议，不是普通批注。批注表达“有人留下了一段说明或判断”；Proposal
表达“系统建议对某个对象、关系、状态或 Logseq 位置做一个可审核、可应用、可回滚的变更”。

本轮新增通用 `proposals` 表和 `proposal_events` 历史表。旧的 `write_proposals` 仍保留给既有
`tm write ...` 命令使用；新的 `tm proposal ...` 是后续 Clarify、远端 API 和 Logseq
安全写回的语义底座。

## Types

- `status_change` ：修改 GTD / 处理状态。
- `relation_change` ：添加或修改 relation。
- `annotation` ：添加 CLI 内部 annotation，不写 Logseq。
- `needs_clarification` ：标记待澄清。
- `logseq_append_marker` ：向 Logseq 块追加 `**[注]**` 、 `**[AI注]**` 、 `**[待澄清]**`
等子块。
- `logseq_task_marker` ：修改 Logseq task marker，目前支持 `TODO` / `DOING` / `DONE` /
`WAITING` 。
- `create_mini_project` ：预留，小任务系统下一轮展开。
- `result_marker` ：追加 `**[成果]**` / `**[无成果]**` ，成果系统下一轮展开。
- `create_project_node` 、 `delete` 、 `merge` 、 `bulk_logseq_writeback` 、 `rewrite_title` 、
`project_tree_rewrite` ：预留高风险或中风险能力。

## Status

- `suggested` ：已提出，未审核。
- `accepted` ：用户已接受，允许进入 apply。
- `rejected` ：用户拒绝。
- `edited` ：预留，表示用户编辑过建议。
- `applied` ：已经应用，并记录 `applied_record` 。
- `rolled_back` ：已尽量回滚，并记录 `rollback_record` 。
- `expired` / `superseded` ：预留。

`apply` 前必须是 `accepted` 。AI 或 rule-based provider 只能生成 `suggested`
proposal，不能直接改事实。

## Risk

- `low` ：状态建议、relation 建议、CLI 内部 annotation、待澄清标记。
- `medium` ：写回 `**[AI注]**` 、写回结果标记、创建小任务、创建项目节点、修改 task marker。
- `high` ：删除、合并、大量写回 Logseq、改写原文标题、大规模项目树调整。

高风险 Proposal 不允许批量自动应用。本轮只实现低风险 annotation 和中风险最小 Logseq
写回；高风险类型只做风险与边界预留。

## CLI

```bash
tm proposal list
tm proposal show <proposal-id> --preview
tm proposal accept <proposal-id>
tm proposal reject <proposal-id>
tm proposal apply <proposal-id> --yes
tm proposal rollback <proposal-id>
```

创建示例：

```bash
tm proposal create-annotation --object 12 "需要先确认输入边界"
tm proposal create-marker AI注 "建议先做最小验证" --object 12
tm proposal create-task-marker WAITING --object 12
```

## Rollback

内部 annotation proposal 的 rollback 会删除本次 apply 创建的 annotation。Logseq 写回 proposal 的
rollback 使用 apply 前生成的备份恢复目标文件。若备份缺失或未来操作不是可逆
append-only，本系统会保留应用记录并明确报错，而不是假装已回滚。

## Provider Generated Proposals

Clarify provider 只能生成 `suggested` Proposal。Provider 返回的 classification、状态、marker 或
annotation 都只是候选建议，不是事实。

系统会把 provider response 中的 proposal candidates 转换为 Proposal，并记录：

- provider summary；
- provider confidence；
- reasoning summary；
- `needs_user_confirmation` ；
- 对应 Review Session。

高风险 provider 建议不会自动 apply，也不允许批量自动 apply。

## Edit / Supersede

本轮支持基础编辑：

```bash
tm proposal edit 1 --title "新标题"
tm proposal edit 1 --content "新的 annotation 或 marker 内容"
tm proposal edit 1 --marker AI注
tm proposal edit 1 --task-marker WAITING
tm proposal edit 1 --risk medium
tm proposal supersede 1 --with 2
```

编辑会保留 `proposal_events` 历史，并把 Proposal 状态置为 `edited` 。 `edited` Proposal 仍可
`accept` / `apply` 。已 applied 或 rolled back 的 Proposal 不允许静默原地修改。

`supersede` 会把旧 Proposal 标记为 `superseded` ，新 Proposal 继续独立走审核和应用流程。

## Provider Validation

Provider-generated proposals 会经过白名单校验：

- provider candidate type 必须可映射到系统 Proposal type；
- risk 必须是 `low` / `medium` / `high` ；
- target 必须是 object；
- target object_id 如果出现，必须匹配当前 clarify item；
- payload 必须是 object；
- content 会进入 redaction / payload 控制；
- invalid JSON 或 schema mismatch 会让 review item 进入 `failed` / `parse_error` 。

不合法 provider proposal 不会被创建，更不会 apply。
