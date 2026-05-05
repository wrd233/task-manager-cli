# task-manager-cli 设计文档

版本：v0.1。

定位：本地行动对象索引器、上下文查询接口、Agent 批注存储层。

## 核心边界

系统只管理事实、对象、记录、位置、关系和批注。外部 Agent 可以调用 CLI 获取上下文并写入建议，但
CLI 本身不判断今天该做什么、不排序优先级、不自动修改 Logseq。

Logseq 是第一阶段主要来源。未来 Flomo、手动 inbox 或其他 Markdown/API 来源应通过 adapter 接入。

## 分层

- Core
Domain： `ActionObject` 、 `SourceRecord` 、 `Location` 、 `Relation` 、 `Annotation` 、
`ContextPackage` ，不依赖 Logseq。
- Adapter Layer：读取外部来源并输出标准候选数据。Logseq adapter 位于 `adapters/logseq/` 。
- Ingest / Merge：把候选数据幂等写入 SQLite，记录 sync run。
- Storage：SQLite schema、repository 和事务边界。
- Query / Context：对象列表、单对象 context、Agent JSON / Markdown。
- Annotation：批注只写内部数据库。
- CLI：命令入口，只做参数解析和 service 编排。

## 对象模型

`objects` 表保存 Project / Task / Idea 的统一抽象：

- `object_type` : `project` / `task` / `idea`
- `title`
- `status`
- `canonical_source`
- `source_item_id`
- `canonical_location_id`
- `confidence`
- `created_at`
- `created_at_source`
- `first_seen_at`
- `last_seen_at`
- `metadata_json`

`source_records` 保存原始片段。 `locations` 保存文件、页面、journal 日期、block uuid、行号和
block path。 `object_record_links` 表达对象和记录之间的 `definition` 、 `child_record` 、
`process_note` 、 `idea_note` 等关系。 `relations` 表达对象间 `belongs_to` 、 `references`
等关系。

## 身份策略

- Project：以 Logseq page identity 为主， `page:<relative-file-path>` 。
- Block object：有 `id::` 时使用 `block:<uuid>` 。
- 无 uuid block：使用 `block:<relative-file-path>:<line>:<content-hash>` 。
- 重复同步通过 SQLite unique key 幂等 upsert，不重复创建对象、记录或关系。
- 第一版不做激进语义合并，避免把不同事项错误合并。

## 创建时间策略

- Project：优先 `start::` ，否则文件 mtime。
- Journal 中 Task / Idea：使用 journal 文件名推断日期。
- 项目页中的 Task / Idea：没有显式时间时使用 `first_seen_at` 。
- 每个对象保留 `created_at_source` ，不假装所有对象都有真实创建时间。

## 安全和隐私

Agent context 默认启用脱敏。脱敏来源包括默认正则、用户配置正则、 `private:: true` 和 `[敏感]` /
`**[敏感]**` 标记。原始 Logseq 文件只读。

## Agent-oriented Context Views

除 full export 外，系统提供面向 Agent 的薄上下文视图：

- `today-context` ：最近 journal 暴露的任务、想法、活跃项目和活动性字段。
- `project-context` ：单项目诊断上下文、任务统计、relations、journal exposures 和事实性
  signals。
- `inbox-context` ：未关联 idea、可疑 idea 和候选关联。

这些视图只提供证据和信号，不做最终优先级判断。

## 受限写入能力

写入能力是配置 gated 的 append-only proposal/apply 机制。

模式：

- `disabled` ：默认，不写 Logseq。
- `proposal` ：只保存写入提案和 diff。
- `guarded` ：允许 apply，默认需要 `--yes` 。
- `agent` ：自动化模式，但仍受 allowlist 限制。

允许操作：

- append child block
- append page section
- create page

安全约束：

- 不删除、不替换、不移动。
- apply 前检查目标文件 sha256。
- 写前备份。
- proposal 状态持久化在 SQLite。
