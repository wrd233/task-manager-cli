# Agent Interface

Agent 通过 CLI 读取上下文并写入批注。CLI 不输出优先级结论，只提供事实。

## 读取上下文

```bash
tm agent context --type project --limit 10 --format json
tm agent task 12 --format json
tm context 12 --format json
tm agent today-context --days 14 --format json
tm agent project-context 项目-韩国旅行 --format markdown
tm agent project-pack 项目-韩国旅行 --format json
tm agent project-restructure-pack 项目-韩国旅行 --format json
tm agent inbox-context --days 30 --format json
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

- `objects` : 对象元信息和原始位置。
- `records` : definition、child records、process notes、idea notes。
- `relations` : belongs_to / references 等对象关系。
- `annotations` : 当前对象已有批注。
- `truncation` : 输出截断策略。
- `redaction` : 脱敏是否启用和数量。

## Agent Views

`today-context` 面向“今天该看什么”的外部 Agent，提供最近 journal 中出现的
task/idea、近期未完成任务、活跃项目、活动字段和 annotations。CLI 不输出最终优先级结论。

`project-context <project>`
面向项目诊断，包含项目元信息、任务统计、未完成任务、最近完成任务、最近 idea、relations、journal
exposures 和事实性 signals。

`inbox-context` 面向想法 inbox，包含无 project/task relation 的 idea、可能关联候选和 suspicious
ideas。

Human-facing `tm view ...` 是另一层：它不面向 Agent，不输出 JSON，不展开完整 evidence。Agent
应继续使用 `tm agent ...` 或 `tm report ...` 。

通用选项：

```bash
--format json|markdown
--limit 50
--include-annotations / --no-annotations
--redact / --no-redact
```

默认启用 redaction 和 annotations。

新增只读 project node evidence：

```bash
tm agent project-node <node-id> --raw --context
tm agent project-node <node-id> --format json
```

该命令输出 node metadata、ancestor context、raw subtree、source location 和 project id/name，不写回
Logseq。`tm agent today-context` 表示今日事实；`tm agent dashboard-context` 预留为全局态势接口。

Project Lifecycle Agent Pack：

```bash
tm agent project-pack <project> --format json|markdown
tm agent project-restructure-pack <project> --format json|markdown
```

`project-pack` 包含 project metadata、semantic tree、project inbox、unplaced objects、tasks、ideas、resources、results、mini projects、recent records、project health、constraints 和 available operations。

`project-restructure-pack` 包含 semantic tree、unplaced objects、project health、node summaries、raw evidence references、proposal schema、allowed proposal types、forbidden operations 和 expected output schema。默认不会输出完整项目页原文；Agent 如需证据，应调用 `tm agent project-node <node-id> --project <project>`。

Project restructure output 必须是 JSON object：

```json
{
  "summary": "",
  "questions_for_user": [],
  "proposed_nodes": [],
  "object_mappings": [],
  "proposal_candidates": [],
  "risks": [],
  "unplaced_remaining": []
}
```

使用：

```bash
tm project restructure <project> --from-agent-output output.json
```

该命令只生成 Proposal，不 apply。

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

Agent 不应直接任意修改 Logseq。第一版仅允许 append-only：追加子块、追加到 page section、创建新
page。

Lifecycle Proposal 类型包括 `create_project`、`create_project_node`、`link_object_to_node`、`append_block_ref_to_node`、`promote_to_mini_project`、`convert_idea_to_task`、`mark_object_as_resource`、`mark_object_as_result`、`archive_project_item`。其中安全 apply 当前只覆盖 append-only / internal-only 类型；`move_original_block`、`delete_block`、`merge_blocks`、`mass_reorder` 禁止直接 apply。

## 隐私默认值

Agent context 默认脱敏。需要本地人工排查时可加 `--no-redact` ，但不建议给外部模型使用。
