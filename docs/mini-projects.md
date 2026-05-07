# Mini Projects

小任务是介于 Action Item 和正式 Project 之间的轻量组织单元。

它表示“需要多个 Action Item 才能完成、但还不到正式 Project 复杂度”的事务。可以把它理解为最小
PARA/Project，但它不等同于正式 Project。

## Boundary

- Action Item 是可执行、可流转的基础行动单位。
- Mini Project 是多个 Action Item 的轻量容器。
- Project 是更长期、更复杂、更有持续上下文的正式项目。
- Reference / Resource 是资源，不应被当作行动条目。
- Idea 可以孕育 Action Item 或 Mini Project，但不应自动被消耗掉。

## Logseq Marker

本轮识别：

```text
**[小任务]**
```

Round 3.5 同时识别非加粗 `[小任务]`。推荐写法仍是 `**[小任务]**`。

示例：

```text
- **[小任务]** 整理打车攻略
  - TODO 查询 Kakao T 使用方式
  - TODO 对比机场接送
  - **[资源]** Kakao T 官网
```

Daily Log 和 Project Page 中的 `**[小任务]**` 都会进入系统，object type 为 `mini_project`。
它不会被误认为正式 Project。

## Project Tree

Mini Project 可以出现在 readonly project tree view 中。它以 Logseq 原始缩进层级为主，下面可以挂
Action Items、Resources、Ideas、Annotations 和 Result Markers。

```bash
tm project tree 项目-韩国旅行
tm project tree 项目-韩国旅行 --format json
tm agent project-tree 项目-韩国旅行 --format json
```

Project Tree 默认只显示结构化 marker 节点。小任务下面的普通 TODO、普通备注和过程记录不会进入
semantic tree，也不会显示成 `[未识别]`；它们仍保留在 raw block subtree 中。

在 Human Shell 中进入 mini project 后，`show` 会展示完整 Logseq 子树：

```text
cd mini 28729
show
```

输出包含 mini id、所属项目、source location、简洁 context，以及当前 mini block 下的全部子块。`tree`
在 project node / mini 语境中仍用于查看结构化子节点；如果只想看内容和证据，应使用 `show`。

## Proposals

本轮支持与小任务相关的 Proposal 类型：

- `promote_to_mini_project` ：建议把复杂 Action Item 升级为小任务候选。
- `attach_to_mini_project` ：建议把对象挂到已有小任务。
- `create_mini_project` / `create_mini_project_node` ：预留或 append-only 最小写回。

这些 Proposal 默认不会直接创建复杂工作流。必须先 `accept`，再 `apply`。Provider 返回的建议只会成为
`suggested` Proposal。

## Supported In Round 3

- 识别 `**[小任务]**`。
- 抽取 `mini_project` 对象。
- 在项目树中展示小任务。
- 作为项目纳管 Proposal 的目标或结果。
- 支持 append-only 追加 `**[小任务]**` 标记并 rollback。

## Not Supported In Round 3

- 完整小任务编辑器。
- 深层嵌套任务管理。
- 自动拆分行动项。
- 自动创建正式 Project。
- 完整成果系统。

## Round 3.5 Quality Notes

小任务质量报告：

```bash
tm report mini-project-quality
```

报告覆盖：

- project page / journal 来源分布；
- 是否有 child action items；
- 是否包含 resource / result marker；
- 空小任务或默认标题；
- duplicate mini projects；
- 是否被误提升为正式 Project；
- source/location mismatch。

`[资源]` 或 `#reference` 语境下的内容不会进入 Action Item。`[想法]` 仍作为 Idea 语义保留，不会因为出现在项目页里就被强制转成 Task 或 Mini Project。

Suspicious mini project 只进入报告，不自动重构项目页。典型 suspicious cases 包括无子块、标题为空、重复标题和 source/location 不一致。
