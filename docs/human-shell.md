# Human Shell

## Project Lifecycle Commands

Human Shell 现在支持项目生命周期闭环：

```text
cd /projects
project create "测试项目" --template standard --goal "形成第一版成果" --enter
todo "先记录一个任务"
idea "一个还不成熟的想法"
resource "一个参考资料"
result "形成第一版成果"
ls inbox
ls unplaced
clarify unplaced
proposals
accept 1
preview 1
apply 1
tree
quality project
undo
```

`project create` / `new project` 创建项目页和内部 Project object，不覆盖已有页面，支持 `--preview` 和最近操作 `undo`。在项目 root 下 capture 的对象会 append-only 写入对应 section；没有明确 semantic node 时视为 project-level / unplaced，不进入结构化 `tree`。

Dashboard 视角：

```text
cd /dashboard
ls quality
ls unplaced
ls project-health
```

安全边界：Shell 的直接写回只做追加或受限块修改；Proposal apply 仍要求 preview、backup、rollback。移动、删除、合并、重排原始 Logseq 块不由 Shell 自动执行。

Human Shell 是 `task-manager-cli` 面向用户本人日常高频操作的 REPL 行动工作台。它建立在现有 `tm`
service 之上，不替代底层命令，也不改变 Agent / Provider 的 Proposal 审核边界。

启动：

```bash
tm shell
```

可以自行配置短别名：

```bash
alias ta='tm shell'
```

系统不会自动修改用户 shell 配置。

## Context

Human Shell 维护当前 session context。第一版只在当前 REPL 内保存，不强制持久化。

上下文包含：

- 当前虚拟路径；
- 当前 project；
- 当前 project node；
- 当前 mini project；
- 当前 journal date；
- 默认 provider；
- detail 模式；
- 上一个上下文；
- 最近 Direct Action / Proposal apply 操作，用于 undo。

提示符示例：

```text
ta:/today>
ta:/projects/项目-韩国旅行>
ta:/projects/项目-韩国旅行/工作流/出行交通>
```

## Virtual Paths

支持语义路径：

```text
/
├── today
├── dashboard
├── inbox
├── waiting
├── someday
├── ideas
├── projects
├── mini
├── reviews
└── proposals
```

导航命令：

```text
pwd
ls
cd /today
cd /dashboard
cd /projects
cd /projects/项目-韩国旅行
cd 工作流/出行交通
cd 小任务/整理打车攻略
cd ..
cd -
tree
tree detail
tree plain
tree raw
show 123
show
open 123
find 关键词
```

别名：

```text
cd @today
cd @inbox
cd @p/项目-韩国旅行
cd @mini/整理打车攻略
```

路径无法解析时会输出候选，不会崩溃。

## Tree And Show

在 project root 下，`tree` 显示干净的 semantic project tree，只包含 `[目标]`、`[工作流]`、
`[小任务]`、`[资源]` 等结构化 marker 节点。普通备注和普通 TODO 不会显示成 `[未识别]`，也不会污染
`ls nodes`。

在 project node context 下：

```text
cd /projects/项目-韩国旅行
cd 整理打车攻略
tree
show
```

`tree` 只显示当前节点下面的 semantic subtree；如果没有结构化子节点，会提示使用 `show`。`show`
显示任意 semantic project node 的类型、id、所属项目、source location、简洁上级 context，以及该节点完整
Logseq raw subtree，包括普通块、TODO / DOING / WAITING / DONE 子块、properties 和 marker。支持的节点包括
目标、价值层、目标层、里程碑、工作流、具体事务、小任务、资源、成果、无成果、想法、反思、项目收件箱、
待澄清、注、AI注。标题重复时依赖稳定 node id / source location，不只靠 title 定位。

在 mini project 或 object context 下，省略目标的 `show` 会展示当前对象的 raw subtree：

```text
cd mini 28729
show
```

`tree detail` 临时显示 node id / type / line / children count。`tree plain` 或 `tree no-color`
禁用 ANSI；非 TTY 和 `NO_COLOR=1` 也会自动禁用颜色。

## Status Colors

Human-readable 视图会对 task marker 使用偏深色 ANSI：

```text
TODO     blue
DOING    magenta
WAITING  dark yellow
DONE     green
CANCELED gray
```

