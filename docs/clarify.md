# Clarify

Clarify
是做题式审核流程：用户主动选择一批候选条目，系统逐条展示摘要并提出基础问题，用户回答后交给
provider 生成 Proposal。Clarify 不直接改事实，也不直接写回 Logseq。

Clarify 复用 Review Session：

- Review Session 记录范围、候选 item、状态和事件。
- Review item 的 `metadata.clarify` 记录 questions、answers、skip reason、provider request /
response 摘要和 generated proposals。
- Provider 返回只会转换成 `suggested` Proposal。
- Proposal 仍需用户 `accept` / `reject` / `edit` ，写回仍需 preview / confirm / apply。

## Commands

```bash
tm clarify selected --ids 12 34 --answer "仍有价值，等待外部反馈" --provider mock
tm clarify inbox --limit 10 --answer "先沉淀 AI 注" --provider mock
tm clarify today --limit 10 --provider dry-run --answer "payload preview"
tm clarify project 项目-Alpha --limit 10 --answer "项目内澄清"
tm clarify resume 1 --answer "继续处理" --provider mock
tm clarify retry 1 --answer "修正配置后重试" --provider deepseek
tm clarify status 1
tm clarify eval 1
```

`selected` 是本轮的主入口。 `inbox` 、 `today` 、 `project`
是轻量候选选择器，不实现完整项目语义树。

## Questions

本轮固定基础问题：

- 这个条目现在还有价值吗？
- 它更像：行动 / 想法 / 资源 / 等待 / 未来可能 / 已完成 / 丢弃？
- 它是否属于某个项目？
- 它是否需要拆成小任务？
- 它是否需要等待别人或外部条件？
- 它完成后是否需要成果标注？
- 你希望如何处理它？

CLI 可以逐条 prompt，也可以用 `--answer` 非交互记录一条 freeform answer。 `--skip` 会把 item
标记为 `skipped` 并保留原因。

## Provider Flow

Clarify 构造脱敏 payload，只包含对象摘要、状态、位置摘要、基础问题、用户回答和安全约束。Provider
生成 proposal candidates 后，系统校验 schema 并创建 `suggested` Proposal。

真实 provider 流程建议：

```bash
tm clarify selected --ids 12 --answer "..." --provider dry-run --format json
tm clarify selected --ids 12 --answer "..." --provider deepseek --format markdown
tm clarify eval <review-id>
```

先看 payload preview，再做真实调用。真实调用不会自动 apply。

Payload 默认分层且克制：object id、title、current state、semantic markers / tags、source
type、page、journal date、line、short child notes、existing annotations summary、user answer 和
safety constraints。默认不发送完整文件正文、全量 Logseq 子树或大量 linked records。payload
超过限制会截断 notes / answer，并标出 `payload_truncated` 。

Review item clarify 状态包括：

- `pending`
- `asked`
- `answered`
- `submitted`
- `proposal_generated`
- `skipped`
- `failed`
- `done`

`resume` 会继续处理 pending / asked / answered / failed item。

## Suggestion Table

Clarify 结束后输出建议表：

| Proposal | Object | Current | Suggestion | Type | Risk | Confidence | Reason | Action |
|---|---|---|---|---|---|---|---|---|

操作仍通过 `tm proposal ...` 完成：

```bash
tm proposal accept 1
tm proposal show 1 --preview
tm proposal apply 1 --yes
tm proposal rollback 1
```

## Round 2 Boundary

本轮支持核心 Clarify 闭环、mock / dry-run provider、OpenAI-compatible remote provider
边界、payload preview、Proposal edit / supersede。

本轮不支持完整小任务系统、完整项目语义树、成果系统、复杂 TUI、文件系统
metadata、自动删除、自动合并或未经确认的写回。

Round 2.5 增加 provider doctor、真实 provider smoke test、retry failed、clarify eval、严格
response schema 和 payload size guard。
