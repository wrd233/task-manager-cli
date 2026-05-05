# Architecture

`task-manager-cli` 是本地行动对象索引器和上下文接口，不是 todo app，也不是优先级决策器。

## Layers

- Core： `ActionObject` 、 `SourceRecord` 、 `Location` 、 `Relation` 、 `Annotation`
等通用模型。
- Adapter：读取外部来源，输出标准候选数据。Logseq 只是第一个 adapter，不是核心模型。
- Ingest / Merge：把候选对象、记录、位置、关系幂等写入 SQLite。
- Storage：SQLite schema、repository、sync run 和 proposal 状态。
- Query / Context：对象查询、Agent context、抽取质量报告、脱敏。
- View：人类可读短视图，复用 Query / AgentView 的底层查询，不复制抽取逻辑。
- CLI：参数解析和 service 编排，不堆业务逻辑。

## Boundaries

- Core 不依赖 Logseq。
- Adapter 不直接做最终优先级判断。
- Query 不直接扫描 Logseq 原文件。
- Annotation 写 CLI 内部数据库，不写回 Logseq。
- 写入 Logseq 默认禁用；开启后也只允许受限 append-only proposal/apply。
- `tm view ...` 只读，不写 annotation，不写 Logseq，不做最终优先级判断。

## Object Invariants

- 每个抽取出的 ActionObject 必须有 `definition` SourceRecord。
- object canonical location 必须来自 definition SourceRecord location。
- related records 必须使用 role 区分，不能冒充 definition。
- source/location mismatch 会进入 `tm report extraction-quality` 。
