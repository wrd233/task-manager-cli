---
name: tm-agent-today
description: "基于 today-context、近期未完成任务和活跃项目，为外部 Agent 提供中文的今日行动分析工作流。"
---

# tm-agent-today

用于回答“今天最值得处理什么”这类问题。

## 目标

基于 `task-manager-cli` 的事实证据，输出今日最值得处理的 3-5 件事。

必须明确说明：

- 优先级是 Agent 判断，不是 CLI 判断
- 结论来自 `tm` 提供的上下文证据
- 禁止修改 Logseq
- 禁止自动写 annotation

## 必跑命令

```bash
tm agent today-context --days 14 --format json
tm report recent-unresolved-tasks --days 14 --format json
tm report active-projects --format json
```

如果 `tm` 不在 PATH，可使用等价 fallback：

```bash
PYTHONPATH=src python3 -m task_manager_cli.cli.main agent today-context --days 14 --format json
PYTHONPATH=src python3 -m task_manager_cli.cli.main report recent-unresolved-tasks --days 14 --format json
PYTHONPATH=src python3 -m task_manager_cli.cli.main report active-projects --format json
```

## 分析步骤

1. 阅读 `today-context` 中的 `recent_unfinished_tasks`、`recent_ideas`、`active_projects` 和 `signals`。
2. 用 `recent-unresolved-tasks` 交叉确认最近仍未完成且在 journal 中有暴露的任务。
3. 用 `active-projects` 识别近期仍在活动、但可能缺少推进动作的项目。
4. 将结论拆成“证据”和“建议”，不要把主观判断伪装成 CLI 原始输出。

## 输出格式

输出应包含：

1. 今日最值得处理的 3-5 件事
2. 每件事对应的证据
3. 为什么现在值得处理
4. 哪些判断是 Agent 推断而非 CLI 明示
5. 如有需要，列出 1-2 个待用户确认的问题

## 禁止事项

- 不要修改 Logseq
- 不要自动调用 `tm annotation add`
- 不要使用 `--no-redact`
- 不要直接读取全量 dump 代替 `tm agent today-context`
