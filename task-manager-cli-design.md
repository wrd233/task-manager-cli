# task-manager-cli 设计文档

> 版本：v0.1  
> 定位：本地行动对象索引器 + 上下文查询接口 + Agent 批注存储层  
> 主要数据源：Logseq；后续扩展 Flomo、手动 inbox、其他 Markdown / API 来源

---

## 1. 项目定位

`task-manager-cli` 不是一个传统 TODO 工具，也不是一个 AI 自动规划器。它的目标是：

> 从用户已经存在的本地记录系统中，提炼出抽象的 Project、Task、Idea 等行动对象，并维护这些对象与原始记录、位置、关系、Agent 批注之间的连接；通过 CLI 向人和外部 Agent 提供稳定、可追溯、可过滤的上下文接口。

它的核心职责是：

1. 从 Logseq、Flomo 等来源读取原始记录。
2. 抽取 Project / Task / Idea 等行动对象。
3. 保留每个对象的来源位置、上下文记录、父子层级、引用关系。
4. 在内部存储 Agent 对项目、事务、想法的批注和建议。
5. 向外部 Agent 输出结构化上下文包，让 Agent 判断“今天该做什么”“项目是否卡住”“优先级如何”。

它不负责：

1. 替用户自动决定优先级。
2. 替用户判断今天必须做什么。
3. 默认修改 Logseq 原始文件。
4. 自动把想法转成任务。
5. 自动重组用户的项目结构。

一句话：

> `task-manager-cli` 管“事实、对象、记录、位置、关系、上下文”；外部 Agent 管“理解、分析、判断、建议”。

---

## 2. 设计原则

### 2.1 原始数据源优先

Logseq、Flomo 等来源是原始事实来源。`task-manager-cli` 内部数据库是索引、缓存、关系层和批注层，不应擅自取代原始数据源。

尤其是 Logseq：

- Logseq 继续作为主要工作现场。
- 用户仍然在 Logseq Daily Log、项目页、块下面自然记录。
- CLI 负责读取、索引、查询和导出，而不是要求用户改用另一套任务系统。

### 2.2 对象抽象优先，而不是 Logseq 结构优先

系统核心不应直接围绕 Logseq Page / Block / Journal 建模。Logseq 只是一个适配器。核心层应该围绕通用行动对象建模：

- Project：项目。
- Task：事务 / 任务 / 行动项。
- Idea：想法 / 灵感 / 未成熟行动线索。
- Record：原始记录片段。
- Location：原始位置。
- Relation：对象之间或对象与记录之间的关系。
- Annotation：Agent 或人对对象的批注和建议。

### 2.3 强溯源

每一个 ActionObject 都必须尽可能回答：

- 它来自哪个数据源？
- 它的原始位置在哪里？
- 它对应哪个页面、文件、块、memo？
- 它下面有哪些记录？
- 它最近在哪里被提到？
- 它和哪些项目、事务、想法有关？

Agent 输出上下文时，不能只给标题，必须给来源位置和证据记录。

### 2.4 轻判断，重证据

CLI 可以提供事实性信号，例如：

- 对象创建或首次发现时间。
- 最近活跃时间。
- 出现次数。
- 是否处于 TODO / DOING / DONE。
- 是否有子块过程记录。
- 是否最近被 journal 引用。
- 是否有未处理 Agent 批注。

CLI 不应该自行给出最终判断，例如：

- 今天必须做这个。
- 这个项目优先级最高。
- 这个想法应该变成项目。
- 这个任务应该拆分。

这些应交给外部 Agent 或用户判断。

### 2.5 只读优先，写入分层

默认情况下：

- 对 Logseq：只读。
- 对 Flomo：只读或导入式读取。
- 对 CLI 内部数据库：可写，用于索引、关系、批注、同步状态。

Agent 的批注和建议写入 CLI 内部数据库，而不是写回 Logseq。

后续如果支持回写 Logseq，必须是显式、可预览、可确认的操作，不属于第一阶段核心目标。

