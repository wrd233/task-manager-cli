---
name: tm-inbox-review
description: "基于 inbox-context 审阅最近想法，将其分类为项目候选、事务候选、保留、归档或疑似误抽。"
---

# tm-inbox-review

用于整理最近的 idea inbox，而不是直接替用户建任务或改 Logseq。

## 必跑命令

```bash
tm agent inbox-context --days 30 --format json
```

如 `tm` 不在 PATH，可使用：

```bash
PYTHONPATH=src python3 -m task_manager_cli.cli.main agent inbox-context --days 30 --format json
```

## 分类标准

把 ideas 尽量分到以下类别：

- 可转项目
- 可转事务
- 可并入已有项目
- 暂时保留
- 可归档
- 疑似误抽

分类时结合：

- `unlinked_ideas`
- `possible_project_links`
- `suspicious_ideas`
- 定义记录与最近 journal 暴露
- 是否具有明确行动性、范围和持续性

## 输出要求

每条重要 idea 至少给出：

1. 分类结果
2. 证据
3. 推荐动作
4. 如是“疑似误抽”，说明为什么可疑

## 禁止事项

- 禁止自动创建任务
- 禁止修改 Logseq
- 禁止自动写 annotation
- 禁止使用 `--no-redact`
