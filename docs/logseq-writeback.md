# Logseq Writeback

## Project Lifecycle Writeback

Project Lifecycle 写回遵循强安全边界：

- Agent / Provider 不得直接修改 Logseq。
- 高风险结构变更必须走 Proposal。
- 不自动删除、移动、合并、重排原始 Logseq 块。
- 所有写回必须 preview / backup / rollback。
- 无法安全实现的高风险 apply 只允许生成 Proposal，不允许 apply。

当前安全写回：

- `create_project`：创建新页面，不覆盖已有页面。
- `create_project_node`：append 到项目页、目标 section 或 parent node。
- `append_block_ref_to_node`：append block ref，不移动原始 block。
- project capture：Shell 在项目上下文内 append 到 `[项目收件箱]`、`[想法]`、`[资源]`、`[成果]`、`[反思]`、`[小任务]`。

Internal-only apply：

- `link_object_to_node` 更新 SQLite relation。
- `promote_to_mini_project` / `mark_object_as_result` 写内部 annotation。

典型命令：

```bash
tm proposal show <id> --preview
tm proposal accept <id>
tm proposal apply <id> --yes
tm proposal rollback <id>
```

本轮 Logseq 写回只提供安全骨架，不做大规模移动、重排、项目树重写或原文改写。所有写回必须由
Proposal 驱动，并且必须明确目标 source / location。

## Safety Boundary

- 默认 `write_mode=disabled` ，不会写 Logseq。
- 创建写回 Proposal 需要配置 Logseq graph。
- 应用写回需要 `write_mode=guarded` 或 `agent` 。
- `guarded` 默认需要 `--yes` 。
- 写回只允许目标文件位于配置的 graph 内。
- apply 前会重新生成 preview，检查目标文件 hash，并备份原文件。
- rollback 通过备份恢复目标文件。

建议先只对临时测试 graph 使用：

```bash
tm config init --graph /tmp/test-logseq-graph
tm config set-write-mode guarded
```

不要默认指向真实日常 Logseq graph。真实 graph 写回应在更多测试、preview 和人工确认后再启用。

## Supported Writes

追加子块：

- `**[注]**`
- `**[AI注]**`
- `**[待澄清]**`
- `**[成果]**`
- `**[无成果]**`
- `**[小任务]**`
- `**[资源]**`

修改 task marker：

- `TODO`
- `DOING`
- `DONE`
- `WAITING`

`WAITING` 已在 parser 中识别并写回，但不同 Logseq 插件或工作流可能对它的展示支持不一致。

## Preview / Diff / Apply

```bash
tm proposal create-marker AI注 "建议先确认输入边界" --object 12
tm proposal show 1 --preview
tm proposal accept 1
tm proposal apply 1 --yes
tm proposal rollback 1
```

preview 不修改文件。diff 使用 unified diff。apply 后重新 `tm sync logseq` 可以识别新增语义标记和
task marker 变化。

## Not Supported In Round 1

- 移动块。
- 删除块。
- 合并块或页面。
- 大规模项目树调整。
- 改写原文标题。
- 无 Proposal 的任意写回。

## Clarify Writeback

Clarify provider 可以建议 Logseq 写回 Proposal，例如：

- 追加 `**[AI注]**` ；
- 追加 `**[待澄清]**` ；
- 修改 task marker 为 `WAITING` ；
- 追加 `**[成果]**` / `**[无成果]**` 。

Provider 不能直接写回。Clarify 只创建 `suggested` Proposal。写回仍然需要：

```bash
tm proposal accept <proposal-id>
tm proposal show <proposal-id> --preview
tm proposal apply <proposal-id> --yes
```

rollback 仍使用第 1 轮的备份恢复机制。

Round 3.5 修复了同一文件连续多次 append-only 写回时的备份碰撞风险。每次 apply 都会生成唯一备份文件；
rollback 按当前 Proposal 的 `applied_record.backup_path` 恢复，因此可以先回滚第二次写回，再回滚第一次写回。

## Round 3 Project Writeback

项目树默认只读。项目纳管 Proposal 默认只写内部 relation，不移动原始 Logseq 块。

Round 3 允许的项目相关写回仍然是 append-only：

- 在目标节点下追加 block ref。
- 追加 `**[AI注]**`。
- 追加 `**[待澄清]**`。
- 追加最小 `**[小任务]**` 节点。
- 追加 `**[资源]**` 引用。

仍然禁止移动、删除、合并、重排项目页、大规模项目树重写或自动改标题。Provider 不能直接写回项目树。

## Human Shell Direct Action

Human Shell v1 允许用户本人明确输入的 Direct Action 真实写回 Logseq：

```text
todo "..."
idea "..."
mini "..."
resource "..."
note 123 "..."
done 123
wait 123 "..."
result 123 "..."
noresult 123 "..."
```

这些操作不走 Proposal，因为它们已经是用户决策。Provider / Agent 输出仍然必须走 Proposal。

Human Shell 使用合适位置 resolver：

- `/today` 写入今日 journal，不存在则创建；
- `/inbox` 写入今日 journal，并带 inbox 语义；
- `/projects/<project>` 按类型优先写入 `[具体事务]`、`[想法]`、`[小任务]`、`[资源]`；
- `/projects/<project>/<node>` 写入当前项目节点；
- `/mini/<mini>` 写入 mini project block；
- 无法定位时 fallback 到 today inbox，并明确提示。

`wait` 优先把 Logseq task marker 改为 `WAITING`，等待原因作为 `**[注]**` 子块追加。

Direct Action 仍只允许 append-only 或 task marker 修改，不移动、删除、合并、重排项目页。每次直接写回都会记录内存 operation history，
并保存 backup 或 inverse 信息；`undo` 至少可撤销最近一次写回。

