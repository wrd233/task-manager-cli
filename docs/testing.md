# Testing

运行：

```bash
python3 -m pytest
```

测试 fixture 位于 `tests/fixtures/logseq_graph/`，包含：

- 项目页 `pages/项目-Alpha.md`
- Daily Log `journals/2026_05_03.md`
- 模板页 `pages/Template.md`

覆盖语法：

- `PARA:: [[PARA/Project]]`
- `[具体目标]`、`[具体事务]`、`[头脑风暴]`、`[反思]`
- TODO / DONE
- `[想法]` / `[随想]`
- Task 下方子块过程记录
- `id::`
- `((uuid))`
- `{{embed ((uuid))}}`
- 代码块中的 TODO
- 敏感信息和 private 标记

测试覆盖：

- block tree parser
- page properties
- task / project / idea extraction
- structural embed 不因 journal embed 重复生成任务
- ingest 幂等
- object context
- Agent JSON 可解析
- annotation add/list/update
- sensitive redaction
