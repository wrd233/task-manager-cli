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

## Undo

```text
undo
```

v1 支持撤销最近一次 Direct Action 写回和 shell 触发的 Proposal apply rollback。连续写回同一文件时，每次 apply 都有独立备份。

如果操作缺少 rollback 信息，shell 会明确提示原因。

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
```

`proposals` 显示 session-local 编号，同时保留底层 Proposal id。高风险 Proposal 不参与批量 apply。

## Clarify

在当前上下文运行：

```text
clarify
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

## Not In V1

Human Shell v1 不做复杂 TUI、全屏表格编辑、自动补全、复杂历史、文件系统 metadata 扫描、完整成果系统、Anki、项目树拖拽或重排。