## Human Shell Inline Edit Writeback

`insert` 是用户本人在当前 focus 上发起的 Direct Action，但比 append-only 更敏感，因此保存前始终 preview：

```text
focus <id>
insert line
:save
```

写回边界：

- `line` 只替换目标 block 首行。
- `subtree` 只替换目标 block 的 source range。
- 保存时检查文件 hash；外部修改会触发 conflict，不强制覆盖。
- apply 前生成 diff、line count change、content-loss warning 和 rollback 提示。
- apply 后备份原文件，写回新内容，执行单文件 refresh，并记录 `undo` operation。

当前版本不做跨文件编辑、移动块、删除其他 subtree、合并块或重排项目页。若用户删除了 `id::` 等属性，preview 会暴露 diff，后续索引身份可能退回到 file + line 策略。

## Human Shell Preview And Undo List

Human Shell v1.5 在 Direct Action 前提供短预览：

```text
preview on
where todo "查询 Kakao T 支付支持"
todo "查询 Kakao T 支付支持" --preview
```

预览展示：

- graph；
- relative file；
- target context；
- operation；
- content；
- short diff。

`where` 和 `--preview` 不修改文件。`preview on` 后真实写回前需要确认。`preview off` 仅在目标明确时直接写；目标或位置模糊时仍会展示候选，不会静默 fallback 到错误位置。

Operation history 支持查看和指定撤销：

```text
history
history --detail
undo
undo 3
```

可撤销的 shell operation 包括 append TODO / idea / mini / resource、append note / ainote / result / noresult、task marker change，以及 shell 触发的 Proposal apply rollback。撤销后该 operation 标记为 `undone`，重复撤销会被拒绝。

连续多次写回同一文件时，每个 Direct Action 都保留自己的备份或 inverse 信息。撤销指定操作会恢复该操作记录中的文件快照；如果后续操作依赖前序内容，shell 会提示风险或失败原因，而不是假装成功。

## V1.5.1: `edit task` 写回边界

### `preview_modify_block_text` 保守规则

`edit task title` 和 `edit task content` 通过 `LogseqWriter.preview_modify_block_text()` 实现，遵循极度保守的修改策略：

1. **只修改目标 block 首行** — 通过 uuid（优先）或 line_start 精确定位
2. **保留缩进** — 完全保留原行前导空白
3. **保留 bullet** — 保留 `- ` 前缀
4. **保留 task marker** — `edit task title` 保留 TODO/DOING/DONE/WAITING marker；`edit task content` 本轮等价于 title，也保留 marker
5. **保留子块** — 子块、属性块完全不接触
6. **保留 block uuid** — `id::` 属性不修改

### 强制 preview

`edit task title` 和 `edit task content` **始终显示 preview 并要求确认**，不受 `preview on/off` 设置影响。这是因为修改块文本属于高风险操作。

### 安全保证

- 修改前显示 unified diff
- 修改前自动备份原文件
- 支持 undo 恢复
- 不移动、不删除、不重排、不破坏子块
- 修改后 resync 可识别新内容

### `edit task status`

`edit task <target> status <status>` 复用已有的 `preview_update_task_marker`，修改 TODO/DOING/DONE/WAITING marker，遵循已有的 preview/backup/undo 保护。

## Real Graph Fix: Lightweight Refresh

Human Shell Direct Action 不再默认调用全量 `sync_logseq()`：

```text
writeback apply
→ direct DB patch 当前 object status/title
→ single-file refresh 被修改文件
→ 用户需要时手动 tm sync logseq
```

`done` / `doing` / `wait` / `edit task status` 会立即更新当前 object 的 `status`；`edit task title` 会立即更新当前 object 的 `title`。新增 `todo` / `idea` / `mini` / `resource` 通过单文件 refresh 进入当前索引。

对象身份策略：

- 有 `id::` block property 时，使用 `block:<uuid>`。
- 无 uuid 时，使用 `block:<relative-file>:<line_start>`，不把 task marker 或标题 hash 放入 canonical id。
- ingest 时如果发现同一 file + line + object type 的旧对象，会更新原 object，而不是插入新 object。
- 历史重复对象不会被批量删除；`show` / `find` 会提示并优先展示 active/latest 结果。

preview 默认展示人类决策视图：file、line、operation、scope、undo、old/new 或 new child。raw unified diff 只在 `detail on` 或底层 Proposal preview 中展示。

撤销后 shell 会对恢复的文件执行单文件 refresh。若用户怀疑外部编辑导致全局索引过期，可运行：

```bash
tm sync logseq
```

## Readonly Evidence Boundary

本轮新增的 semantic node `show`、`tree raw` 和 `tm agent project-node <node-id> --raw --context`
都是只读证据视图，不触发写回。它们可以展示任意 project semantic node 的 raw subtree、ancestor context、
source location、node id 和 object id，但不会移动、删除、合并或重排 Logseq block。

Project Lifecycle 的完整闭环仍未实现。未来的 `project create`、`project capture`、`project inbox`、
`project clarify`、`project restructure` 和 phased apply 必须继续走 preview / proposal / accept / apply /
rollback 边界；Agent restructure pack 只能先产出证据和 proposal，不直接改真实 graph。

## Physical Migration Safety

真实 graph 物理迁移必须先备份整个 graph，并记录每个文件的 before/after hash、line count、bullet count、TODO count、link count 和 `id::` count。迁移允许标准化 section marker 和补缺失 section，但默认不删除、不合并、不移动原始子树。

如果迁移后需要回滚，使用报告目录中的 `rollback.sh`，它基于完整 graph 备份执行 `rsync` 恢复。
