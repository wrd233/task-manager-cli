# task-manager-cli Human Shell / 行动工作台需求设计文档

> 版本：v0.2  
> 定位：需求层 / 交互模型层 / 产品设计层  
> 主题：在现有 `tm` 底层 CLI 之上，设计一层面向用户本人日常高频使用的 Human Shell。  
> 范围：本文不涉及数据库表、函数签名或具体代码实现细节，但会明确交互边界、默认行为和写回策略。  
>
> 本版相对 v0.1 的关键变化：
>
> 1. **允许真实 Logseq graph 写回**，但必须写回到合适的位置，并保留可恢复能力。
> 2. **新建内容按当前上下文直接落位**：在 `/today` 写入今日 Daily Note；在 `/projects/<project>` 写入项目页；在项目节点下写入节点；如果无法确定位置，则进入 inbox / 待澄清。
> 3. **用户 Direct Action 不走 Proposal**：`todo / idea / mini / resource / note / done / wait / result / noresult` 等用户明确操作应直接执行并可 undo。
> 4. **`done / wait / result` 直接作用于 Logseq 原文**：`done` 改为 `DONE`，`wait` 优先改为 Logseq `WAITING` task marker，`result` 追加 `**[成果]**`。
> 5. **第一版 Human Shell 的 `clarify` 支持真实逐条回答**，不是简单包装底层 `tm clarify`。

---

## 0. 总体定位

当前 `task-manager-cli` 已经具备较强底层能力：Logseq 同步、Action Item 抽取、Idea / Mini Project / Project Tree 识别、Proposal、Review Session、Clarify、Provider、项目纳管 Proposal、有限 Logseq 写回与 rollback、三类质量报告、Agent / Human / Report 视图。

但这些能力主要通过显式、较长、适合 Agent / 脚本 / 测试的 `tm ...` 命令暴露。

Human Shell 要解决的是：

> 如何让用户本人在日常使用中像操作一个“行动空间”一样操作自己的任务、想法、项目、成果和待审核建议，而不需要每次手动输入完整上下文参数。

因此，Human Shell 不是替代底层 `tm`，而是在底层 `tm` 之上增加一层人类高频操作工作台。

建议入口：

```bash
tm shell
```

推荐用户自行配置短别名：

```bash
alias ta='tm shell'
```

后续文档中使用 `ta>` 代表进入 Human Shell 后的提示符。

---

## 1. 第一性原理：为什么需要 Human Shell

### 1.1 人类操作依赖上下文，而不是每次显式传参

底层 CLI 为了可测试、可脚本化、可给 Agent 使用，必须显式：

```bash
tm clarify selected --ids 123 124 --project "韩国旅行" --provider deepseek
tm project propose-membership --object 123 --project "韩国旅行" --node-id ...
tm proposal accept 456
tm proposal apply 456 --yes
```

但人类日常操作更像：

```text
我现在在今天；
我现在在韩国旅行项目；
我现在在“出行交通”这个工作流；
我想在这里新增一条 TODO；
我想把这条标记为 WAITING；
我想补一个成果；
我想继续澄清这里的条目。
```

因此，Human Shell 必须维护“当前上下文”。

这类似 Linux shell：用户先 `cd` 到某个目录，后续操作默认发生在当前目录下。

在行动系统中，对应为：用户进入 today / inbox / project / project node / mini project，后续 `todo / idea / done / result / clarify` 默认作用于当前上下文。

### 1.2 人类需要连续操作流，而不是孤立命令集合

真实使用时，用户不是单次执行孤立命令，而是在一个上下文中连续工作：

```text
进入今天
查看今天
进入韩国旅行项目
查看项目树
进入出行交通节点
新增任务
把一条任务标记 WAITING
给一条任务补注释
完成一条任务
追加成果
处理待审核 Proposal
启动 Clarify
回到今天
```

Human Shell 的目标不是简单缩短命令，而是提供连续行动会话。

### 1.3 用户自己的明确操作不应被 Proposal 化

Proposal 的意义是约束 AI / Agent / Provider 的建议。

它解决的是：外部智能体认为应该修改系统，但这个判断必须由用户审核。

但用户本人明确输入：

```text
done 123
wait 123 "等客服回复"
note 123 "先做最小版本"
result 123 "形成初稿"
```

这本身已经是用户决策，不应再要求生成 Proposal、accept、apply。

因此必须区分：

```text
用户直接操作 Direct Action
AI / Agent / Provider 建议 Proposal
```

这是 Human Shell 的核心边界。

### 1.4 Human Shell 必须能真实写回 Logseq

Human Shell 面向日常使用，如果所有操作只进入内部数据库，不写回 Logseq，就会割裂用户工作现场。