覆盖 `ls tasks`、`ls todo/doing/waiting/done`、`show` raw subtree、`tree raw`、write preview old/new、
`doing` / `done` / `wait` 操作结果、object context show 和 project node context show。`NO_COLOR=1`、非 TTY、
`ls --no-color`、`tree plain`、`tree no-color` 会输出纯文本。JSON / Agent structured 输出不加 ANSI。

## Today And Dashboard

`/today` 和 `/dashboard` 分工明确：

```text
/today      = 今日现场
/dashboard  = 全局行动态势
```

`/today` 默认只显示今日 journal 的事实和今天暴露出的对象，不再把全库 TODO / DOING 当作“今天要做”。它不做优先级判断，也不自动决定今天该做什么。

第一版 `/today` 子视图：

```text
ls journal
ls tasks
ls exposed
ls results
ls ideas
ls notes
ls all
```

今日 journal 不存在或为空时，`ls` 会提示空状态和预期 journal 文件位置。

`/dashboard` 承接原 `/today` 的全局驾驶舱职责。默认展示 active projects、active tasks、waiting、pending proposals、open reviews 和 ideas。

第一版 `/dashboard` 子视图：

```text
ls projects
ls tasks
ls active
ls waiting
ls proposals
ls reviews
ls ideas
ls all
```

Tab completion 和 fallback `complete cd /d` 支持 `/dashboard`。Agent 侧语义预留为：

```text
tm agent today-context      # 今日事实
tm agent dashboard-context  # 全局态势，后续补齐
```

## Direct Actions

用户在 shell 中明确输入的操作是 Direct Action，默认不走 Proposal，直接写回 Logseq，并记录可 undo 的操作历史。

创建类命令：

```text
todo "确认韩国打车 App 是否需要韩国手机号"
idea "返点公司可以做一个风险评分表"
mini "整理打车攻略"
resource "Kakao T 官方说明 https://example.com"
```

写回格式：

```text
- TODO ...
- **[想法]** ...
- **[小任务]** ...
- **[资源]** ...
```

状态、成果和注释：

```text
doing 123
done 123
wait 123 "等客服回复"
someday 123
result 123 "形成初稿"
noresult 123 "无需沉淀"
note 123 "先做最小版本"
ainote 123 "用户手动输入的 AI 注"
```

`WAITING` 使用 Logseq task marker。`done` 不强迫成果系统，但如果目标没有 `[成果]` / `[无成果]`，会提示可以补 `result` 或 `noresult`。

## Writeback Resolver

Direct Action 会根据当前上下文定位写回位置：

- `/today`：写入今日 journal；不存在则创建。
- `/inbox`：写入今日 journal，并附带 inbox 语义。
- `/projects/<project>`：写入项目页，按命令类型优先寻找 `[具体事务]`、`[想法]`、`[小任务]`、`[资源]`。
- `/projects/<project>/<node>`：写入当前 project node 下。
- `/mini/<mini>`：写入 mini project block 下。
- 无明确位置：fallback 到 today inbox，并明确输出位置。

Direct Action 只做 append-only 和 task marker 修改，不移动、删除、合并、重排项目页。

## Safety Preview

v1.5 增加写回位置预览。开启后，所有 Direct Action 写回前都会展示 graph、文件、目标、操作类型、内容和短 diff：

```text
preview on
where todo "查询 Kakao T 支付支持"
todo "查询 Kakao T 支付支持"
todo "只看位置" --preview
```

`where` 和命令级 `--preview` 不修改文件。`preview off` 只在目标明确时直接写；如果目标或位置有歧义，shell 仍会展示候选并等待用户选择。

## Target Selection

需要对象目标的命令会先解析精确 id；如果输入是标题片段，则按当前上下文优先搜索候选：

```text
done 打车
note 返点 "先确认汇率"
show 韩国
open 攻略
```

多候选时 shell 会展示编号、对象类型、状态、所属页面和行号，要求用户选择或取消。Resource / Reference 默认不会被状态命令当作 Action Item 处理，除非命令本身允许查看资源。

`cd` 也支持候选选择：

```text
cd /projects/韩国
cd 出行
cd -
cd ..
```

项目名或节点名不唯一时会显示候选；取消不会改变当前上下文。

## Operation History

```text
history
history --detail
ops
undo
undo last
undo 3
```

