# Agent Interface

Agent 通过 CLI 读取上下文并写入批注。CLI 不输出优先级结论，只提供事实。

## 读取上下文

```bash
tm agent context --type project --limit 10 --format json
tm agent task 12 --format json
tm context 12 --format json
```

`agent context` JSON 顶层结构：

```json
{
  "query": {"object_type": "project", "limit": 10},
  "packages": [
    {
      "query": {"object_id": 12, "record_limit": 20},
      "objects": [],
      "records": [],
      "relations": [],
      "annotations": [],
      "truncation": {},
      "redaction": {}
    }
  ],
  "redaction": {"enabled": true},
  "truncation": {}
}
```

单对象 context 包含：

- `objects`: 对象元信息和原始位置。
- `records`: definition、child records、process notes、idea notes。
- `relations`: belongs_to / references 等对象关系。
- `annotations`: 当前对象已有批注。
- `truncation`: 输出截断策略。
- `redaction`: 脱敏是否启用和数量。

## 写入批注

```bash
tm annotation add 12 "建议先澄清输入边界" --author agent --type suggestion
tm annotation list --object 12 --format json
tm annotation status 1 accepted
```

支持状态：

- `open`
- `accepted`
- `rejected`
- `archived`

支持类型建议：

- `comment`
- `suggestion`
- `risk`
- `summary`
- `critique`
- `decision`

批注只写入 SQLite，不写回 Logseq。

## 写入提案

当配置允许时，Agent 可以生成受限写入提案：

```bash
tm config set-write-mode proposal
tm write append-child --object 12 "[Agent建议] 先确认输入边界"
tm write preview 1
```

真正 apply 需要 `guarded` 或 `agent` 模式：

```bash
tm config set-write-mode guarded
tm write apply 1 --yes
```

Agent 不应直接任意修改 Logseq。第一版仅允许 append-only：追加子块、追加到 page section、创建新 page。

## 隐私默认值

Agent context 默认脱敏。需要本地人工排查时可加 `--no-redact`，但不建议给外部模型使用。