因此，本版明确：

> Human Shell 的 Direct Action 可以真实写回 Logseq，但必须写回到合适位置，并保留操作历史与 undo 能力。

这与底层 Proposal 写回不同：

- 用户 Direct Action：可以直接执行；
- AI / Provider Proposal：仍需审核后执行；
- 高风险用户操作：仍需确认。

---

## 2. 系统分层：底层 `tm` 与 Human Shell

### 2.1 底层 `tm`

底层 `tm` 继续服务 Agent、脚本、自动化测试、调试、JSON 输出、精确操作、复杂参数传递、质量报告、Provider 验证。

它应保持显式、稳定、可组合、可测试、可脚本化、参数完整、适合 Agent。

Human Shell 不应破坏已有 `tm` 能力。

### 2.2 Human Shell

Human Shell 面向用户本人，特点是：短命令、有当前上下文、默认中文友好、默认人类可读、连续操作、少参数、真实写回、可 undo、低摩擦。

它调用底层 service / command，不重新实现领域逻辑。

抽象关系：

```text
Human Shell command
→ 解析当前上下文
→ 转换为底层语义操作
→ 调用已有 service
→ 写入合适 Logseq 位置或内部关系
→ 记录 operation history
→ 输出人类视图
```

---

## 3. 行动空间与当前上下文

### 3.1 虚拟行动空间

Human Shell 将系统抽象为虚拟行动空间：

```text
/
├── today
├── inbox
├── waiting
├── someday
├── ideas
├── projects
├── mini
├── reviews
└── proposals
```

这些不是磁盘路径，而是语义路径。

### 3.2 当前上下文

当前上下文类似 shell 当前目录。

示例：

```text
ta:/today>
ta:/inbox>
ta:/projects/韩国旅行>
ta:/projects/韩国旅行/工作流/出行交通>
ta:/mini/整理打车攻略>
ta:/reviews/42>
ta:/proposals>
```

当前上下文决定默认行为。

例如：

```text
ta:/today> todo "确认韩国打车 App 是否需要韩国手机号"
```

默认写入今天 Daily Note。

```text
ta:/projects/韩国旅行> todo "整理打车攻略"
```

默认写入韩国旅行项目页。

```text
ta:/projects/韩国旅行/工作流/出行交通> todo "查询 Kakao T 海外信用卡是否可用"
```

默认写入该项目节点下。

### 3.3 Session Context 至少应表达

Human Shell session 需要维护：当前 scope、当前 project、当前 project node、当前 mini project、当前 journal date、默认 provider、默认写回策略、默认输出模式、上一个上下文、最近操作。

退出 shell 后不强制持久化 session。第一版可以只在当前 REPL 会话内维护。

---

## 4. 导航命令

第一版 Human Shell 应支持类文件系统导航。

### 4.1 `pwd`

显示当前上下文：

```text
ta> pwd
/today
```

### 4.2 `ls`

列出当前上下文中的对象。

在 `/today`：

```text
ta:/today> ls

今日待办
待澄清
最近想法
活跃项目
待审核 Proposal
```

在 `/projects/韩国旅行`：

```text
ta:/projects/韩国旅行> ls

项目节点
小任务
未完成行动
想法
资源
成果
待审核 Proposal
```

### 4.3 `cd`

切换上下文：

```text
cd /today
cd /inbox
cd /waiting
cd /projects
cd /projects/韩国旅行
cd 工作流/出行交通
cd 小任务/整理打车攻略
cd ..
cd -
```

允许别名：

```text
cd @today
cd @inbox
cd @p/韩国旅行
cd @mini/整理打车攻略
```

第一版不要求复杂路径补全，但路径解析错误应给出候选提示。

### 4.4 `tree`

显示当前项目或项目节点树。

### 4.5 `show`

显示对象详情：

```text
show 123
show proposal 88
show review 7
```

默认简洁，支持 `--detail`。

### 4.6 `open`

显示或打开 Logseq 源位置。若无法打开 GUI，至少显示文件路径、行号和 block path。

### 4.7 `find`

轻量搜索对象，支持关键词和 marker/tag。

---

## 5. Direct Action：用户直接操作

### 5.1 Direct Action 原则

以下用户明确操作默认是 Direct Action，不走 Proposal：

```text
todo
idea
mini
resource
note
done
doing
wait
someday
result
noresult
```

它们必须直接执行、写回合适 Logseq 位置、更新内部索引或提示 resync、记录 operation history、可 undo，高风险时确认。

### 5.2 `todo`

#### 在 `/today`

```text
ta:/today> todo "确认韩国打车 App 是否需要韩国手机号"
```