v1.5 会列出 session 内最近 Direct Action 和 shell 触发的 Proposal apply。每条记录包含 operation id、类型、目标、状态、是否可撤销和可选内容。`undo` 默认撤销最近可撤销操作，`undo <op>` 可撤销指定操作。

支持撤销：

- append TODO / idea / mini / resource；
- append note / ainote / result / noresult；
- task marker change；
- shell-triggered Proposal apply rollback。

如果操作缺少 rollback 信息，shell 会明确提示原因。

## Command History

```text
commands
clear-history
```

命令历史是 session-local。包含 `api_key`、`token`、`password`、`secret`、`sk-` 的命令会被脱敏记录；`exit` / `quit` 不记录。交互式终端中会尽量启用 Python 标准库 `readline` 的上下键历史；不可用时 shell 正常运行。

## Proposal Shortcuts

Provider / Agent 输出仍然只能生成 `suggested` Proposal，不能直接写 Logseq，不能直接 apply。

Human Shell 提供快捷审核：

```text
proposals
accept 1
reject 1
preview 1
apply 1
accept low
apply accepted
edit 1 content "新的内容"
edit 1 reason "新的理由"
edit 1 risk low
supersede 1 2
```

`proposals` 显示 session-local 编号，同时保留底层 Proposal id。高风险 Proposal 不参与批量 apply。

未 applied 的 Proposal 可在 shell 内编辑常见字段。编辑会写入底层 proposal event history；已 applied 或 rolled back 的 Proposal 不允许静默编辑。

## Clarify

在当前上下文运行：

```text
clarify
clarify status
clarify resume
clarify retry
clarify eval
clarify cancel
```

候选来自当前路径，例如 `/today`、`/inbox`、project 或 ideas。Shell 会逐条展示对象，并按基础问题逐条记录答案。支持：

```text
skip
quit
show
```

Provider 设置：

```text
provider
provider off
provider dry-run
provider mock
provider deepseek
```

`provider off` 只记录 Review Session 和回答；`dry-run` 展示 payload preview；`mock` / 真实 provider 只能生成 suggested Proposal。

`clarify` 会记录当前 review id。中断后可用 `clarify status` 查看 answered / skipped / failed / generated proposals，用 `clarify resume` 继续，用 `clarify retry` 重试 failed items，用 `clarify eval` 查看当前 review 质量摘要。

## Quality Shortcuts

Human Shell 提供质量报告快捷入口，不影响底层 `tm report ...` 命令：

```text
quality project-tree
quality mini
quality membership
quality clarify
quality all
q tree
```

项目上下文下报告会优先解释当前项目；全局上下文下输出 markdown 简版。

## Tab Completion

v1.5 使用 Python 标准库 `readline` 注册轻量 completer。支持：

- shell command；
- virtual path；
- project name；
- project node；
- mini project；
- object target；
- proposal session number；
- provider；
- quality report；
- `preview` / `detail` 的 `on` / `off`。

示例：

```text
cd /p<Tab>
cd /projects/韩<Tab>
cd 出<Tab><Tab>
done 打<Tab><Tab>
accept <Tab><Tab>
quality m<Tab><Tab>
provider d<Tab><Tab>
preview o<Tab>
```

唯一候选会补全；多候选交给 readline / libedit 的双 Tab 展示。平台行为不一致时，可用 fallback：

```text
complete cd 出
```

Completion 只读：不调用 provider、不写 Logseq、不修改数据库、不建议敏感值。候选最多展示前 20 个，中文候选可按前缀匹配；带空格或 `/` 的名称不会使 shell 崩溃，实际执行时建议用引号包住。

## V1.5.1 Additions

### Context Inventory & `ls` IDs

项目上下文下 `ls` 使用统一的 Context Inventory 显示可操作对象编号：

```text
ta:/projects/韩国旅行> ls
Project: 韩国旅行

Nodes:
  [block:...]  [工作流] 出行交通

Open Actions:
  #123 TODO 整理韩国打车攻略  (项目-韩国旅行:8)
  #124 DOING 写旅行攻略初稿  (项目-韩国旅行:12)

Ideas:
  #201 IDEA 返点公司风险评分表  (项目-韩国旅行:18)

Resources:
  #301 RESOURCE Kakao T 官方说明  (项目-韩国旅行:22)

Mini Projects:
  #401 MINI 整理打车攻略  (项目-韩国旅行:25)
```

