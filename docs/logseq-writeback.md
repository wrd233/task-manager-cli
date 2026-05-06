# Logseq Writeback

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
