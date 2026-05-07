# Project Restructure Migration

This migration path normalizes historical Logseq project pages to the current Project model.

## Rules

- Back up the full graph before writing.
- Preserve original blocks, TODO markers, links, `id::` properties, and child subtrees.
- Standardize legacy section aliases.
- Add missing standard sections conservatively.
- Do not delete, merge, or reorder user content.
- Put uncertain future work in project inbox or clarify/proposal flow.

## Standard Sections

```text
[目标]
[项目收件箱]
[具体事务]
[小任务]
[资源]
[成果]
[想法]
[反思]
```

## Legacy Aliases

```text
[具体目标] -> [目标]
[资源列表] -> [资源]
[头脑风暴] -> [想法]
[随想] -> [想法]
[心得]/[复盘]/[经验] -> [反思]
[产出]/[交付物] -> [成果]
```

## Audit Outputs

The migration writes:

```text
reports/project-restructure/summary.md
reports/project-restructure/project_restructure_manifest.json
reports/project-restructure/diff_summary.md
reports/project-restructure/project_health_comparison.md
reports/project-restructure/rollback.sh
```

`rollback.sh` restores the full graph from the backup snapshot.
