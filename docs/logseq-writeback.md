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

## Round 3 Project Writeback

项目树默认只读。项目纳管 Proposal 默认只写内部 relation，不移动原始 Logseq 块。

Round 3 允许的项目相关写回仍然是 append-only：

- 在目标节点下追加 block ref。
- 追加 `**[AI注]**`。
- 追加 `**[待澄清]**`。
- 追加最小 `**[小任务]**` 节点。
- 追加 `**[资源]**` 引用。

仍然禁止移动、删除、合并、重排项目页、大规模项目树重写或自动改标题。Provider 不能直接写回项目树。
