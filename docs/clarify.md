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
是轻量候选选择器。Round 3 中 `project` 会使用 readonly project tree summary，但仍不实现完整项目树重构。

Round 3 还支持给 selected clarify 传入项目上下文：

```bash
tm clarify selected --ids 12 --project 项目-韩国旅行 --answer "属于这个项目" --provider mock
```

payload 中只包含简短 project tree summary，不发送完整项目页原文。

## Questions

本轮固定基础问题：

- 这个条目现在还有价值吗？
- 它更像：行动 / 想法 / 资源 / 等待 / 未来可能 / 已完成 / 丢弃？
- 它是否属于某个项目？
- 它是否需要拆成小任务？
- 它是否需要等待别人或外部条件？
- 它完成后是否需要成果标注？
- 你希望如何处理它？
- 如果它属于项目，更像挂在哪个工作流 / 小任务 / 具体事务下？
- 它是否只是资源，而不是行动？

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

## Project Membership

Clarify 可以生成项目纳管相关 Proposal：

- `link_to_project`
- `link_to_project_node`
- `link_idea_to_project`
- `link_resource_to_project`
- `promote_to_mini_project`
- `attach_to_mini_project`

这些建议仍然只是 `suggested` Proposal。Provider 不会直接创建 relation，不会移动 Logseq 块，也不会重写项目树。

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

Round 3 增加 project context、project membership proposals 和 `promote_to_mini_project` 建议，但仍不做完整小任务系统、
完整项目树写回或复杂 TUI。

## Round 3.5 Project Validation

`tm clarify project <project>` 在大样本临时 graph 上用于验证项目上下文 payload 和 provider 纳管建议质量。

项目 payload 默认只发送短 project tree summary：

- project id / title / source；
- node id；
- node type；
- title 摘要；
- depth；
- line_start；
- truncated 标记。

默认不发送完整项目页原文、整页 Markdown、全量 linked records 或大段子树正文。payload 超过限制时会截断 child notes / answer，并设置 `payload_truncated`。

Provider 项目纳管建议限制：

- provider 只能生成 `suggested` Proposal；
- 低于 0.6 confidence 的项目纳管候选不直接创建 Proposal；
- Resource / Reference 不应建议为 Action；
- Idea 不应被强制转为 Task；
- 高风险项目树重写、删除、合并、移动和批量重排只允许作为高风险边界被识别，不会自动 apply；
- 真实 provider 应先用 `dry-run` 查看 payload，再少量验证。

质量检查：

```bash
tm clarify project <project> --provider dry-run --format json
tm clarify project <project> --provider mock
tm clarify eval <review-id>
```

## Human Shell Clarify

Human Shell v1 在当前上下文中提供逐条问答：

```text
tm shell
cd /inbox
clarify
```

候选来自当前路径，例如 `/today`、`/inbox`、project、project node、mini 或 ideas。Shell 每次展示一个对象，
逐条提出基础问题，并把每个回答写入 Review Session。

交互中支持：

- `skip` ：跳过当前 item；
- `quit` ：暂停 review；
- `show` ：查看当前对象摘要后继续回答。

Provider 设置在 shell 内完成：

```text
provider off
provider dry-run
provider mock
provider deepseek
```

`provider off` 只记录问题和回答；`dry-run` 只展示 payload preview；`mock` / 真实 provider 仍只能生成 suggested Proposal。
Human Shell 不允许 Provider 直接写 Logseq 或直接 apply。
