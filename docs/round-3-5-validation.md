# Round 3.5 Validation

Round 3.5 是项目树、小任务和项目纳管的质量验证轮。它不新增 Human Shell，也不做项目页自动重构；目标是在更接近真实 Logseq 使用习惯的临时 graph 上确认解析、候选和写回边界可靠。

## Temporary Graph

首选复制真实 Logseq 的一个子集到临时目录：

```bash
export TM_APP_DIR=/tmp/tm-round35/app
export TM_DATABASE_PATH=/tmp/tm-round35/tm.sqlite3
export TM_LOGSEQ_GRAPH=/tmp/tm-round35/graph
tm sync logseq --graph /tmp/tm-round35/graph
```

建议样本规模：

- 5-10 个项目页；
- 10-30 个 journal；
- 同时包含结构规范、结构凌乱和空项目页；
- 包含 `**[小任务]**` / `[小任务]`、资源、成果、想法、待澄清；
- journal 中包含 `[[项目名]]`、`#inbox`、`#waiting`、`#reference`、`#someday`；
- 包含不应被识别为 Project 的普通页面。

如果不能使用真实子集，可以扩展 fixture graph。最终报告需要明确使用的是真实子集临时 graph 还是扩展 fixture graph。

## Commands

```bash
tm sync logseq --graph /tmp/tm-round35/graph
tm report project-tree-quality --format markdown
tm report project-tree-quality --format json
tm report mini-project-quality --format markdown
tm report membership-quality --format markdown
tm clarify project <project> --provider dry-run
tm clarify project <project> --provider mock
tm clarify eval <review-id>
```

`tm project tree-quality` 和 `tm project membership-quality` 是同一组报告的 project 命令别名。

## Project Tree Quality

重点检查：

- recognized project pages 是否接近预期；
- skipped non-project pages 是否包含普通页面；
- node type distribution 是否合理；
- projects with empty tree 和 suspicious tree 是否可解释；
- source/location mismatch count 是否为 0；
- resource / idea / result 节点是否没有被误归类为行动项；
- large project page truncation status 是否提醒 payload 摘要需要截断。

## Mini Project Quality

重点检查：

- project page 与 journal 中的小任务都能识别；
- 小任务下 TODO 仍是行动项；
- 小任务下 `[资源]` 不进入行动流；
- 小任务没有被提升为正式 Project；
- duplicate 和 suspicious examples 是否可解释。

## Membership Quality

报告会区分 high / medium / low confidence。低置信候选只出现在 candidate / ambiguous list，不直接成为可 apply Proposal。

重点检查：

- Daily Log 中 `[[项目名]]` 产生高置信候选；
- title keyword 是中置信；
- weak keyword 是低置信且不自动 proposal；
- active duplicate proposal 被抑制；
- applied relation 不重复建议；
- resource / reference 使用 resource proposal，不进入行动流；
- idea 使用 idea-to-project，不被强迫转 task。

## Clarify Project

`clarify project` payload 默认只包含项目树短摘要：project metadata、少量 node id、node type、title、depth 和 line。默认不发送完整项目页原文、全量 linked records 或整页 Markdown。

真实 provider 验证建议先跑：

```bash
tm clarify project <project> --provider dry-run --format json
tm clarify project <project> --provider mock
```

确认 payload 短、proposal 类型保守、没有把 Resource 当 Action、没有把 Idea 强行变 Task 后，再少量使用真实 provider。

## Writeback Verification

只允许验证 append-only：

- 追加 `[AI注]`；
- 追加 `[待澄清]`；
- 在项目节点下追加 block ref；
- 追加 `**[小任务]**`；
- 追加 `**[资源]**`。

每次都必须走 preview、accept、apply、resync、rollback。连续多次写回同一文件时，每次 apply 都会创建唯一备份，rollback 按 proposal 的备份恢复。

## Round 4 Gate

建议进入 Round 4 前满足：

- `python3 -m pytest` 通过；
- `python3 -m compileall -q src` 通过；
- `git diff --check` 通过；
- 三个 quality report 无不可解释的高风险异常；
- source/location mismatch 为 0 或有明确解释；
- 低置信纳管候选不直接 proposal；
- append-only rollback 在临时 graph 上通过；
- Human Shell 未实现。

## Human Shell Boundary

Human Shell / `tm shell` / `ta` 暂不实现。本轮只验证项目结构、纳管关系和 append-only 写回安全性。
