# Review Sessions

Review Session 记录一次澄清、审核或整理流程。它保存 review 范围、候选对象、关联 proposals、状态变化和用户操作历史，为下一轮 Clarify 做题流程提供可暂停、可恢复的外壳。

## Supported Types

- `inbox`：面向 inbox / 捕获池。
- `today`：面向今日上下文。
- `selected`：用户显式传入一组对象或记录 id。

本轮不实现完整交互式 Clarify，只实现 session 的创建、查询、状态和 proposal 关联。

## Status

- `open`
- `in_progress`
- `paused`
- `completed`
- `cancelled`

`paused` 是第一版的暂停 / 恢复状态保留。下一轮可以在此基础上加入 Clarify 问题、答案、跳过原因、provider 生成建议和批量审核 UI。

## CLI

```bash
tm review start --type inbox
tm review start --type today
tm review start --type selected --ids 12 34
tm review list
tm review show <review-id>
tm review proposals <review-id>
tm review status <review-id> paused
tm review close <review-id>
tm review close <review-id> --cancel
```

Review Session 不直接修改 Logseq。它只关联候选项和 proposals；具体变更仍由 Proposal 的 accept / apply / rollback 控制。

