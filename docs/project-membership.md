# Project Membership

项目纳管不是移动 Logseq 块。

项目纳管表示：把散落的 Action Item / Idea / Resource / Mini Project 建立到某个 Project 或
Project Node 的语义关系。Round 3 默认优先更新内部 relation，不重排项目页。

## Candidate Confidence

高置信来源：

- 条目位于 Project Page 中。
- 条目位于 Project Tree Node 下。
- 条目明确引用项目页面。
- 条目中有 `[[项目名]]`。

中置信来源：

- 条目标题包含项目关键词。
- Clarify 回答指定属于某项目。
- Provider 建议属于某项目。

低置信来源：

- 仅语义相似。
- 仅弱关键词相关。
- 仅历史上相近出现。

低置信候选应进入报告或问题，不应直接生成可 apply 的 Proposal。

## Proposal Types

Round 3 支持：

- `link_to_project`
- `link_to_project_node`
- `link_idea_to_project`
- `link_resource_to_project`
- `promote_to_mini_project`
- `attach_to_mini_project`

Proposal 内容包含：

- target object；
- target project；
- target project node，可选；
- relation type；
- reason；
- confidence；
- risk；
- writeback suggested；
- source evidence。

## Commands

```bash
tm project propose-membership --object 12 --project 项目-韩国旅行
tm project propose-membership --object 12 --project 项目-韩国旅行 --node-id block:abc
tm project promote-mini 12 --reason "需要多个行动项"
tm proposal accept 1
tm proposal apply 1
tm proposal rollback 1
```

`apply` 默认写入内部 relation，并记录 `applied_record`。Rollback 会删除本次创建的 relation，或恢复
被本次 apply 更新前的 relation metadata。

## Writeback Boundary

本轮允许很有限的 append-only 写回：

- 在目标节点下追加 block ref。
- 追加 `**[AI注]**`。
- 追加 `**[待澄清]**`。
- 追加最小 `**[小任务]**` 节点。
- 追加 `**[资源]**` 引用。

禁止：

- 移动原块。
- 删除块。
- 合并块。
- 重排项目树。
- 自动改写标题。
- 批量重构项目页。

## Provider Boundary

Provider 可以建议纳管，但只能返回 proposal candidates。系统会校验 type、risk、target 和 payload。
Provider 不能直接创建 relation，不能直接写 Logseq，不能直接 apply。
