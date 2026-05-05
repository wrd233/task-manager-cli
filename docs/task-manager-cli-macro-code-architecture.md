# task-manager-cli 宏观代码架构设计说明

> 版本：v0.1  
> 读者：Codex / Claude Code / 后续接手开发的代码 Agent  
> 定位：宏观代码层设计，不是完整工程规格，不限定所有类名、函数签名、数据库表结构或实现细节。  
>
> 本文的目标是：让代码 Agent 理解 `task-manager-cli` 接下来应该如何从“Logseq 行动对象索引器”演进为“个人行动系统”的工程结构，而不是直接替它完成所有细节设计。

---

## 1. 项目定位

`task-manager-cli` 不再只是一个 TODO 抽取工具，也不只是一个 Agent context exporter。

它的长期定位是：

> 以 CLI 为主要入口、以 Logseq 为自然记录现场、以行动条目为第一公民、以 Clarify / Review / Proposal 为核心流转机制、以项目语义树和成果标注为组织方式的个人行动系统。

因此，代码架构应服务于以下目标：

1. 从 Logseq / 未来 Flomo / CLI 输入中捕获行动线索；
2. 将自然记录抽象为行动条目、想法、小任务、项目、资源、成果等语义对象；
3. 支持 Clarify / Review 流程，让用户和远端 API 共同澄清条目；
4. 支持 Proposal 机制，让 AI 或系统建议成为可审核、可回滚的结构化变更；
5. 支持部分语义在用户确认后写回 Logseq；
6. 支持项目语义树与 Logseq 项目页结构同步；
7. 支持 `[成果]` / `[无成果]` 的成果沉淀；
8. 同时提供人类视图、Agent 上下文和开发调试报告。

---

## 2. 设计原则

### 2.1 不要把所有逻辑塞进 Logseq adapter

Logseq adapter 只负责理解 Logseq 格式：

- Markdown block tree；
- Daily Log；
- TODO / DOING / DONE / WAITING；
- 行首标注，如 `[想法]`、`[待澄清]`、`[成果]`、`[注]`；
- 项目页属性；
- 项目页结构；
- block ref / page ref；
- 文件位置。

它不应该负责最终的 GTD 判断、Proposal 应用、Review 交互、项目语义树优化或 Agent 调用。

这些属于更上层的领域逻辑。

### 2.2 Core 不应该依赖任何具体数据源

核心领域层不应该知道 Logseq、Flomo 或文件系统具体格式。

它应该只理解：

- 行动条目；
- 想法；
- 小任务；
- 项目；
- 项目节点；
- 资源；
- 成果标注；
- Review Session；
- Proposal；
- Annotation；
- Relation；
- Location / Source。

### 2.3 AI 输出永远不是事实

远端 API / Agent 的输出必须先进入 Proposal 或 Annotation。

不能让 AI 输出直接修改：

- 内部语义层；
- Logseq 原文；
- 项目语义树；
- GTD 状态；
- 文件关联。

结构性变更必须经过用户确认。

### 2.4 Logseq 可写，但必须安全

早期版本强调不写 Logseq。新需求中，Logseq 可以在用户确认后写回部分内容。

但写回必须遵守：

1. 只写用户确认过的内容；
2. 不覆盖用户原文；
3. 有 preview / diff；
4. 可追踪；
5. 格式稳定；
6. 不自动写高风险结构调整；
7. 不把 AI 草稿当用户记录。

### 2.5 人类视图和 Agent 视图必须分离

给人的输出要短、清楚、少字段。

给 Agent 的输出可以详细、结构化、有证据链。

给开发者的 report 可以全量和诊断化。

不要让一个命令同时试图服务三类读者。

---

## 3. 建议的宏观分层

这不是强制目录结构，但建议保持以下职责边界。

```text
task_manager_cli/
  core/             # 领域对象与核心语义
  adapters/         # Logseq / Flomo / file-system 等来源适配器
  ingest/           # 同步、候选对象归并、幂等导入
  semantics/        # GTD 状态、行动条目语义、Idea/Task/Reference 分类
  review/           # Clarify / Review Session 流程
  proposals/        # Proposal 生成、审核、应用、回滚
  annotations/      # 用户注、AI 注、批注管理
  projects/         # Project / 小任务 / 项目语义树 / 项目纳管
  outcomes/         # [成果] / [无成果] / 文件成果线索
  query/            # 人类视图、Agent 上下文、报告查询
  providers/        # 远端 API provider 抽象
  storage/          # 持久化、迁移、仓储
  privacy/          # 脱敏、payload 预览、安全边界
  cli/              # 命令行入口与交互编排
```

