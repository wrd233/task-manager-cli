# Providers

Provider 是 Clarify 的建议生成边界。它接收脱敏 payload，返回结构化 proposal candidates。Provider
不直接修改数据库事实，不直接写回 Logseq，不绕过 Proposal 审核。

## Built-in Providers

- `mock` ：本地规则 provider，用于测试和离线开发。
- `dry-run` ：只展示 payload preview，不发起远端请求，不生成 Proposal。
- `openai-compatible` / `deepseek` / `remote` ：OpenAI-compatible chat completions provider。
- `invalid-json` ：测试用 provider，用来验证失败路径。

## Configuration

配置可来自环境变量、 `.env.local` 、 `.env` 或用户本地 config。API key 不会写入 `config.json` 。

```bash
export TM_PROVIDER=deepseek
export TM_PROVIDER_BASE_URL=https://example.invalid/v1
export TM_PROVIDER_MODEL=provider-model-name
export TM_PROVIDER_API_KEY=sk-placeholder
```

也可以放在不提交的 `.env.local` ：

```text
TM_PROVIDER=deepseek
TM_PROVIDER_BASE_URL=https://example.invalid/v1
TM_PROVIDER_MODEL=provider-model-name
TM_PROVIDER_API_KEY=sk-placeholder
```

`.gitignore` 已忽略 `.env` 、 `.env.*` 、 `*.local` 和 `config.local.*` 。不要把真实 key 写入
README、测试或 tracked config。

## Doctor / Ping

```bash
tm provider doctor --no-call
tm provider doctor --provider deepseek
tm provider ping --provider deepseek
```

`--no-call` 只检查配置，不访问网络。doctor 输出 provider name、base URL、model、API key
是否存在、masked key、smoke test 状态、latency、token usage、payload hash 和 response id。完整
API key 不会输出。

## Dry Run

```bash
tm clarify selected --ids 12 --answer "先看 payload" --provider dry-run --format json
tm clarify selected --ids 12 --answer "先看 payload" --payload-preview --format json
```

dry-run 输出：

- provider 配置摘要；
- API key 是否存在和 masked 值；
- 将发送的字段；
- redacted payload；
- prompt version；
- 不发起真实请求。

## Response Schema

Provider 应返回 JSON object：

```json
{
  "summary": "short summary",
  "classification_suggestion": "action",
  "gtd_state_suggestion": "waiting",
  "project_suggestion": "Project name",
  "marker_suggestion": "**[AI注]**",
  "annotation_suggestion": "short annotation",
  "proposal_candidates": [
    {
      "proposal_type": "logseq_append_marker",
      "title": "Append AI note",
      "risk": "medium",
      "payload": {
        "marker": "**[AI注]**",
        "content": "clarified note"
      },
      "confidence": 0.8,
      "reasoning_summary": "short explanation"
    }
  ],
  "confidence": 0.8,
  "reasoning_summary": "brief summary only",
  "needs_user_confirmation": true
}
```

Provider response 不可信。系统会校验 JSON 和 candidate 结构；无效 JSON 会让 review item 进入
`failed` ，不会崩溃，也不会应用任何结果。

Round 2.5 使用 `clarify-v1` / `clarify_v1_zh` 风格的保守 Clarify prompt。目标是少量、高置信、
可审核建议，而不是自动管理任务。

Provider proposal candidate 白名单：

- `add_marker`
- `change_task_marker`
- `add_annotation`
- `change_state`
- `add_relation`
- `create_mini_project`
- `add_result_marker`
- `link_to_project`
- `link_to_project_node`
- `link_idea_to_project`
- `link_resource_to_project`
- `promote_to_mini_project`
- `attach_to_mini_project`

Risk 只能是 `low` 、 `medium` 、 `high` 。非法 type、risk、target 或 invalid JSON 会进入 parse
error。

## Round 3 Project Payload

Clarify 可以附带简短 project tree context：

```bash
tm clarify selected --ids 12 --project 项目-韩国旅行 --provider dry-run
tm clarify project 项目-韩国旅行 --limit 10 --provider mock
```

payload 只包含 project metadata、少量 node summary、node id、node type、title、depth 和 line summary。
默认不发送完整项目页原文，不发送全量 linked records。

Provider 可以建议项目纳管或小任务升级：

```json
{
  "summary": "project membership",
  "proposal_candidates": [
    {
      "type": "link_to_project_node",
      "risk": "low",
      "target": {
        "object_id": "12",
        "project_id": 3,
        "project_node_id": "block:node"
      },
      "content": "挂到出行交通工作流",
      "confidence": 0.8,
      "reason": "条目明确引用项目并匹配节点",
      "needs_user_confirmation": true
    }
  ]
}
```

Provider 不能建议移动、删除、合并、大规模重排或重写项目页。若不确定，应返回
`questions_for_user`，而不是强行生成 Proposal。

Round 3.5 加强项目纳管边界：项目纳管候选的 confidence 低于 0.6 时不会创建 Proposal，只保留在质量报告或后续澄清里。
Resource / Reference 不应返回 Action 类建议，Idea 不应被强制转换成 Task。

## Errors / Retry

Provider 失败会写入 review item clarify metadata。覆盖 timeout、network error、401 / 403 / 429 /
5xx、invalid JSON、schema mismatch、empty response、partial response。

```bash
tm clarify retry <review-id> --answer "修正后重试" --provider mock
tm clarify resume <review-id> --answer "继续" --provider deepseek
```

retry 不会重复处理已经 `proposal_generated` 的 item。

## Quality Eval

```bash
tm clarify eval <review-id>
tm clarify eval <review-id> --format json
```

指标包括 success / failed / parse error、proposal type distribution、risk distribution、average
confidence、high risk count、latency、redaction status 和 suspicious suggestions。

## Security

默认 payload preview 会做 redaction。不要发送完整文件正文，不发送不必要的 linked
records。Provider request / response 在 Review item 中只保存摘要，不保存完整远端响应或
chain-of-thought。
