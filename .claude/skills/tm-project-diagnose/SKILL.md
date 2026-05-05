---
name: tm-project-diagnose
description: "围绕单个项目运行 project-context 诊断，输出状态、证据、卡点和下一步建议的中文工作流。"
---

# tm-project-diagnose

用于诊断某个项目当前的进展、卡点和下一步动作。

## 必跑命令

项目明确时：

```bash
tm agent project-context "$ARGUMENTS" --format json
```

如果项目名不明确、项目可能有多个候选，先运行：

```bash
tm report active-projects --format json
```

如 `tm` 不在 PATH，可使用：

```bash
PYTHONPATH=src python3 -m task_manager_cli.cli.main agent project-context "$ARGUMENTS" --format json
PYTHONPATH=src python3 -m task_manager_cli.cli.main report active-projects --format json
```

## 分析重点

必须检查：

- 项目元信息与 definition record
- `task_stats`
- `unfinished_tasks`
- `recent_done_tasks`
- `recent_ideas`
- `relations`
- `recent_journal_exposures`
- `signals`
- 现有 annotations

还要主动关注以下线索：

- 长期未完成 TODO
- 最近有无完成闭环
- 最近记录是否持续出现但缺少推进
- 是否存在 `[问题]`、`[待澄清]`、`blocked`、`阻塞`、`卡住`
- idea 是否明显多于可执行任务
- 是否出现“有目标但无未完成任务”的异常状态

## 输出要求

输出应包含：

1. 项目当前状态
2. 关键证据
3. 可能卡点
4. 建议下一步
5. 不确定点或需用户确认的问题

必须清楚区分：

- CLI 直接提供的事实
- Agent 基于事实做出的解释

## 禁止事项

- 禁止写回 Logseq
- 禁止自动写 annotation
- 禁止使用 `--no-redact`