Codex 可以根据当前仓库已有结构做取舍，不需要机械照搬目录名。

关键不是名字，而是职责不要混乱。

---

## 4. 关键模块职责

## 4.1 Core：领域对象层

Core 负责定义系统理解世界的基本对象。

至少需要能表达：

- Action Item；
- Idea；
- Mini Project / 小任务；
- Project；
- Project Node；
- Resource / Reference；
- Result Marker，即 `[成果]` / `[无成果]`；
- Annotation；
- Proposal；
- Review Session；
- Relation；
- Source / Location。

注意：

- Reference 不应简单作为 Action Item，而更像资源；
- Idea 可以是行动条目的一种语义，也可以作为设计型对象长期保留；
- 小任务独立于 Project，可以存在于日记，也可以挂载到 Project / Project Node；
- Project 在 Logseq 中应对应项目页和 `PARA:: [[PARA/Project]]`；
- `[成果]` 是用户层面的统一成果表达，不要过早拆成大量复杂对象。

Core 不要关心 Markdown 怎么解析，也不要关心具体 CLI 命令怎么写。

---

## 4.2 Adapter：来源适配层

Adapter 负责把不同来源转成系统可理解的候选数据。

### Logseq Adapter

应继续作为第一优先级。

它需要识别：

- pages；
- journals；
- page properties；
- Logseq task states；
- 行首标注；
- 项目页结构；
- 项目语义树节点；
- block refs；
- page refs；
- 子块层级；
- `[成果]` / `[无成果]`；
- `[注]` / `[AI注]`；
- `#inbox` / `#waiting` / `#someday` 等轻标签；
- Source / Location。

Logseq adapter 的输出应该是候选对象和候选关系，而不是最终事实。

### Future Adapters

未来可扩展：

- Flomo；
- 文件系统 metadata；
- 手动 CLI inbox；
- 远端系统；
- 浏览器剪藏。

这些适配器都应输出统一候选格式，不要绕过 ingest / merge。

---

## 4.3 Ingest：同步与归并层

Ingest 负责将 adapter 产生的候选数据合并进内部语义层。

它需要处理：

- 幂等同步；
- 对象身份稳定；
- SourceRecord 与 Location 的一致性；
- 已存在对象更新；
- Logseq 状态变化同步；
- 删除 / 缺失 / 改名；
- block ref 暴露；
- Project / 小任务 / Action Item 的候选关系；
- `[成果]` 等子块的识别关联。

Ingest 不负责用户确认逻辑。需要用户确认的变更应进入 Proposal。

---

## 4.4 Semantics：语义层

Semantics 负责解释条目的处理语义。

它应该服务于：

- GTD 状态；
- 多重语义；
- inbox / next / waiting / someday / reference / done / dropped；
- idea / design idea / actionable idea；
- needs_clarify；
- missing_result；
- project_candidate；
- mini_project_candidate。

注意：

GTD 状态可以部分写回 Logseq，但内部也应维护系统语义。

Logseq 中已有标记是信号，不一定是最终语义。

---

## 4.5 Review / Clarify：澄清流程层

Review 层负责组织用户主动进入的澄清流程。

它应支持概念上的多种 Review：

- Inbox Review；
- Today Review；
- Idea Review；
- Task Review；
- Project Review；
- Tree Review；
- Done Review；
- Weekly Review；
- Manual Selection Review。

Clarify 是 Review 中的一种关键交互形态。

它的核心流程：

```text
选择范围
→ 生成候选条目
→ 系统或远端 API 初步判断
→ 对不确定或高影响条目提问
→ 用户逐条回答
→ 远端 API 生成 Proposal
→ 汇总建议表
→ 用户审核
→ 应用确认后的 Proposal
```

这层应考虑：

- 可暂停；
- 可恢复；
- 可跳过；
- 可批量接受；
- 可逐条修改；
- 保留 Review 历史。

实现细节可由 Codex 决定，但需求层必须保留这些能力边界。

---

## 4.6 Providers：远端 API 层

远端 API 和 Agent 不是同一个概念。

远端 API 是日常操作中的辅助能力，用于：

- Clarify；
- 分类建议；
- 描述细化；
- Proposal 生成；
- 批量语义判断。

Agent 是更重的上下文分析者，用于：

- 项目诊断；
- 复杂计划；
- 深度 Review；
- 代码修改；
- 系统设计；
- 使用 `tm agent` 上下文。

