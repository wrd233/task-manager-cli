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

## Security

默认 payload preview 会做 redaction。不要发送完整文件正文，不发送不必要的 linked
records。Provider request / response 在 Review item 中只保存摘要，不保存完整远端响应或
chain-of-thought。
