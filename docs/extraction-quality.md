# Extraction Quality Report

运行：

```bash
tm report extraction-quality
tm report extraction-quality --format json
```

## Metrics

- `objects` / `projects` / `tasks` / `ideas`：对象数量。
- `records`：SourceRecord 数量。
- `relations`：对象级 relation 数量。
- `unlinked_tasks_ideas`：没有 `belongs_to` relation 的 task/idea。这个值不是越低越好，宁缺毋滥。
- `suspicious_ideas`：标题过短、以 `]` 开头、或 extraction metadata 标记可疑的 idea。
- `source_location_mismatches`：object canonical location 与 definition record location 不一致。
- `missing_definition_records`：缺少 definition SourceRecord 的对象。
- `annotations`：内部批注数量。
- `sync_runs`：同步次数。

## Interpretation

`source_location_mismatches` 和 `missing_definition_records` 应长期为 0。`suspicious_ideas` 应尽量为 0。`unlinked_tasks_ideas` 可以存在，因为 journal 中的 free idea 和无项目任务不应被强行关联。

报告用于诊断抽取质量，不用于判断任务优先级。