默认：写入今日 Daily Note，使用 Logseq `TODO`，进入 Action Item 流。

#### 在 `/projects/<project>`

```text
ta:/projects/韩国旅行> todo "整理打车攻略"
```

默认写入项目页中合适位置。

优先位置：当前 project node；`[具体事务]` 节点；`[小任务]` / `[工作流]` 相关节点；项目页末尾待处理区域；无法确定则提示用户选择或写入 `[待澄清]`。

#### 在项目节点

```text
ta:/projects/韩国旅行/工作流/出行交通> todo "查询 Kakao T 海外信用卡支付支持"
```

默认 append 到当前 node 下，关联当前 project 与 node。

### 5.3 `idea`

```text
ta:/today> idea "返点公司可以做一个风险评分表"
ta:/projects/韩国旅行> idea "打车方案可以分为省钱、稳妥、应急三类"
```

默认写入 `**[想法]** ...`，在项目上下文中关联当前项目，在 node 上下文中关联当前节点，不强行转成 Task。

### 5.4 `mini`

```text
ta:/projects/韩国旅行> mini "整理打车攻略"
```

默认写入 `**[小任务]** 整理打车攻略`，在当前项目 / 节点下创建 mini_project。

### 5.5 `resource`

```text
ta:/projects/韩国旅行> resource "Kakao T 官方说明 https://..."
```

默认写入 `**[资源]** ...` 或当前 `[资源]` 节点。Resource 不进入 Action Item 流。

---

## 6. 状态与成果操作

### 6.1 `doing`

```text
doing 123
```

将 Logseq task marker 改为 `DOING`。

### 6.2 `done`

```text
done 123
```

将 Logseq task marker 改为 `DONE`。如果目标没有 `[成果]` / `[无成果]`，提示用户可补充 `result` 或 `noresult`，但不强制。

### 6.3 `wait`

```text
wait 123 "等返点客服回复汇率"
```

将 Logseq task marker 改为 `WAITING`。必须优先使用 Logseq `WAITING` task marker。等待原因可以作为子块或注释记录，例如 `**[注]** 等返点客服回复汇率`。

### 6.4 `someday`

```text
someday 123
```

追加 `#someday` 或更新内部语义状态。若有明确 Logseq location，优先写回 marker/tag。

### 6.5 `result`

```text
result 123 "形成了一版韩国打车攻略初稿"
```

在目标对象下追加：

```text
- **[成果]** 形成了一版韩国打车攻略初稿
```

### 6.6 `noresult`

```text
noresult 123 "只是临时沟通，无需沉淀成果"
```

追加：

```text
- **[无成果]** 只是临时沟通，无需沉淀成果
```

---

## 7. 注释操作

### 7.1 `note`

```text
note 123 "先做最小版本，不要追求完整"
```

追加：

```text
- **[注]** 先做最小版本，不要追求完整
```

### 7.2 `ainote`

```text
ainote 123 "建议先比较 Kakao T、出租车、机场接送"
```

如果用户手动输入 `ainote`，视为 Direct Action，追加 `**[AI注]** ...`。但 Provider / Agent 生成 `[AI注]` 必须仍走 Proposal。

---

## 8. Direct Action 写回策略

### 8.1 允许真实写回，但必须写到合适位置

本版明确允许 Human Shell Direct Action 写回真实 Logseq。

但必须满足：当前上下文能定位到合适 Logseq location；写回采用 append-only 或 task marker 修改等低/中风险方式；不移动、删除、重排用户原文；记录 operation history；支持 undo；写回后可 resync；无法确定位置时提示用户选择或进入 inbox / 待澄清。

### 8.2 合适位置的默认选择

#### `/today`

写入今日 journal。

#### `/inbox`

写入今日 journal 的 inbox / 待澄清区域；如果没有该区域，可以 append 到今日 journal 末尾，并使用 `#inbox` 或 `**[待澄清]**`。

#### `/projects/<project>`

写入项目页。优先级：当前 node；类型匹配的 marker 节点，如 `[具体事务]`、`[想法]`、`[资源]`；项目页已有同类区域；项目页末尾创建或追加轻量区域；无法定位时询问用户。

#### `/projects/<project>/<node>`

写入当前 node 下。

#### `/mini/<mini>`

写入 mini project 所在 block 下。

### 8.3 Undo

Human Shell 必须支持：

```text
undo
```

第一版至少支持最近一次操作的撤销。

可撤销对象包括：append 的 TODO / Idea / Resource / Mini Project；append 的 `[注]` / `[AI注]`；append 的 `[成果]` / `[无成果]`；task marker 修改；proposal apply，如果底层已有 rollback。

如果无法撤销，必须提示原因。

---

## 9. Proposal 在 Human Shell 中的体验