### 2.6 适配器隔离

Logseq 兼容能力必须放在 adapter 中，不能污染核心领域模型。未来新增 Flomo adapter 时，不应重写核心查询、批注和 Agent 上下文生成逻辑。

---

## 3. 系统边界

### 3.1 核心层负责

- 存储 ActionObject、SourceRecord、Location、Relation、Annotation。
- 管理对象与记录的关联。
- 管理对象之间的关系。
- 管理 Agent 批注。
- 提供查询和导出。
- 生成面向 Agent 的上下文包。

### 3.2 适配器层负责

- 读取某种外部数据源。
- 解析外部数据源的结构。
- 生成标准候选对象、候选记录、候选位置、候选关系。
- 不直接替用户判断优先级。
- 不直接写入原始数据源。

### 3.3 外部 Agent 负责

- 基于 CLI 输出判断今天该做什么。
- 判断项目是否卡住。
- 判断事务优先级。
- 对项目、事务、想法进行批注、风险提示、建议。
- 通过 CLI 的 annotation 接口把批注写入系统内部数据库。

---

## 4. 核心领域模型

本节描述概念模型，不要求实现时逐字使用同名类或同名表，但实现必须覆盖这些语义。

### 4.1 ActionObject

ActionObject 是系统最核心的抽象对象。Project、Task、Idea 都是 ActionObject 的不同类型。

必要语义：

- id：系统内部稳定 ID。
- type：project / task / idea。
- title：对象标题或主文本。
- status：对象状态。对 Task 可来自 TODO / DOING / DONE；对 Project 可来自页面属性；对 Idea 可是 captured / linked / archived 等。
- created_at：对象创建时间或推断创建时间。
- created_at_source：创建时间来源，例如 explicit、journal_date、page_property、file_stat、first_seen。
- updated_at：对象最近修改时间或来源记录最近修改时间。
- first_seen_at：第一次被 CLI 索引到的时间。
- last_seen_at：最近一次被 CLI 索引到的时间。
- canonical_source：首要来源，如 logseq、flomo、manual。
- canonical_location_id：最可信的原始位置。
- confidence：对象识别置信度。
- metadata：扩展信息。

Project、Task、Idea 可以有专属 profile，但第一版也可以通过 metadata 表达差异。

### 4.2 SourceRecord

SourceRecord 是原始数据源中的记录片段。

它可以是：

- Logseq 页面。
- Logseq 块。
- Logseq Daily Journal。
- Flomo memo。
- 手动输入的 inbox 条目。

必要语义：

- id：系统内部记录 ID。
- source_type：logseq / flomo / manual。
- source_item_id：外部来源中的 ID，例如 block uuid、memo id、文件路径。
- raw_text：原始文本。
- normalized_text：规范化后的文本。
- record_type：page / block / journal / memo / annotation_context 等。
- parent_record_id：父记录。
- location_id：位置。
- observed_at：本次同步观察到的时间。
- source_created_at：来源中可识别的创建时间。
- source_updated_at：来源中可识别的更新时间。
- metadata：页属性、块属性、Logbook、标签、引用等扩展信息。

### 4.3 Location

Location 表示可回跳或可定位的原始位置。

必要语义：

- source_type。
- workspace / graph。
- file_path。
- page_name。
- journal_date。
- block_uuid。
- line_start / line_end。
- block_path：从页面根部到当前块的层级路径。
- external_url：对 Flomo 或未来其他来源可用。

Location 必须尽可能保留足够信息，让用户或 Agent 能追溯到原文。

### 4.4 ObjectRecordLink

ActionObject 和 SourceRecord 是多对多关系。一个对象可能有多个记录，一个记录也可能参与多个对象的上下文。

关系角色包括：

- definition：对象的定义来源。
- child_record：对象下方的子块记录。
- process_note：执行过程记录。
- idea_note：对象下方产生的想法。
- resource：资源。
- reflection：反思。
- journal_exposure：某天 Daily Log 中重新出现或被引用。
- reference：引用关系。
- context：其他上下文。