因此，代码上应预留 provider 抽象：

- provider 可配置；
- prompt 可配置；
- 请求可预览；
- 支持失败重试；
- 支持异步 / 批量处理；
- 不要把某一个模型写死到业务逻辑中。

---

## 4.7 Proposal：结构化变更层

Proposal 是 AI 或系统建议修改结构的载体。

它不同于 Annotation。

Proposal 可以建议：

- 修改 GTD 状态；
- 改写标题；
- 创建小任务；
- 关联 Project；
- 关联 Project Node；
- 创建项目树节点；
- 调整项目树；
- 写回 `[AI注]`；
- 添加 `[成果]` 或 `[无成果]`；
- 关联文件；
- 归档；
- 合并；
- 拆分。

Proposal 应有风险分级：

- 低风险；
- 中风险；
- 高风险。

高风险 Proposal 必须显式确认。

Proposal 必须可追溯，且需要支持回滚或撤销。

这层是系统可信度的关键，不要省略。

---

## 4.8 Annotation：批注层

Annotation 更接近用户笔记中的 `[注]`。

它不是主要给 AI 大量写评论的系统。

需要区分：

- `[注]`：用户批注；
- `[AI注]`：AI 批注。

AI 注应该：

- 短；
- 少；
- 经用户确认；
- 不冲散原文；
- 不替代用户记录；
- 可过滤。

Annotation 可以挂在：

- Action Item；
- Idea；
- Mini Project；
- Project；
- Project Node；
- Result Marker；
- Review Session。

但不要让 Annotation 和 Proposal 混用。

---

## 4.9 Projects：项目与项目语义树层

Project 层负责：

- 正式 Project；
- 小任务；
- Project Node；
- 项目语义树；
- 项目纳管；
- 项目 Review；
- Project 与 Logseq 项目页同步。

重要需求：

1. Logseq 中的 Project 应对应项目页和 `PARA:: [[PARA/Project]]`。
2. 小任务可以独立存在，也可以挂到 Project / Project Node。
3. 项目语义树是一等对象，但不要求所有项目都有复杂树。
4. 项目语义树倾向与 Logseq 项目页结构同步。
5. 树节点优先使用行首标识表达，例如 `[目标]`、`[里程碑]`、`[工作流]`、`[小任务]`、`[资源]`、`[成果]`。
6. 项目结构以树为主，引用和 relation 作为补充。
7. AI 可提出项目树新增、修改、删除、移动建议，但全部作为 Proposal。

项目树不应强制所有项目 OKR 化。

核心节点应优先支持：

- Workstream / 小任务组；
- 小任务；
- Action Item；
- Resource；
- 成果。

Objective / Key Result / Milestone 可以支持，但不应成为每个项目的必填结构。

---

## 4.10 Outcomes：成果层

需求层已经明确：当前不要过早拆分 Outcome / Artifact / Knowledge 等复杂对象。

用户层统一使用：

```text
**[成果]** ...
**[无成果]** ...
```

代码层可以在内部识别成果线索，但对用户保持简单。

成果层应负责：

- 识别 DONE 下是否存在 `[成果]` 或 `[无成果]`；
- 在 Review 中提醒缺少成果标注；
- 识别 `[成果]` 中的文件路径、链接、文档、经验；
- 支持用户显式触发经验卡片生成；
- 不默认自动生成 Anki Card；
- 不把所有 DONE 都强制成果化。

成果是项目进展的重要证据。

---

## 4.11 File Metadata：文件系统辅助层

文件系统初期只做辅助证据源，不要设计得过重。

建议只做 metadata 扫描：

- 文件名；
- 路径；
- 类型；
- 修改时间；
- 大小；
- 最近新增 / 修改。

不要默认读取文件内容。

文件关联必须先成为 Proposal。

如果 `[成果]` 中出现文件路径，可以尝试识别为成果证据。

文件系统主要服务于：

- 项目 Review；
- 成果确认；
- 项目进展诊断；
- 缺失交付物提示。

---

## 4.12 Query：视图层

查询层需要清晰地区分不同读者。

### Human View

给用户看：

- 短；
- 中文优先；
- 少字段；
- 分组清楚；
- 可展开；
- 支持快速操作。

### Review View

给用户交互式澄清：

- 一次只展示必要上下文；
- 支持问题；
- 支持回答；
- 支持跳过；
- 支持审核 Proposal。

### Agent Context

给 Agent：

- JSON / 结构化；
- 可包含更多上下文；
- source / location / evidence；
- 不追求短。

