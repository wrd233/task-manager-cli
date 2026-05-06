# Human Shell Real Graph Troubleshooting

## `tree` 全部平铺

真实 Logseq 文件常用 Tab 缩进。当前 parser 已支持 Tab / mixed Tab+space；如果仍平铺，先运行：

```bash
tm sync logseq
tm project tree <project>
```

确认项目页是 Logseq bullet 层级，而不是普通无 bullet 文本。

## `ls tasks` 为空

项目下 `ls tasks` 会合并三类来源：`[relation]`、`[page]`、`[journal-link]`。低置信关键词推断不会默认进入 `ls tasks`。如果 journal TODO 没出现，检查该 block 或父 block 是否包含 `[[项目名]]`。

## `done` 后 `show` 不一致

Direct Action 会直接 patch DB 并单文件 refresh。`show` 中出现：

```text
index: updated by shell writeback
```

表示状态来自 shell 写回路径。如果文件被外部工具同时修改，运行：

```bash
tm sync logseq
```

## `find` 结果重复或太全局

`find <query>` 默认当前上下文优先，并隐藏同一 file + line + title 的重复对象。使用：

```text
find --global <query>
find --all <query>
```

分别查看全局或分区结果。历史重复对象不会被自动删除；当前版本会避免继续因 task marker / title 变化制造重复。

## Direct Action 慢

`done` / `doing` / `wait` / `edit task title` / `todo` 等 shell 写回默认不再全量 sync，只刷新被修改文件。Proposal 批量 apply 或手动 `tm sync logseq` 仍可能扫描整个 graph。

## Preview 太长

默认 preview 显示 old/new 人类视图。需要 raw diff 时：

```text
detail on
where todo "..."
```

## Object Context

可以进入对象后省略 target：

```text
cd #3313
show
note "..."
done
edit title "..."
```

支持 task、idea、mini project、resource/reference 和 project。状态命令只支持 task。