### 4.5 Relation

Relation 表示对象之间的关系。

典型关系：

- belongs_to：Task 属于 Project，Idea 属于 Project / Task。
- derived_from：Task 来源于 Idea。
- references：对象引用另一个对象或记录。
- related_to：弱关联。
- blocks：阻塞关系，可由 Agent 批注或用户手动添加。

第一版最重要的是 belongs_to。

### 4.6 Annotation

Annotation 用于存储人或 Agent 对对象的批注、建议、风险提示、总结和评论。

必要语义：

- id。
- target_object_id 或 target_record_id。
- author：human / agent 名称。
- annotation_type：comment / suggestion / risk / summary / critique / decision。
- content。
- created_at。
- status：open / accepted / rejected / archived。
- context_snapshot_id：可选，用于记录该批注基于哪一次上下文导出。
- metadata：模型名、prompt、来源命令等。

Annotation 不写回 Logseq，默认仅保存在 CLI 内部数据库。

### 4.7 ContextPackage

ContextPackage 是对外部 Agent 的主要输出单位。

它不是一个永久对象，而是查询结果的组织格式。

它应该包含：

- 查询条件。
- 被选中的 objects。
- 每个 object 的元信息。
- 每个 object 的来源位置。
- 每个 object 的关键 records。
- 每个 object 的 relations。
- 每个 object 的 annotations。
- 截断策略说明。
- 敏感内容过滤说明。

---

## 5. 核心服务

### 5.1 Sync / Ingest 服务

负责接收 adapter 输出的候选数据，并写入内部索引。

关键要求：

- 幂等：同一来源重复同步不应产生重复对象。
- 可追踪：记录每次 sync run 的开始时间、结束时间、来源、文件数、记录数、对象数、错误数。
- 可重建：索引理论上应能从原始来源重新生成。
- 可增量：支持按文件 mtime、source id、memo timestamp 等做增量同步。

### 5.2 Merge / Identity 服务

负责判断候选对象是否与已有对象相同。

初期策略可以保守：

- 有稳定外部 ID 的，以 source_type + source_item_id 为主键。
- Logseq block 有 uuid 时，以 uuid 为强身份。
- Logseq block 无 uuid 时，以 file_path + line range + normalized text hash 作为弱身份。
- Project 以 page identity 为主。
- Journal 中纯引用块不创建新 Task，而创建 journal_exposure 关系。

不要在第一版过度进行语义去重。宁可保留重复候选，也不要错误合并不同事项。

### 5.3 Query 服务

提供面向人和 Agent 的查询能力。

基本查询：

- projects：列出项目。
- tasks：列出事务。
- ideas：列出想法。
- object show：展示对象元信息。
- object context：展示对象完整上下文。
- records：按来源或对象查询记录。
- annotations：查询批注。

### 5.4 Context 服务

负责生成 Agent 上下文包。

关键要求：

- 支持 JSON 和 Markdown 输出。
- 支持按时间范围过滤。
- 支持按 project / task / idea 过滤。
- 支持包含或排除子块记录。
- 支持包含或排除 Agent annotations。
- 支持限制输出大小，避免一次性塞入全量 Logseq。
- 输出必须包含来源位置和截断说明。

### 5.5 Annotation 服务

负责保存、查询、更新 Agent 批注。

关键要求：

- 可以给 project / task / idea / record 添加批注。
- 可以区分 comment、suggestion、risk、summary、critique。
- 可以标记 accepted / rejected / archived。
- 不写回 Logseq。

---

## 6. 适配器设计

### 6.1 适配器统一契约

每个 adapter 应输出标准候选数据，而不是直接操纵核心表。

候选数据包括：

- CandidateObject。
- CandidateRecord。
- CandidateLocation。
- CandidateRelation。
- CandidateWarning。

候选数据必须带：

- source_type。
- source identity。
- raw_text。
- location。
- confidence。
- extraction_rule。

