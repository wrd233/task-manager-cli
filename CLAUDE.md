# CLAUDE.md

## 项目身份

本仓库是 `task-manager-cli`。

它是一个本地行动对象索引器和上下文接口，用来从 Logseq 等本地数据源中抽取并维护：

- Project
- Task
- Idea
- SourceRecord
- Location
- Relation
- Annotation

`task-manager-cli` 不是普通 todo app，不是优先级决策器，也不是自动计划系统。

必须始终记住：

- `task-manager-cli` 不是优先级决策器。
- CLI 提供事实和上下文，Agent 负责解释和建议。
- Agent annotation 写入 tm 内部数据库，不写回 Logseq。
- 默认不修改 Logseq。
- 优先使用 `tm agent ...`，不要直接读取全量 dump。

## 核心边界

Logseq、Flomo 等来源是原始记录来源。`task-manager-cli` 内部 SQLite 数据库是对象索引、关系层、上下文层和批注层。

本项目自身不负责判断：

- 今天该做什么
- 哪些任务优先级最高
- 某个项目是否一定卡住
- 某个想法是否一定应转成项目

这些是外部 Agent 的职责。CLI 的职责是提供可追溯证据、上下文包、关系与批注存储。

默认情况下：

- Logseq 只读
- Annotation 只写入 `task-manager-cli` 内部数据库
- 不自动执行任何 Logseq 写入命令
- 不默认使用 `--no-redact`

除非用户明确要求并确认风险，否则不要执行：

- `tm sync logseq`
- `tm annotation add ...`
- `tm annotation status ...`
- `tm write *`
- 任何 `--no-redact`

## 第一性原则

系统存在的目的，是帮助用户和外部 Agent 基于本地真实记录回答以下问题：

1. 当前有哪些项目、事务和想法？
2. 这些对象来自哪里？
3. 每个对象有哪些关联记录、子记录和最近暴露？
4. 最近有哪些活动、未完成事项和自由想法？
5. Agent 或人曾对哪些对象加过批注？
6. 推理前最值得读取的上下文是什么？

分工必须清晰：

- CLI 提供事实、对象、记录、位置、关系、信号
- Agent 提供解释、判断、建议
- 用户负责最终确认与执行

## 架构分层

请尊重当前代码结构：

- `src/task_manager_cli/core/`
  - 通用领域模型、枚举、错误定义
- `src/task_manager_cli/adapters/`
  - 外部来源适配器；当前以 Logseq 为主
- `src/task_manager_cli/ingest/`
  - 候选数据到 SQLite 的幂等合并
- `src/task_manager_cli/storage/`
  - 数据库 schema、连接、repository
- `src/task_manager_cli/query/`
  - 查询服务、Agent views、导出
- `src/task_manager_cli/annotations/`
  - annotation 新增、查询、状态更新
- `src/task_manager_cli/privacy/`
  - 默认脱敏与敏感规则
- `src/task_manager_cli/writes/`
  - 受限写入提案与 apply 逻辑
- `src/task_manager_cli/cli/`
  - 命令入口与参数编排

约束：

- 不要把 Logseq 专用解析逻辑放进 `core/`
- 不要让 `query/` 直接解析 Logseq 原始文件
- 不要让 adapter 替 Agent 做优先级判断
- 不要让 annotation 伪装成原始记录

## Logseq Adapter 规则

Logseq adapter 负责解析：

- Markdown block tree
- page properties
- journal date
- TODO / DOING / DONE
- `((uuid))`
- `{{embed ((uuid))}}`
- idea markers

关于 Logseq idea 抽取，必须遵守以下高置信规则：

高置信 idea 只包括：

- `**[想法]** xxx`
- `[想法] xxx`
- `**[随想]** xxx`
- `[随想] xxx`

不要把以下内容抽成 idea：

- `[[想法]]`
- `[[随想]]`
- 普通句子里的“想法”
- 无 marker 的 Readwise highlight
- `] xxx` 形式的 idea 残片
- 空标题、纯符号、纯 wiki link 残片

结构性 `{{embed ((uuid))}}` 模板复用不要当成语义任务关系。journal 中纯 block ref 应作为 `journal_exposure` 处理，不复制出新 task。

## Source / Location 不变量

每个抽取出的 ActionObject 都应该有 definition SourceRecord，除非它是未来显式人工创建的对象。

