---
name: tm-extraction-audit
description: "结合 extraction-quality、测试、compileall 和 dry-run sync，对抽取质量进行中文审计。"
---

# tm-extraction-audit

用于检查抽取质量、回归风险和数据不变量，而不是给任务排序。

## 必跑命令

```bash
tm report extraction-quality --format json
python3 -m pytest
python3 -m compileall -q src
```

必要时追加：

```bash
tm sync logseq --dry-run --recent-journals 30
```

如 `tm` 不在 PATH，可使用：

```bash
PYTHONPATH=src python3 -m task_manager_cli.cli.main report extraction-quality --format json
PYTHONPATH=src python3 -m task_manager_cli.cli.main sync logseq --dry-run --recent-journals 30
```

## 必查项目

- `suspicious_ideas`
- `unlinked_tasks_ideas`
- `source_location_mismatches`
- `missing_definition_records`
- redaction 是否仍默认启用
- annotation count
- relation count
- 最近 sync run 是否异常

还应结合测试关注：

- idea marker 误抽
- `] xxx` 残片 idea
- `[[想法]]` / `[[随想]]` 误抽
- structural embed 造成重复 task
- `journal_exposure` 是否被正确保留

## 输出要求

输出应包含：

1. 抽取质量概况
2. 发现的问题或风险
3. 可能受影响的模块
4. 建议的修复或补测方向

## 禁止事项

- 不要修改 Logseq
- 不要默认执行真实 sync 写入
- 不要使用 `--no-redact`