### Report

给开发者：

- 抽取质量；
- 同步状态；
- suspicious items；
- mismatch；
- raw statistics。

不要混淆这四类输出。

---

## 4.13 CLI：命令入口层

CLI 只做编排，不应承载领域逻辑。

需求倾向：

- 面向用户的命令应尽量短；
- 可考虑交互式 shell 或 TUI；
- 可提供 alias；
- Agent 命令可以保持显式前缀；
- report 命令可以更详细。

概念分层：

```text
view      用户快速查看
review    用户交互式澄清
clarify   主动澄清
agent     Agent 上下文
report    调试报告
sync      数据同步
proposal  审核与应用
note      注释 / 批注
done      完成与成果标注
project   项目与项目树
```

Codex 可以根据当前 CLI 结构选择具体命令命名，不必一次性重构所有命令。

---

## 5. 关键数据流

## 5.1 从 Logseq 到内部语义层

```text
Logseq Markdown
→ Logseq Adapter
→ Candidate Records / Objects / Relations
→ Ingest / Merge
→ 内部 Action Item / Project / Idea / Mini Project / Result Marker
→ View / Review / Agent Context
```

## 5.2 Clarify 数据流

```text
候选 Action Items
→ Review Session
→ 系统初筛
→ 用户回答问题
→ 远端 API 处理
→ Proposal 生成
→ 建议表
→ 用户审核
→ Proposal 应用
→ 内部语义层更新
→ 可选写回 Logseq
```

## 5.3 项目树优化数据流

```text
Logseq Project Page
→ Project Tree Parse
→ Project Review
→ Agent / API 生成结构 Proposal
→ 用户审核
→ 更新内部项目树
→ 可选写回 Logseq 项目页
```

## 5.4 Done 与成果数据流

```text
Logseq DONE
→ 检查子块是否有 [成果] / [无成果]
→ 缺失则进入 Done Review 候选
→ 用户补充成果或确认无成果
→ 写回 Logseq
→ 内部记录成果线索
→ 可选触发 markcard / 经验卡片
```

## 5.5 文件成果数据流

```text
Project Root 配置
→ 文件 metadata 扫描
→ 最近新增/修改文件
→ 生成可能成果关联 Proposal
→ 用户确认
→ 关联到 Project / 小任务 / Action Item / [成果]
```

---

## 6. Codex 实现时的边界提醒

这份文档不是让 Codex 一次性实现所有能力。

Codex 应：

1. 保持现有可用能力不破坏；
2. 在现有结构上逐步扩展；
3. 优先抽象出清晰领域边界；
4. 不要把所有逻辑塞进 CLI；
5. 不要把所有逻辑塞进 Logseq adapter；
6. 不要过早设计复杂 UI；
7. 不要把 Outcome / Artifact / Knowledge 过早拆得太复杂；
8. 不要让远端 API 直接修改系统；
9. 不要让 AI 注污染 Logseq；
10. 不要默认读取文件内容；
11. 不要默认批量写回 Logseq；
12. 不要牺牲当前索引 / Agent context 能力。

如果要实现下一轮，建议先选择一个小而核心的闭环，例如：

```text
Clarify / Review Session / Proposal / 可确认写回
```

或者：

```text
DONE 缺少 [成果] 的检测与成果 Review
```

但这是后续“实施规格文档”的事情，不在本文展开。

---

## 7. 建议 Codex 阅读顺序

Codex 接手时建议先读：

1. README.md；
2. 当前 docs；
3. `task-manager-cli-action-flow-system-design.md`；
4. `task-manager-cli-requirements-supplement-v0.2.md`；
5. 当前代码目录；
6. tests；
7. 当前 CLI help。

然后再基于本文判断现有代码哪里已经具备，哪里需要扩展。

---

## 8. 最终总结

宏观代码架构的核心不是目录怎么命名，而是职责如何分开：

```text
Adapter 负责读来源；
Ingest 负责归并；
Core 负责领域语义；
Semantics 负责状态解释；
Review 负责澄清流程；
Provider 负责远端 API；
Proposal 负责可审核变更；
Projects 负责项目与语义树；
Outcomes 负责 [成果]；
Query 负责不同视图；
CLI 只负责编排。
```

只要这个边界保持清楚，Codex 可以自主设计具体模块、类、命令和数据结构。

本系统最需要守住的第一性原则是：

> 自然记录不被破坏，行动条目能够流转，AI 建议必须可审核，成果必须能沉淀，用户始终拥有最终确认权。