这样核心层可以统一 ingest，而不关心来源细节。

### 6.2 Logseq Adapter

Logseq adapter 是第一阶段最重要的 adapter。

#### 6.2.1 输入范围

应支持配置：

- graph_path。
- pages_dir。
- journals_dir。
- include / exclude patterns。
- 是否扫描 assets，第一版默认不扫描。
- 是否只扫描最近 n 天 journals。

#### 6.2.2 Markdown 块树解析

Logseq 的关键结构是缩进块。Adapter 应将 Markdown 文件解析为 block tree。

解析要求：

- 识别 `- ` 开头的块。
- 根据缩进恢复父子关系。
- 保留原始行号。
- 识别代码块边界，避免把代码块中的 TODO 当成任务。
- 识别块属性，例如 `id::`、`type::`、`collapsed::`。
- 识别页面属性，例如文件顶部的 `key:: value`。

#### 6.2.3 Project 识别

高置信 Project：

- 页面属性含 `PARA:: [[PARA/Project]]`。
- 页面正文含至少一个项目结构标记：`[具体目标]`、`[具体事务]`、`[资源列表]`、`[头脑风暴]`、`[反思]`。

中置信 Project：

- 只有 PARA project 属性。
- 或只有项目结构标记。

低置信 Project：

- 页面名前缀为 `项目-`、`任务-`、`学习-`、`课程-`、`阶段-` 等，且包含任务或结构标记。

不要只识别 `项目-` 前缀。用户的实际项目概念比此前缀更广。

#### 6.2.4 Task 识别

识别：

- `TODO ...`
- `DOING ...`
- `DONE ...`

同时解析：

- 优先级标记 `[#A]` / `[#B]` / `[#C]`。
- `SCHEDULED`。
- `DEADLINE`。
- `:LOGBOOK:` / `CLOCK:`。
- `type:: [[任务]]` / `type:: [[行动]]`。

注意：用户实际很少使用 DOING，很多过程记录直接写在 TODO 下方。所以系统应保留原始 task_state，同时通过记录活动提供 activity signals，但不自行判断优先级。

#### 6.2.5 Idea 识别

识别：

- `**[想法]** ...`
- `[想法] ...`
- `**[随想]** ...`
- `[随想] ...`

关联规则：

- 位于项目页 `[头脑风暴]` 区域下：关联到 Project。
- 位于 Task 子块下：关联到 Task。
- 位于 Daily Log 中且无父级任务：作为 free idea。
- 未来来自 Flomo：默认作为 free idea，后续由 Agent 或用户建议关联。

#### 6.2.6 Record 抽取

Task / Idea / Project 下方的子块不要丢弃。它们是 Agent 判断的重要上下文。

子块可以按角色粗分：

- `[注]`：note。
- `[想法]`：idea_note。
- `[问题]`：question。
- `[部署]`：operation / process_note。
- `[反思]`：reflection。
- URL / 代码块 / 自由叙述：context。

这些角色不必过度精确，但要保留原文和层级。

#### 6.2.7 Block reference 与 embed

需要识别：

- `((uuid))`
- `{{embed ((uuid))}}`

处理原则：

- 纯引用行不是新任务。
- embed 可能是结构性模板复用，不能直接当成任务关联。
- 对高频被嵌入的模板块，应允许配置忽略或标记为 structural_embed。
- 对 journal 中引用某个任务块的情况，可建立 journal_exposure 记录。

#### 6.2.8 敏感信息处理

Logseq 子块里可能含 token、密码、IP、账号等敏感信息。

第一版应至少支持：

- 基于关键词或正则的基础脱敏。
- 用户配置 sensitive patterns。
- 支持 `private:: true` 或 `**[敏感]**` 标记。
- Agent context 默认不输出敏感记录原文，只输出占位说明。

### 6.3 Flomo Adapter

Flomo 不是第一阶段必须完成的完整能力，但核心架构必须允许后续接入。