### 9.1 `proposals`

展示待审核建议。

### 9.2 Proposal 快捷操作

支持：

```text
accept 1
reject 2
edit 3
preview 1
apply 1
apply accepted
```

Proposal 列表可以使用 session-local 编号，但必须能映射到底层 proposal id。

可选简写：`a1 / r2 / e3 / p1`。第一版可以先支持清晰长命令。

### 9.3 批量规则

允许 `accept low`、`apply accepted`。但高风险 Proposal 不允许批量自动 apply。

---

## 10. Clarify 在 Human Shell 中的体验

### 10.1 第一版必须支持真实逐条回答

本版明确：Human Shell v1 的 `clarify` 不只是包装底层命令，而应支持真实的逐条问答体验。

在当前上下文中输入：

```text
clarify
```

根据当前 context 选择候选：`/today`、`/inbox`、`/projects/<project>`、project node、`/mini/<mini>`、`/ideas`、`/waiting`。

### 10.2 做题式交互

示例：

```text
条目 #123：整理打车攻略

当前状态：TODO
来源：今日 Daily Note
当前上下文：韩国旅行 / 出行交通

问题 1：这个条目是否仍然有价值？
> 有

问题 2：它更像一个行动、小任务、想法、资源，还是等待？
> 小任务

问题 3：它属于当前项目节点吗？
> 是

已记录，进入下一条。
```

回答完成后：

```text
生成 3 条建议：

[1] #123 升级为小任务
[2] #123 关联到 韩国旅行 / 出行交通
[3] #123 追加 [AI注]：建议拆为三步

操作：accept / reject / edit / apply
```

Clarify 仍然基于 Review Session。Provider 输出仍然只生成 Proposal。

### 10.3 Clarify 模式

支持：

```text
provider off
provider dry-run
provider mock
provider deepseek
```

Clarify 可以有 manual、dry-run、mock、provider 模式。

---

## 11. 输出原则

Human Shell 默认短输出，不展示大段 JSON、全量 metadata、全量 source records、provider payload 和调试细节。

支持 `detail on/off` 或命令级 `--detail`。

JSON 继续由底层 `tm` 命令服务 Agent / 脚本，Human Shell 默认人类可读。

---

## 12. 第一版最小可用范围

第一版 Human Shell 应支持：

```text
tm shell

pwd
ls
cd
tree
show
open
find

todo
idea
mini
resource
note
ainote
doing
done
wait
someday
result
noresult

clarify
proposals
accept
reject
edit
preview
apply
undo

provider
mode
help
exit
```

其中必须实现的核心闭环是：

```text
进入 shell
→ cd 到 today/project/node
→ todo / idea / note / done / wait / result
→ 真实写回合适 Logseq 位置
→ undo
→ clarify 逐条回答
→ Provider 生成 Proposal
→ proposals / accept / apply
→ rollback 或 undo
```

---

## 13. 本阶段不做

本阶段不做复杂 TUI、全屏表格编辑器、项目树拖拽重排、大规模移动 Logseq 块、自动批量重写项目页、文件系统扫描、完整成果系统、Anki Card、多用户协作、图数据库式复杂关系编辑、自动补全、复杂 shell history。

---

## 14. 成功标准

Human Shell v1 成功标准：

1. 用户可以每天通过 `tm shell` 进入行动工作台。
2. 用户可以 `cd /today`、`cd /projects/<project>`、`cd` 到项目节点。
3. 当前上下文能决定 `todo / idea / mini / resource` 的写入位置。
4. `done / wait / result` 能直接修改 Logseq 原文，并可 undo。
5. `WAITING` 使用 Logseq task marker。
6. Direct Action 不要求 Proposal。
7. Provider / Agent 建议仍必须走 Proposal。
8. `clarify` 支持真实逐条回答。
9. Human Shell 不破坏底层 `tm` 命令。
10. 真实写回能写到合适位置，而不是无脑 append 到文件末尾。
11. 错误或无法定位时，系统能提示用户选择，不静默乱写。
12. 所有核心操作有测试和文档。

---

## 15. 总结

Human Shell 的本质是：

> 在现有 `tm` 底层能力之上，提供一个面向用户本人日常操作的行动工作台。

本版确定了更明确的方向：

```text
允许真实 Logseq 写回；
新建内容按当前上下文落位；
用户 Direct Action 直接执行并可 undo；
done / wait / result 直接改 Logseq，其中 WAITING 使用 Logseq task marker；
clarify 第一版支持真实逐条问答；
AI / Provider 输出仍然走 Proposal。
```

最终目标是让系统从“一组强大的工程命令”变成“用户每天愿意打开的个人行动 shell”。
