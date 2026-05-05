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
