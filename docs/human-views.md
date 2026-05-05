# Human Views

`tm view ...` 是给人快速扫一眼的短视图，和 Agent/report 层分开。

## Commands

```bash
tm view today
tm view projects
tm view project <name-or-id>
tm view tasks
tm view ideas
tm view inbox
```

通用选项：

```bash
--brief
--detail
--limit 20
```

## Principles

- 面向人，不面向 Agent。
- 默认短、清楚、分组良好。
- 默认不展示 metadata、confidence、完整 linked records、JSON。
- 每条通常一行，`--detail` 最多增加一行信号或记录片段。
- 只呈现注意力信号，不判断优先级。
- 不修改 Logseq。
- 不写 annotation。

## Relationship To Other Layers

- `tm agent ...`：给外部 Agent 的结构化上下文。
- `tm report ...`：诊断和轻量报告。
- `tm export ...`：完整调试 dump。
- `tm view ...`：给人看的短视图。

需要深挖时，用：

```bash
tm show <id>
tm context <id>
```
