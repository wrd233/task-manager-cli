# task-manager-cli

本项目是一个“本地行动对象索引器 + 上下文查询接口 + Agent 批注 / Proposal 存储层”。它从 Logseq 等本地记录系统中抽取 Project / Action Item / Task / Idea / Record / Location / Relation，并把 Agent 或人的批注写入自己的 SQLite 数据库。

它不是普通 TODO 工具：CLI 不判断今天该做什么，不做最终优先级排序，也不自动修改 Logseq。
外部 Agent 负责基于 CLI 输出做判断；Agent 的批注和建议默认写入 CLI 内部 SQLite，不写回 Logseq。第 1 轮新增的是 Proposal / Review Session / 沙箱 Logseq 写回基础闭环，不是完整 Clarify、远端 API、小任务系统或项目语义树。

## Round 1 新增能力

- 通用 Proposal：`suggested -> accepted -> applied -> rolled_back` 的基础生命周期，支持风险分级和事件历史。
- Review Session：记录一次 inbox / today / selected 审核范围、候选对象、关联 proposals 和状态变化。
- Logseq 写回安全骨架：由 Proposal 驱动，支持 preview / diff / apply / backup / rollback，先面向测试 graph。
- 语义标记识别：`**[想法]**`、`**[待澄清]**`、`**[注]**`、`**[AI注]**`、`**[成果]**`、`**[无成果]**`，以及 `#inbox` / `#someday` / `#waiting` / `#reference`。
- Provider 边界：本轮只有 rule-based/mock provider，不接真实远端 API。

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

人类短视图：

```bash
tm view today
tm view projects --limit 20
tm view project 项目-韩国旅行 --detail
tm view tasks --brief
tm view ideas
tm view inbox
```

`view` 面向人快速扫一眼，默认短输出，不展示 JSON、metadata、confidence 或完整 linked records。需要完整上下文时再用 `tm show <id>` / `tm context <id>`。

Agent 上下文：

```bash
tm agent context --type project --limit 10 --format json
tm agent today-context --days 14 --format markdown
tm agent today-context --days 14 --format json
tm agent project-context 项目-韩国旅行 --format markdown
tm agent inbox-context --days 30 --format json
tm agent task 12 --format json
tm agent ideas --limit 20 --format markdown
```

轻量报告：

```bash
tm report active-projects
tm report recent-unresolved-tasks --days 14
tm report extraction-quality
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

结构化 Proposal：

```bash
tm proposal create-annotation --object 12 "这个任务需要先确认输入边界"
tm proposal create-marker AI注 "建议先做最小验证" --object 12
tm proposal create-task-marker WAITING --object 12
tm proposal list
tm proposal show 1 --preview
tm proposal accept 1
tm proposal apply 1 --yes
tm proposal rollback 1
```

Review Session：

```bash
tm review start --type inbox
tm review start --type selected --ids 12 34
tm review list
tm review show 1
tm review proposals 1
tm review status 1 paused
tm review close 1
```

API key 不要写入仓库。本轮不需要真实 API key；下一轮接远端 provider 时应使用环境变量、`.env.local` 或用户本地配置，并确保不提交。

Logseq 写回请先只在临时测试 graph 中使用。真实 graph 写回必须先看 `tm proposal show <id> --preview` 的 diff，再显式 accept/apply。

## 目录结构

- `src/task_manager_cli/core/`：与数据源无关的领域模型和枚举。
- `src/task_manager_cli/adapters/`：Logseq / Flomo 等外部来源适配器，只输出候选数据。
- `src/task_manager_cli/ingest/`：候选数据到 SQLite 的幂等合并。
- `src/task_manager_cli/storage/`：SQLite schema、连接和 repository。
- `src/task_manager_cli/query/`：对象查询、context package、Agent context。
- `src/task_manager_cli/query/human_views.py`：人类可读短视图，复用 query / agent view 底层能力。
- `src/task_manager_cli/annotations/`：批注新增、查询、状态更新。
- `src/task_manager_cli/proposals/`：结构化 Proposal 生命周期、风险、apply / rollback。
- `src/task_manager_cli/reviews/`：Review Session 创建、状态和 proposal 关联。
- `src/task_manager_cli/providers/`：下一轮远端 API / 本地规则 provider 边界。
- `src/task_manager_cli/privacy/`：默认脱敏和用户敏感规则。
- `src/task_manager_cli/cli/`：命令入口，只做参数编排。
- `tests/fixtures/logseq_graph/`：稳定 Logseq fixture。

## 当前限制

- 第一版使用保守身份策略：Logseq block 有 `id::` 时以 uuid 为强身份，否则以文件、行号和文本 hash 为弱身份。
- 不做跨来源语义去重，也不判断任务优先级。
- 默认不写 Logseq；开启写模式后也只支持 append-only proposal/apply。
- Flomo adapter 只有边界文档，尚未接入真实 API 或导出格式。
- 第 1 轮不实现完整 Clarify、小任务系统、项目语义树、Anki、远端 API 或复杂 TUI。

## 文档

- `docs/proposals.md`
- `docs/review-sessions.md`
- `docs/logseq-writeback.md`
- `docs/semantic-markers.md`

## Claude Code

项目级 Claude Code 使用说明见：

- `CLAUDE.md`
- `docs/claude-code-usage.md`