必须保持：

- object canonical location 与 definition SourceRecord location 一致
- `SourceRecord.location_id` 指向真实 Location
- related records 使用明确 role 区分
- 不把任意 related record 错当成 definition

常见 role 包括：

- `definition`
- `child_record`
- `process_note`
- `journal_exposure`
- `idea_note`
- `resource`
- `reflection`
- `reference`

如出现 definition 缺失或 source/location mismatch，应优先用 `tm report extraction-quality` 和测试排查，而不是在 Agent 层“猜正确答案”。

## Agent Context 使用规则

用户询问以下问题时，优先使用 `tm agent ...`：

- 今天做什么
- 哪些任务值得先看
- 某个项目是否卡住
- 某个项目当前进展如何
- 最近有哪些想法值得处理

推荐读取顺序：

1. `tm agent today-context --days 14 --format json`
2. `tm agent project-context "<项目名或对象 id>" --format json`
3. `tm agent inbox-context --days 30 --format json`
4. `tm report active-projects --format json`
5. `tm report recent-unresolved-tasks --days 14 --format json`

不要把日常 Agent 分析建立在全量 dump 之上。只有在抽取质量调试、回归排查或深度审计时，才考虑更重的导出和 debug 命令。

回答时请区分四类内容：

- CLI 事实
- Agent 解释
- Agent 建议
- 需要用户确认的事项

## Annotation 规则

Agent 批注和建议必须写入 `task-manager-cli` 内部 annotation 数据，不写回 Logseq。

对象级 annotation：

```bash
tm annotation add <object-id> "判断 + 依据 + 建议下一步 + 置信度" --author claude --type suggestion
tm annotation list --object <object-id> --format json
tm annotation status <annotation-id> accepted
```

record 级 annotation：

```bash
tm annotation add --record <record-id> "判断 + 依据 + 建议下一步 + 置信度" --author claude --type comment
tm annotation list --record <record-id> --format json
```

批注内容应尽量包含：

- 判断
- 依据
- 建议下一步
- 不确定性或置信度

没有用户明确授权时，不要自动写入 annotation。

## 隐私与安全

默认启用 redaction。除非用户明确要求并理解风险，否则不要使用 `--no-redact`。

不要读取或输出以下敏感信息：

- `.env`
- `secrets/`
- `*secret*`
- `*token*`
- `*credential*`
- `*key*`
- cookie、session、password、API key

不要执行破坏性命令，例如：

- `rm -rf`
- `git push`
- 任意未审查的批量写入

不要默认执行任何 Logseq 写回命令，包括：

- `tm write apply`
- `tm write append-child`
- `tm write append-section`
- `tm write create-page`

## 常用命令

如果 `tm` 尚未安装，可优先使用：

```bash
PYTHONPATH=src python3 -m task_manager_cli.cli.main --help
```

常用只读命令：

```bash
tm doctor
tm sync status
tm sync runs
tm sync logseq --dry-run --recent-journals 30
tm report active-projects --format json
tm report recent-unresolved-tasks --days 14 --format json
tm report extraction-quality --format json
tm agent today-context --days 14 --format json
tm agent project-context "项目-韩国旅行" --format json
tm agent inbox-context --days 30 --format json
tm annotation list --object 12 --format json
tm annotation list --record 34 --format json
```

调试和开发时常用：

```bash
python3 -m pytest
python3 -m compileall -q src
tm debug parse-file /path/to/file.md
tm debug stats
git status
git diff
```

## 开发工作流

当任务是修复代码、测试或文档时，推荐流程：

1. 先复现问题或确认现状
2. 为 bug 或回归补测试
3. 做最小安全修复
4. 跑 `python3 -m pytest`
5. 跑 `python3 -m compileall -q src`
6. 如行为变化涉及用户使用方式，更新文档

额外约束：

- 禁止为了通过测试而削弱 redaction
- 禁止为了“方便 Agent”而放宽 Logseq 写入边界
- 禁止把 annotation 设计成写回 Logseq
- 禁止把优先级判断硬编码进 CLI

## Claude Code 使用建议

本项目中，Claude Code 默认应扮演三种角色：

- `task-manager-cli` 的使用者
- 行动上下文分析者
- 抽取质量诊断者

只有在用户明确要求修复代码、补测试、改文档时，才切换到开发者角色。
