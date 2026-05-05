# Testing

运行：

```bash
python3 -m pytest
```

测试 fixture 位于 `tests/fixtures/logseq_graph/`，包含：

- 项目页 `pages/项目-Alpha.md`
- 项目页 `pages/项目-韩国旅行.md`
- 项目页 `pages/任务-APM平台.md`
- 项目页 `pages/学习-日语.md`
- Daily Log `journals/2026_05_03.md`
- Daily Log `journals/2026_05_01.md`
- Daily Log `journals/2026_05_02.md`
- 模板页 `pages/Template.md`
- 模板页 `pages/模板-DailyGoals.md`

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
- `[[想法]]` / `[[随想]]` 不误抽
- journal wiki link 到项目
- journal block ref 作为 exposure

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
- source/location/definition consistency
- Agent today/project/inbox context
- extraction-quality report

新增回归样例时优先扩展 fixture，再补测试断言。对抽取 bug，至少断言对象标题、definition record、canonical location 和 relation。