Flomo adapter 应将 memo 映射为：

- SourceRecord: memo。
- CandidateObject: 通常是 Idea；如果有明确 TODO 标记，也可生成 Task candidate。
- Location: memo id / external url / created_at。

Flomo 的关键价值是轻量捕获，所以不要要求它和 Logseq 一样结构化。

---

## 7. CLI 接口设计

CLI 命令名可由实现者决定，但语义应覆盖以下能力。

### 7.1 配置

- 初始化配置。
- 设置 Logseq graph path。
- 查看当前配置。
- 检查数据源可用性。

示例语义：

```bash
tm init
tm config set logseq.graph_path /path/to/graph
tm config show
tm doctor
```

### 7.2 同步 / 索引

```bash
tm sync logseq
tm sync all
tm sync status
tm sync runs
```

要求：

- 同步结果要输出统计。
- 支持 dry-run。
- 支持 verbose。
- 支持只扫描最近 journal 或指定页面。

### 7.3 对象查询

```bash
tm projects
tm tasks
tm ideas
tm show <object-id>
tm context <object-id>
```

输出应支持：

- table / markdown / json。
- 过滤 active / done / recent / project。
- 限制数量。

### 7.4 Agent 上下文

```bash
tm agent context
tm agent context --recent 14d
tm agent project <project-id-or-title>
tm agent task <task-id>
tm agent ideas --recent 30d
```

要求：

- 输出稳定 JSON，供 Agent 程序化读取。
- 同时支持 Markdown，供人复制给 Agent。
- 不做优先级最终判断。
- 包含来源、记录、批注、截断说明。

### 7.5 Annotation

```bash
tm annotation add <object-id> --type suggestion --author agent --content "..."
tm annotation list <object-id>
tm annotation update <annotation-id> --status accepted
tm annotation archive <annotation-id>
```

要求：

- 批注保存在 CLI 内部数据库。
- 不写回 Logseq。
- 支持关联到 project / task / idea / record。

### 7.6 调试与诊断

```bash
tm debug parse-logseq-file <path>
tm debug block <uuid>
tm debug refs <uuid>
tm stats
```

这类命令对于适配 Logseq 非常重要。

---

## 8. 数据存储建议

第一版建议使用 SQLite。

原因：

- 本地单用户。
- 事务可靠。
- 方便做索引。
- 可用 FTS 做全文检索。
- 便于 Agent 和 CLI 快速查询。

概念表建议：

- objects。
- source_records。
- locations。
- object_record_links。
- relations。
- annotations。
- sync_runs。
- adapter_items / source_fingerprints。
- context_exports，可选。

不要求实现时完全照搬表名，但必须覆盖这些语义。

---

## 9. 时间语义

创建时间是关键，但 Logseq Markdown 未必能提供真实块创建时间。因此系统必须区分：

- explicit_created_at：原文明确给出的时间。
- inferred_created_at：从 journal 日期、页面 start、文件时间等推断。
- first_seen_at：CLI 第一次索引到该对象的时间。

不同对象的策略：

### Project

优先级：

1. 页面属性 `start::`。
2. 页面属性中其他显式日期。
3. 文件创建时间或 Git 历史。
4. first_seen_at。

### Task

优先级：

1. 块属性或调度字段中的显式日期。
2. 如果在 journal 中，使用 journal 日期作为 inferred_created_at。
3. 如果在项目页中，使用 first_seen_at；未来可用 Git blame 辅助。

### Idea

优先级：

1. Flomo memo created_at。
2. journal 日期。
3. 项目页中无明确时间时使用 first_seen_at。

不要伪装成拥有绝对准确的创建时间。每个时间都要标明来源。

---

## 10. Agent 工作流

典型流程：

1. 用户运行 `tm sync logseq` 更新索引。
2. 外部 Agent 调用 `tm agent context --recent 14d --format json`。
3. CLI 返回当前项目、事务、想法、记录、批注、来源位置。
4. Agent 判断“今天该做什么”“优先级如何”“项目是否卡住”。
5. Agent 通过 `tm annotation add` 把分析结果作为批注存入 CLI 内部数据库。
6. 用户可查询批注，决定是否采纳。

