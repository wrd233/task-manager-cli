# Human Shell

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
cd /projects
cd /projects/项目-韩国旅行
cd 工作流/出行交通
cd 小任务/整理打车攻略
cd ..
cd -
tree
show 123
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

## Not In V1.5

Human Shell v1.5 不做复杂 TUI、全屏表格编辑、鼠标交互、文件系统 metadata 扫描、完整成果系统、Anki、项目树拖拽、移动块、删除块、合并块或重排。
