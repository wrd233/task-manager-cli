# task-manager-cli

本项目是一个“本地行动对象索引器 + 上下文查询接口 + Agent 批注存储层”。它从 Logseq 等本地记录系统中只读抽取 Project / Task / Idea / Record / Location / Relation，并把 Agent 或人的批注写入自己的 SQLite 数据库。

它不是普通 TODO 工具：CLI 不判断今天该做什么，不做最终优先级排序，也不自动修改 Logseq。

## 安装

```bash
python3 -m pip install -e .
```

开发和测试：

```bash
python3 -m pip install -e ".[dev]"
python3 -m pytest
```

也可以不安装，直接用：

```bash
PYTHONPATH=src python3 -m task_manager_cli.cli.main --help
```

## 初始化

```bash
tm config init --graph /Users/wangrundong/logseq/Logseq_File
tm doctor
```

配置默认写入 `~/.task-manager-cli/config.json`，数据库默认写入 `~/.task-manager-cli/task_manager.sqlite3`。也可以用环境变量覆盖：

- `TM_APP_DIR`
- `TM_LOGSEQ_GRAPH`
- `TM_DATABASE_PATH`

## 常用命令

同步 Logseq：

```bash
tm sync logseq
tm sync logseq --dry-run --recent-journals 30
tm sync runs
tm sync status
```

查询对象：

```bash
tm list projects
tm list tasks --status todo
tm list ideas --format json
tm show 12
tm context 12 --format markdown
```

Agent 上下文：

```bash
tm agent context --type project --limit 10 --format json
tm agent task 12 --format json
tm agent ideas --limit 20 --format markdown
```

批注只写入 CLI 内部数据库：

```bash
tm annotation add 12 "这个任务需要先确认输入边界" --author agent --type suggestion
tm annotation list --object 12
tm annotation status 1 accepted
```

Debug：

```bash
tm debug parse-file /path/to/graph/pages/项目-Alpha.md
tm debug block 11111111-1111-1111-1111-111111111111
tm debug refs 11111111-1111-1111-1111-111111111111
tm debug stats
```

受限写入：

```bash
tm config set-write-mode proposal
tm write append-child --object 12 "[Agent建议] 先确认输入边界"
tm write preview 1
tm config set-write-mode guarded
tm write apply 1 --yes
```

`proposal` 只生成提案和 diff，不修改 Logseq。`guarded` 才允许 apply，默认需要 `--yes`，写前会检查文件 hash 并备份原文件。第一版只支持 append-only：

```bash
tm write append-child --object 12 "[Agent批注] ..."
tm write append-section --object 34 --section "[反思]" "[Agent反思] ..."
tm write create-page "Agent Inbox" "[Agent建议] ..."
tm write list --status open
tm write preview 1 --no-redact
tm write reject 1
```

## 目录结构

- `src/task_manager_cli/core/`：与数据源无关的领域模型和枚举。
- `src/task_manager_cli/adapters/`：Logseq / Flomo 等外部来源适配器，只输出候选数据。
- `src/task_manager_cli/ingest/`：候选数据到 SQLite 的幂等合并。
- `src/task_manager_cli/storage/`：SQLite schema、连接和 repository。
- `src/task_manager_cli/query/`：对象查询、context package、Agent context。
- `src/task_manager_cli/annotations/`：批注新增、查询、状态更新。
- `src/task_manager_cli/privacy/`：默认脱敏和用户敏感规则。
- `src/task_manager_cli/cli/`：命令入口，只做参数编排。
- `tests/fixtures/logseq_graph/`：稳定 Logseq fixture。

## 当前限制

- 第一版使用保守身份策略：Logseq block 有 `id::` 时以 uuid 为强身份，否则以文件、行号和文本 hash 为弱身份。
- 不做跨来源语义去重，也不判断任务优先级。
- 默认不写 Logseq；开启写模式后也只支持 append-only proposal/apply。
- Flomo adapter 只有边界文档，尚未接入真实 API 或导出格式。