关键边界：

- `tm agent context` 不直接回答今天做什么。
- Agent 的判断不是事实，只是 annotation / suggestion。
- Logseq 原文不被自动修改。

---

## 11. 推荐的 Logseq 轻量规范

不要求大规模迁移，但建议用户逐步保持：

1. 项目页尽量保留 `PARA:: [[PARA/Project]]`。
2. 希望被系统识别为事务的内容，显式写成 TODO / DOING / DONE。
3. 想法统一为 `**[想法]** ...`。
4. 重要项目尽量写 `start:: YYYY-MM-DD`。
5. 敏感内容使用 `private:: true` 或 `**[敏感]**` 标记。
6. 结构性模板 embed 可以列入配置忽略名单。

---

## 12. 测试要求

实现必须包含测试，而不是只做能跑的脚本。

### 12.1 Parser 测试

覆盖：

- Logseq block tree 解析。
- 页面属性解析。
- 块属性解析。
- TODO / DOING / DONE 识别。
- 代码块内 TODO 不误判。
- 子块层级恢复。
- block uuid 解析。
- block ref / embed 解析。

### 12.2 Adapter 测试

覆盖：

- 项目页识别。
- journal 任务识别。
- 项目页任务归属。
- idea 识别与归属。
- structural embed 不生成任务。
- 纯引用行不生成新任务。

### 12.3 Core 测试

覆盖：

- ingest 幂等。
- 对象与记录关联。
- annotation 增删查改。
- context package 生成。
- 敏感内容过滤。

### 12.4 CLI 测试

覆盖：

- sync 命令。
- list 命令。
- show/context 命令。
- agent context JSON 输出可解析。
- annotation 命令。

### 12.5 Fixture

需要构造一个小型 Logseq fixture graph，包含：

- pages/ 项目页。
- journals/ daily log。
- TODO / DOING / DONE。
- `[想法]`。
- 子块过程记录。
- `id::`。
- `((uuid))`。
- `{{embed ((uuid))}}`。
- 代码块中的 TODO。
- 敏感信息样本。

---

## 13. 文档要求

实现应包含：

1. README：项目定位、安装、初始化、基本用法。
2. docs/design.md：核心设计，基于本文档更新为实际实现版本。
3. docs/logseq-adapter.md：Logseq 格式学习结果、解析规则、限制。
4. docs/agent-interface.md：Agent 如何调用 CLI、JSON 输出结构、annotation 使用方式。
5. docs/testing.md：如何运行测试、fixture 说明。

---

## 14. 第一版完成标准

第一版不是最小玩具原型，而应是一版可继续演进的完整基础系统。完成标准：

1. 可以初始化配置和数据库。
2. 可以只读扫描 Logseq graph。
3. 可以识别 Project / Task / Idea。
4. 可以恢复 Task / Idea 下方子块记录。
5. 可以保存来源位置。
6. 可以建立对象与记录关系。
7. 可以查询 projects / tasks / ideas。
8. 可以展示单个对象的上下文。
9. 可以输出 Agent context JSON / Markdown。
10. 可以添加、查询、更新 Annotation。
11. 不会自动修改 Logseq。
12. 有测试 fixture 和自动化测试。
13. 有 README 和设计文档。
14. 有 Logseq adapter 的限制说明。

---

## 15. 后续演进方向

后续可考虑：

1. Flomo adapter。
2. Git 历史辅助推断创建时间。
3. FTS 全文搜索。
4. 更复杂的对象去重和语义关联。
5. Watch mode 增量同步。
6. 手动 inbox。
7. 可确认的 Logseq 回写。
8. MCP server，使 Agent 不仅通过 CLI，而是通过工具协议调用。

但第一版必须先把核心对象、来源位置、上下文记录、Agent 批注闭环打牢。