`ls` 过滤器：
- `ls tasks` / `ls todo` / `ls doing` / `ls waiting` — 按状态过滤
- `ls ideas` / `ls resources` / `ls mini` / `ls nodes` / `ls proposals` — 按类型过滤
- `ls all` — 显示全部

`tree` 仍负责结构视图，`ls` 负责可操作对象列表。

### 相对补全

`/projects` 下支持相对项目名 Tab 补全：

```text
ta:/projects> 韩<Tab>      → 补全为 项目-韩国旅行
ta:/projects> cd 韩<Tab>   → 补全为 /projects/项目-韩国旅行
ta:/mini> 整<Tab>          → 补全 mini project 名
```

### `edit task` 命令

```text
edit task <target> title "新标题"     # 修改任务标题（保留 TODO/DOING marker）
edit task <target> content "新内容"   # 本轮等价于 title
edit task <target> status waiting    # 修改状态：todo/doing/waiting/done
```

安全规则：
- 只修改目标 block 首行，保留缩进、bullet、task marker、子块
- `edit task title/content` 始终显示 preview 并要求确认，不受 `preview on/off` 影响
- 支持 backup + undo
- 不移动、不删除、不重排、不破坏子块

### `edit` 命令路由

`edit proposal` 和 `edit task` 明确分开：

```text
edit proposal 1 content "..."   # 编辑 Proposal
edit task 123 title "..."       # 编辑 Task
edit 1 content "..."            # 兼容旧行为 (Proposal edit)
```

### Proposal 编号一致性

`proposals`、`ls proposals`、`accept`、`reject`、`edit proposal`、`apply` 共享同一 session-local 编号映射。不存在的编号提示先运行 `proposals` 或 `ls proposals`。

## Not In V1.5.1

Human Shell v1.5.1 不做复杂 TUI、全屏表格编辑、鼠标交互、文件系统 metadata 扫描、完整成果系统、Anki、项目树拖拽、移动块、删除块、合并块或重排、`edit task content` 与 `edit task title` 的差异化行为（本轮等价）。

## Real Graph Fix

### Object Context

Human Shell 支持进入对象：

```text
cd 3313
cd #3313
cd task 3313
cd mini 28729
```

进入 task / idea / mini project / resource / project 后，`ShellContext` 会记录当前 object id、type、title 和 source location。以下命令可省略 target：

```text
show
open
note "补充备注"
ainote "补充 AI 注"
result "形成成果"
noresult "无需成果"
done
doing
wait "等外部回复"
edit title "新的标题"
edit content "新的内容"
edit status waiting
```

状态命令只支持 task。mini project context 下 `todo "..."` 会追加到该 mini project 下；task context 下创建子任务仍按当前项目位置处理，本轮不实现复杂子任务系统。

### Tree / Ls / Find

- `tree` 用于看项目页层级，parser 已支持 Tab / mixed Tab+space 缩进。
- `ls` 用于看当前上下文可操作对象；项目下 `ls tasks` 会合并 `[relation]`、`[page]`、`[journal-link]`。
- `find <query>` 默认当前上下文优先，并隐藏同一 source location 的重复对象。
- `find --global <query>` 保留全局搜索。
- `find --all <query>` 分区显示 context 和 global。

### Writeback Consistency

Direct Action 写回后不再默认全量 sync。shell 会直接 patch 当前 object 的 status/title，并对被修改文件做 single-file refresh。`show` 可能显示：

```text
index: updated by shell writeback
```

这表示当前索引已由 shell 写回路径更新；需要全图校验时手动运行 `tm sync logseq`。

### Human Preview

默认 preview 不再展示大段 raw diff，而是显示 file、line、operation、scope、undo、old/new 或 new child。需要 raw unified diff 时：

```text
detail on
where todo "查询 Kakao T 支付支持"
```

### Clarify Modes

```text
clarify quick
clarify standard
clarify deep
clarify ai
clarify mode quick
```

`quick` 只问 1 个处理方式问题；`standard` 默认问 2-3 个关键问题；`deep` 保留原完整问题集；`ai` 调用 provider 生成最多 3 个 `questions_for_user`，只记录问题和回答，不直接写回、不 apply。
