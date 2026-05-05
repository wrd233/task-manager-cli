# Provider Evaluation

本文说明如何在临时 Logseq graph 中验证真实 provider 是否适合进入日常 Clarify。

## Temporary Graph

不要对真实主 graph 做首次验证。建议复制 fixture 或创建临时 graph：

```bash
export TM_APP_DIR=/tmp/tm-provider-eval/app
export TM_DATABASE_PATH=/tmp/tm-provider-eval/tm.sqlite3
export TM_LOGSEQ_GRAPH=/tmp/tm-provider-eval/graph
tm sync logseq
```

## Test Items

建议准备 20-50 条条目，覆盖普通 TODO、WAITING 候选、 `**[想法]**` 、设计型 idea、 `#inbox` 、
`#someday` 、 `#reference` 、 `**[待澄清]**` 、DONE 缺少 `**[成果]**` 、DONE 已有 `**[成果]**`
、敏感条目、项目引用和资源链接。

## Flow

```bash
tm provider doctor --no-call
tm provider doctor --provider deepseek
tm clarify selected --ids 12 13 14 --answer "逐条澄清回答" --provider dry-run --format json
tm clarify selected --ids 12 13 14 --answer "逐条澄清回答" --provider deepseek
tm clarify eval <review-id>
```

只 accept/apply 一个低风险或中风险 Proposal 到临时 graph：

```bash
tm proposal accept <proposal-id>
tm proposal show <proposal-id> --preview
tm proposal apply <proposal-id> --yes
tm sync logseq
tm proposal rollback <proposal-id>
```

## Quality Metrics

重点看 success、failed、parse error、generated proposal count、proposal type distribution、risk
distribution、average confidence、high risk proposal count、accepted / rejected / edited /
applied / rollback count、suspicious suggestions、average latency 和 token usage。

## Bad Suggestion Types

常见坏建议：

- 过度生成 `**[AI注]**` ；
- 把 reference 当 action；
- 把 idea 强行转 task；
- 对 waiting 判断过度积极；
- DONE 后乱加成果；
- 生成不可应用 target；
- 建议高风险删除 / 合并 / 大规模重排。

## Prompt Tuning

如果坏建议多，优先调 prompt：明确“少量、高置信、保守”；强化 reference / idea 边界；限制每个
item 的 proposal 数量；要求 reason 简短；降低高风险建议倾向；要求不输出 chain-of-thought。

只有当 parse error 低、建议不过度、reference / idea / waiting 判断稳定，并且 rollback
验证可靠时，才建议进入 Round 3。
