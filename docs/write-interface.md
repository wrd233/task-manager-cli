# Write Interface

写能力是受限能力，不是默认行为。设计目标是让 Agent 可以提出和执行低风险追加，而不是任意修改 Logseq。

## 模式

- `disabled`：默认值。不能创建写入提案，不能 apply。
- `proposal`：可以创建 proposal 和 preview diff，但不能写 Logseq。
- `guarded`：可以 apply allowlist 操作，默认必须传 `--yes`。
- `agent`：给自动化使用；仍然只允许 allowlist 操作。

设置：

```bash
tm config set-write-mode proposal
tm config set-write-mode guarded
tm config set-write-mode agent --no-confirm
tm config set-write-mode disabled
```

## 支持的操作

第一版只支持 append-only：

- `append_child_block`：给某个 block 追加子块。
- `append_page_section`：给页面中的某个 section marker 追加子块。
- `create_page`：创建新 Logseq page。

不支持删除、替换、移动、全文 patch 或自动重排。

## 命令

```bash
tm write append-child --object 12 "[Agent建议] 先补充验收标准"
tm write append-child --file /path/to/page.md --uuid 1111-... "[Agent批注] ..."
tm write append-section --object 34 --section "[反思]" "[Agent反思] 当前卡点是输入边界不清"
tm write create-page "Agent Inbox" "[Agent建议] 这里集中收纳待处理建议"
tm write list --status open
tm write preview 1
tm write preview 1 --format json
tm write preview 1 --no-redact
tm write apply 1 --yes
tm write reject 1
```

## 安全机制

每个 proposal 保存 operation type、目标对象、文件、block uuid、行号、内容、diff、创建时文件 sha256、作者和状态。

`tm write preview` 默认会对 diff 上下文脱敏；本地排查时可以显式使用 `--no-redact`。

apply 时会：

1. 检查 `write_mode` 是否是 `guarded` 或 `agent`。
2. 检查 proposal 是否仍然 `open`。
3. 重新解析目标 block 或 section。
4. 校验当前文件 sha256 是否等于 proposal 创建时的 hash。
5. 写前备份原文件。
6. append 新 block。
7. 标记 proposal 为 `applied`。

如果 proposal 创建后用户在 Logseq 里改了文件，apply 会拒绝，避免插入到过期上下文。
