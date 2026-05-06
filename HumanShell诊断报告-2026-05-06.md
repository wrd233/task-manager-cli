# Human Shell 真实使用问题诊断报告

> 日期：2026-05-06  
> 仓库：task-manager-cli (main, 11ebf7d)  
> Graph：/Users/wangrundong/logseq/Logseq_File  
> DB：~/.task-manager-cli/task_manager.sqlite3 (130MB)  
> 状态：**本轮仅诊断，不修改代码**

---

## 目录

1. [环境概览](#1-环境概览)
2. [Issue 1: ls tasks / ls todo 为空](#2-issue-1-ls-tasks--ls-todo-为空)
3. [Issue 2: tree 全部平铺](#3-issue-2-tree-全部平铺)
4. [Issue 3: done 后 show 状态不更新](#4-issue-3-done-后-show-状态不更新)
5. [Issue 4: find 不按上下文 + 重复对象](#5-issue-4-find-不按上下文--重复对象)
6. [Issue 5: Direct Actions 慢 (6-8s)](#6-issue-5-direct-actions-慢-68s)
7. [Issue 6: cd 不支持按 ID 导航](#7-issue-6-cd-不支持按-id-导航)
8. [Issue 7: object context 下 note 不能省略 target](#8-issue-7-object-context-下-note-不能省略-target)
9. [Issue 8: preview 不可读](#9-issue-8-preview-不可读)
10. [Issue 9: object context 下 edit title/status 不能省略 target](#10-issue-9-object-context-下-edit-titlestatus-不能省略-target)
11. [Issue 10: clarify 太冗余](#11-issue-10-clarify-太冗余)
12. [数据库发现](#12-数据库发现)
13. [Logseq 文件发现](#13-logseq-文件发现)
14. [风险评估](#14-风险评估)
15. [建议修复优先级](#15-建议修复优先级)

---

## 1. 环境概览

### 1.1 仓库信息

```
Branch:   main
Commit:   11ebf7d Polish human shell ergonomics and tab completion
Status:   clean
Python:   3.9.6
pytest:   8.4.2
```

### 1.2 关键文件清单

| 文件 | 说明 |
|------|------|
| `src/task_manager_cli/shell/inventory.py` (581行) | ContextInventory — 为当前路径构建结构化列表 |
| `src/task_manager_cli/shell/service.py` | HumanShellService — 命令路由、上下文管理、所有 shell 命令 |
| `src/task_manager_cli/shell/completion.py` | ShellCompleter — Tab 补全 |
| `src/task_manager_cli/projects/tree.py` | ProjectTreeService — 树构建与渲染 |
| `src/task_manager_cli/adapters/logseq/parser.py` | Logseq 块解析器 |
| `src/task_manager_cli/writes/logseq_writer.py` | LogseqWriter — 写回预览与应用 |
| `src/task_manager_cli/ingest/merger.py` | Merger — 幂等合并 |
| `src/task_manager_cli/ingest/sync.py` | SyncService — 全量同步 |
| `src/task_manager_cli/clarify/service.py` | ClarifyService — 澄清流程 |
| `src/task_manager_cli/storage/repositories.py` | Repository — SQLite 查询封装 |

### 1.3 配置文件

```json
{
  "app_dir": "/Users/wangrundong/.task-manager-cli",
  "database_path": "/Users/wangrundong/.task-manager-cli/task_manager.sqlite3",
  "logseq_graph_path": "/Users/wangrundong/logseq/Logseq_File",
  "default_redact": true
}
```

注意：`write_mode` 未配置（默认 `"disabled"`），`provider_name` 未配置（默认 `"mock"`）。

### 1.4 数据库表结构

```
annotations          proposals            schema_meta        
locations            relations            source_records     
object_record_links  review_events        sync_runs          
objects              review_items         write_proposals    
proposal_events      review_sessions      
```

核心表：
- `objects`: 抽取的对象（project, task, idea, mini_project 等），通过 `(canonical_source, source_item_id)` 唯一约束
- `source_records`: 原始 Logseq block 记录，通过 `(source_type, source_item_id)` 唯一约束
- `relations`: 对象间关系，`from_object_id → to_object_id`
- `locations`: 文件位置（page_name, journal_date, line_start, block_uuid）

### 1.5 Shell 架构

```
HumanShellService
├── ShellContext (path, project_ref, project_node_id, mini_ref, ...)
├── inventory.py :: build_inventory()
│   ├── _inventory_project_context()  ← 最复杂的上下文
│   │   ├── 项目级: _get_project_children() → belongs_to 关系扫描
│   │   └── 节点级: _add_attributed_objects() → relation > source_path > wiki_link
│   ├── _inventory_today()
│   ├── _inventory_inbox()
│   └── ...
├── cd → _resolve_path() → 路径名解析（不支持数字 ID）
├── find → 全局 SQL LIKE 搜索（不按上下文过滤）
├── tree → ProjectTreeService.build() + render_markdown()
├── note / done / wait → resolve_target() + _apply_direct_preview() + _resync()
├── _resync() → SyncService.sync_logseq() → 全量重扫
└── preview → _location_preview() → 原始 unified diff (截断1200字符)
```

---

## 2. Issue 1: ls tasks / ls todo 为空

### 2.1 用户描述

```
ta:/projects/课程-ECE564-Mobile-Application> ls tasks
Project: 课程-ECE564-Mobile-Application
No tasks found.

ta:/projects/课程-ECE564-Mobile-Application> ls todo
Project: 课程-ECE564-Mobile-Application
No todo found.
```

### 2.2 调查过程

**第一步：复现**

程序化调用 shell，在当前 DB 上执行：

```python
svc.run_line('cd /projects/课程-ECE564-Mobile-Application')
print(svc.run_line('ls tasks'))
print(svc.run_line('ls todo'))
```

输出（截取）：
```
Open Actions:
  #18536 TODO 结合之前的课程仓库，对相关知识点进行整理  (课程-ECE564-Mobile-Application:522)
  #18535 TODO 明确项目要做的内容，建立基础的完成和拓展的完成  (课程-ECE564-Mobile-Application:521)
  #18533 TODO 完成项目Readme的撰写  (课程-ECE564-Mobile-Application:514)
  ...
```

**当前 ls tasks 实际上返回了任务！** 说明该问题现已不重现，可能是用户最初尝试时 DB 尚未完全同步。

**第二步：分析 inventory 逻辑**

`_inventory_project_context` (inventory.py:304-369) 在项目级调用 `_get_project_children` (line 524)：

```python
def _get_project_children(conn, repo, project_id):
    children = []
    for obj_type in ("task", "idea", "mini_project", "reference", "resource"):
        rows = repo.list_objects(obj_type, limit=MAX_LIMIT)
        for row in rows:
            rels = repo.relations_for_object(obj_id)
            belongs = any(
                r.get("relation_type") == "belongs_to" and
                str(r.get("to_id")) == str(project_id)
                for r in rels
            )
            if belongs:
                children.append(row)
    return children
```

**关键点：** `ls tasks` 的数据源只是 `belongs_to` 关系的对象。这意味着：
- journal 中引用项目的 TODO **不会** 自动出现在项目下（除非有 belongs_to 关系）
- 即使 TODO 在项目页内，也需要有 belongs_to 关系

**第三步：统计 belongs_to 关系覆盖**

```sql
SELECT COUNT(*) FROM objects WHERE object_type='task' AND status='todo';
→ 1758

SELECT COUNT(*) FROM relations WHERE relation_type='belongs_to';
→ 1036
```

仅 463 个 (26%) todo task 有 belongs_to 关系。

**第四步：检查项目下的 belongs_to 关系**

```sql
SELECT o.id, o.title FROM objects o
JOIN relations r ON r.from_object_id=o.id
WHERE r.to_object_id=1534 AND r.relation_type='belongs_to'
AND o.object_type='task' AND o.status='todo' LIMIT 20;
```

返回 20+ 结果，包括 #15141 (结合之前的课程仓库...)、#18536 等。

**第五步：检查 journal TODO 是否有 belongs_to**

```sql
SELECT * FROM relations WHERE from_object_id IN (3313, 6705);
→ (空)
```

Journal 中的 TODO (#3313, #6705) **没有 belongs_to 关系**。这意味着即使在项目内执行 `ls tasks`，这些 journal TODO 也不会出现。

### 2.3 根因

1. **journal 暴露的 TODO 不会被收录**：`_get_project_children` 只看 `belongs_to` 关系
2. **belongs_to 覆盖不足**：仅 26% 的 todo task 有 belongs_to 关系
3. **可能的时序问题**：用户初次使用 `ls tasks` 时 DB 可能未完全同步（但后续 resync 后恢复）

### 2.4 建议修复

- 在 `_inventory_project_context` 中增加两个数据源：
  - 项目页内直接包含的 block（通过 source_path 匹配）
  - journal 中通过 wiki_link / block_ref 引用该项目的 TODO
- 为 journal_exposure 自动建立 `belongs_to` 关系（可低置信度）

---

## 3. Issue 2: tree 全部平铺

### 3.1 用户描述

所有项目调用 `tree` 都看到节点列表，没有层级缩进。

### 3.2 调查过程

**第一步：检查 tree 构建代码**

`ProjectTreeService.build()` (tree.py:58-91)：

```python
parsed = parse_logseq_file(path, ...)
roots = [self._node(block, source_map) for block in parsed.blocks if block.parent is None]
```

**关键行**：`if block.parent is None` 决定哪些块成为根节点。

**第二步：检查 parser 中 parent 的设置逻辑**

`parse_logseq_file()` (parser.py:156-188)：

```python
def indent_level(line: str) -> int:
    leading = len(line) - len(line.lstrip(" "))
    return leading // 4

for line in lines:
    block = LogseqBlock(raw=line, indent=indent_level(line), ...)
    while stack and stack[-1].indent >= block.indent:
        stack.pop()
    if stack:
        stack[-1].add_child(block)  # 设置 parent
    blocks.append(block)
    stack.append(block)
```

**关键函数 `indent_level` 第 128-130 行**：

```python
def indent_level(line: str) -> int:
    leading = len(line) - len(line.lstrip(" "))
    return leading // 4
```

**`lstrip(" ")` 只去除空格，不去除 Tab！**

**第三步：验证 Tab vs 空格行为**

```python
tab_line = '\t\t- **[目标]** 有着良好的参与度'
space_line = '        - TODO 使用空格缩进'

# Tab 缩进
len(tab_line) - len(tab_line.lstrip(" "))  → 0    ← 错误！

# 空格缩进
len(space_line) - len(space_line.lstrip(" "))  → 8  → indent_level=2  ← 正确
```

**第四步：检查真实 Logseq 文件的缩进字符**

```
     1  PARA:: [[PARA/Archive]]         ← 空格缩进（非 bullet 行无关）
     9  - TODO [#A] Mobile...           ← 0 级 bullet
    10    type:: [[项目]]                ← 2 空格（属性块）
    11  \t\t- **[具体目标]**...          ← Tab 缩进！
    12  \t\t\t- **[目标]** 有着良好...   ← 双层 Tab 缩进！
```

**Logseq 默认使用 Tab 缩进。** indent_level 对 Tab 行返回 0，因此所有 Tab 缩进的行都被视为 depth=0，`parent is None` 为 True → 全部成为根节点。

**第五步：验证问题的普遍性**

| 项目 | 节点总数 | 根节点数 | 最大深度 |
|------|---------|---------|---------|
| 课程-ECE564-Mobile-Application | 287 | 282 | 1 |
| 学习-南大PA | 99 | 99 | 1 |
| 毕业设计 | 998 | 998 | 1 |

**全部平铺** — 这不是个别项目的问题，而是所有使用 Tab 缩进的 Logseq 项目的系统性问题。

**第六步：确认测试为什么通过**

测试文件 `tests/test_human_shell.py` 创建临时 graph 时使用**空格缩进**：

```python
(pages / "项目-韩国旅行.md").write_text(
    "PARA:: [[PARA/Project]]\n\n"
    "- **[工作流]** 出行交通\n"
    "    - **[具体事务]**\n"     ← 4 空格缩进
    "        - TODO 已有项目任务\n",  ← 8 空格缩进
)
```

测试使用空格缩进 → 测试通过。真实 graph 使用 Tab 缩进 → 问题出现。

### 3.3 根因

**`indent_level()` (parser.py:128-130) 仅处理空格缩进，但 Logseq 使用 Tab 缩进。** Tab 缩进的行 indent_level 返回 0 → 全部成为根节点 → 树完全平铺。

### 3.4 建议修复

修改 `indent_level` 同时处理 Tab 和空格：

```python
def indent_level(line: str) -> int:
    # 去除所有前导空白
    stripped = line.lstrip()
    leading = len(line) - len(stripped)
    if leading == 0:
        return 0
    # 数 Tab 和空格
    leading_ws = line[:leading]
    tabs = leading_ws.count('\t')
    spaces = len(leading_ws) - tabs
    return tabs + spaces // 4
```

或更简单地，使用 `lstrip()`（去除所有空白）替代 `lstrip(" ")`。

---

## 4. Issue 3: done 后 show 状态不更新

### 4.1 用户描述

```
ta:/projects/...> done 3313
#3313 -> DONE (op #1)
该条目已完成，但没有成果标注...

ta:/projects/...> show 3313
#3313 task todo 上次移动的那个他们反应上不去，看一下情况    ← 仍是 todo！
```

### 4.2 调查过程

**第一步：检查文件是否真的被修改**

```bash
nl -ba /Users/wangrundong/logseq/Logseq_File/journals/2026_04_07.md | sed -n '43,50p'
```

输出：
```
43  ...
44  - 以上是我归纳的几个问题...
45  - **[几个问题]**
46  - **[注]** 上次的光衰还是link的相关的...
47  - DONE 上次移动的那个他们反应上不去，看一下情况      ← 文件已改为 DONE！
48  - ## 下午
```

**文件修改成功。** 写回生效了。

**第二步：检查 DB 中的 object**

```sql
SELECT o.id, o.object_type, o.title, o.status, o.source_item_id, l.line_start
FROM objects o LEFT JOIN locations l ON l.id=o.canonical_location_id
WHERE o.id IN (3313, 6705);
```

| id | object_type | title | status | source_item_id | line_start |
|----|------------|-------|--------|----------------|------------|
| 3313 | task | 上次移动的那个... | **todo** | `block:journals/2026_04_07.md:47:87f5bfa7acdf28eb` | 47 |
| 6705 | task | 上次移动的那个... | **done** | `block:journals/2026_04_07.md:47:0cd7d5e51f3e964d` | 47 |

**DB 中有两个 object！** 一个 todo (#3313)，一个 done (#6705)。都指向同一文件同一行。

**第三步：检查 source_records 表**

```sql
SELECT sr.id, sr.source_item_id, sr.normalized_text
FROM source_records sr
WHERE sr.source_item_id LIKE '%journals/2026_04_07.md:47%';
```

| id | source_item_id | normalized_text |
|----|----------------|-----------------|
| 88702 | `...:47:87f5bfa7acdf28eb` | `TODO 上次移动的那个他们反应上不去...` |
| 177945 | `...:47:0cd7d5e51f3e964d` | `DONE 上次移动的那个他们反应上不去...` |

**两个 source_record！** 因为 block 内容从 `TODO` 变为 `DONE`，Logseq 的 block UUID hash 变了。

**第四步：检查 object_record_links**

```sql
SELECT orl.object_id, orl.record_id, orl.role, sr.normalized_text
FROM object_record_links orl
JOIN source_records sr ON sr.id=orl.record_id
WHERE orl.object_id IN (3313, 6705);
```

| object_id | record_id | role | normalized_text |
|-----------|-----------|------|-----------------|
| 3313 | 88702 | definition | TODO 上次移动... |
| 6705 | 177945 | definition | DONE 上次移动... |

每个 object 只有一个 definition record，但分别指向不同版本的 record。

**第五步：追踪写回后 resync 的链路**

```
done 3313
  → change_task_marker() (service.py:418)
    → resolve_target("3313")  → 找到 object #3313
    → writer.preview_update_task_marker(file, marker="DONE")
      → _resolve_block() 定位到 line 47
      → re.subn(r"^(\s*-\s*)(TODO|DOING|DONE|WAITING)\b", r"\1DONE", line)
      → 生成 WritePreview
    → _apply_direct_preview() 将 new_text 写入文件          ← 文件修改成功 ✓
    → _resync() = SyncService.sync_logseq()
      → LogseqAdapter.scan() 重新扫描 graph
        → 发现 line 47 现在是 "DONE 上次移动..."
        → 生成新的 source_item_id (因为 block UUID hash 变了)
        → 生成 SourceRecord #177945 (DONE 版本)
        → 生成 ActionObject (status=done, source_item_id=新ID)
      → Merger.ingest()
        → upsert_object() 按 (canonical_source, source_item_id) 唯一约束
        → 新 source_item_id → INSERT 新 object #6705          ← 创建了新 object！
        → 旧 object #3313 的 source_item_id 不再存在于扫描结果
        → #3313 保持 status="todo"                            ← 旧 object 未更新！
```

**第六步：检查 _resync 和 show 的交互**

`show 3313` (service.py:343-354)：直接从 DB 读取 `SELECT ... WHERE o.id=?`。
`show` **不读取文件**，只读 SQLite。resync 后 #3313 的 status 仍是 "todo"。

### 4.3 根因

**三重问题**：

1. **Logseq source_item_id 依赖内容 hash**：当 `TODO` 变为 `DONE`，block UUID 改变 → source_item_id 改变
2. **Merger 按 source_item_id 做幂等**：新 source_item_id → INSERT 新行，旧 object 不更新
3. **show 只读 DB 不读文件**：旧 object #3313 的 status="todo" 在 DB 中保持不变

**结果**：每次 `done`/`doing`/`wait` 操作都产生一个**重复 object**。

### 4.4 建议修复

方案 A（最小侵入，短期）：
- `change_task_marker` 写回文件后，**直接 UPDATE objects SET status=? WHERE id=?**，绕过 resync 对该对象的覆盖
- resync 时 merger 检测到新 source_item_id 的 record 与旧 object 的 location 匹配 → UPDATE 而非 INSERT

方案 B（根本修复，中期）：
- 使用 location（file_path + line_start）作为 stable identity 辅助匹配
- 或从 source_item_id 中提取 block UUID（不含内容 hash 的部分）

---

## 5. Issue 4: find 不按上下文 + 重复对象

### 5.1 用户描述

```
ta:/projects/课程-ECE564-Mobile-Application> find 移动
- #6705 task 上次移动的那个他们反应上不去，看一下情况 (2026_04_07:47)
- #3313 task 上次移动的那个他们反应上不去，看一下情况 (2026_04_07:47)
```

两个结果来自同一文件同一行。`find` 似乎也不限定在当前项目内。

### 5.2 调查过程

**第一步：阅读 find 实现**

`find` 命令 (service.py:365-380)：

```python
def find(self, query: str) -> str:
    rows = self.conn.execute("""
        SELECT o.*, l.file_path, l.page_name, l.journal_date, l.line_start
        FROM objects o LEFT JOIN locations l ON l.id=o.canonical_location_id
        WHERE o.title LIKE ? OR o.metadata_json LIKE ?
        ORDER BY o.id DESC LIMIT 20
    """, (f'%{query}%', f'%{query}%')).fetchall()
```

**`find` 是全局 SQL 查询**。没有任何 WHERE 条件限制当前项目上下文。没有 `self.context` 引用。

**第二步：确认重复来源**

两个结果 #6705 和 #3313 是 Issue 3 的重复 object（来自同一 source line 的不同内容版本）。

**第三步：复现实际输出**

```
=== find 移动 ===
- #6705 task 上次移动的那个他们反应上不去，看一下情况 (2026_04_07:47)
- #3313 task 上次移动的那个他们反应上不去，看一下情况 (2026_04_07:47)
- #3186 task 和陶锐处理一下 zabbix ... (2026_03_19:26)
- #2393 idea 我觉得可以在logseq当中完成... (2023_04_09:18)
- #1957 task [[283. 移动零]] ... (2022_08_18:22)
```

返回了来自不同 journal、不同年份的结果——纯全局搜索。

### 5.3 根因

1. **`find` 是全局的**：SQL 查询无上下文过滤
2. **重复来自 Issue 3**：修复 Issue 3 后，`find` 的重复问题自动减轻

### 5.4 建议修复

1. 区分 `find <query>`（当前上下文优先）和 `find --global <query>`（全局搜索）
2. 当前上下文为 project 时，优先搜索 belongs_to 该 project 的 object
3. 上下文优先结果先展示，全局结果标注 `[global]`

---

## 6. Issue 5: Direct Actions 慢 (6-8s)

### 6.1 用户描述

`todo` 创建、`doing` 调整状态等操作约 6-8 秒。

### 6.2 调查过程

**第一步：逐操作计时**

```python
cd /projects/课程-ECE564-Mobile-Application:  0.00s
ls tasks:                                      0.04s
find 移动:                                     0.00s
show 3313:                                     0.00s
project tree build:                            0.01s
project tree render:                           0.00s
```

**所有查询操作都非常快**（< 0.05s）。慢的不是查询。

**第二步：计时全量 sync**

```python
SyncService(conn, settings).sync_logseq()
→ 6.32s
```

**全量 resync 耗时 6.32 秒。**

**第三步：确认 write → resync 链路**

每次写操作都调用 `_resync()` (service.py:1082-1083)：

```python
def _resync(self) -> None:
    SyncService(self.conn, self.settings).sync_logseq()
```

调用点：
- `create_item()` 第 399 行 — 创建 todo/idea/mini/resource 后
- `change_task_marker()` 第 436 行 — 状态变更后
- `append_marker()` 第 415 行 — 添加注释后
- `someday()` 第 452 行
- `undo()` 第 472, 477 行 — 恢复后
- `_edit_task_title()` 第 660 行 — 编辑标题后
- `_edit_task_status()` 第 683 行 — 编辑状态后

**每次写操作都触发 6.32s 的全量重扫！**

**第四步：确认 _resync 是全量扫描**

`SyncService.sync_logseq()` (ingest/sync.py:19)：
1. `LogseqAdapter(graph_path).scan()` — 扫描所有 pages + journals
2. `Merger(self.repo).ingest(result)` — 全量合并
3. 创建 sync_run 记录

没有增量模式、没有单文件扫描选项。

### 6.3 根因

**每次写操作后都做全量 `sync_logseq()`**。重新扫描整个 Logseq graph 耗时 ~6.3s。所有写操作（todo, done, doing, wait, note, edit, undo）都受影响。

### 6.4 建议修复

1. **跳过 resync（最小侵入）**：对于状态变更，写回文件后直接 UPDATE objects SET status=?，跳过全量 resync
2. **增量刷新**：只重新解析被修改的文件，只 upsert 受影响的对象
3. **异步 resync**：先返回用户成功消息，后台异步刷新 DB
4. **轻量 resync**：`_resync_light()` 只 scan 最近 30 天 journals + 被修改 page

---

## 7. Issue 6: cd 不支持按 ID 导航

### 7.1 用户描述

```
ta:/projects/课程-ECE564-Mobile-Application> ls mini
  #28729 CAPTURED 再测试一下?  (课程-ECE564-Mobile-Application:596)
  #25331 CAPTURED 搞点东西吃吃  (课程-ECE564-Mobile-Application:595)
  #25330 CAPTURED 未命名小任务  (课程-ECE564-Mobile-Application:594)

ta:/projects/课程-ECE564-Mobile-Application> cd 28729
找到多个路径候选
[1] /projects/阶段-破壳计划
[2] /projects/学习-南大PA
...
```

`cd 28729` 失败了，显示了一堆 project 候选。

### 7.2 调查过程

**第一步：cd 解析流程**

`cd` (service.py:168-195) → `_resolve_path(target)` (line 1114)

`_resolve_path` 的核心流程：

```python
def _resolve_path(self, target):
    # 特殊目标: - (返回上一路径), ..
    # 别名扩展: @today → /today 等
    
    # 如果不是以 / 开头 → 拼接当前路径
    if not target.startswith("/"):
        target = join_path(self.context.path, target)
    
    # 解析路径段
    if target.startswith("/projects/"):
        # 查找 project name → resolve_object_id(name) 或 resolve_object_id(f"项目-{name}")
        # 更深的路径段 → _match_project_node() → 构建 tree 匹配节点标题
        ...
    elif target.startswith("/mini/"):
        # resolve_object_id(mini_name)
        ...
    # etc.
```

**当 `target="28729"` 时**：
1. 不以 `/` 开头 → 拼接当前路径 → `"/projects/课程-ECE564-Mobile-Application/28729"`
2. 匹配 `/projects/` 前缀 → 第二段 "课程-ECE564-Mobile-Application" 解析成功 → project_ref 设置
3. 第三段 "28729" → `_match_project_node()` → 构建 tree → 展平节点 → 查找标题为 "28729" 的节点 → **找不到**（因为 #28729 不是项目节点，是 mini_project 对象）
4. 返回 None → `_path_candidates()` 提供备选 → 显示 project 列表

**第二步：确认 resolve_object_id 支持数字 ID**

`resolve_object_id()` (repositories.py:242-250)：

```python
def resolve_object_id(self, ref):
    if ref.isdigit():
        row = self.conn.execute("SELECT id FROM objects WHERE id=?", (int(ref),)).fetchone()
        return int(row["id"]) if row else None
    # 否则按 title 模糊搜索...
```

`resolve_object_id` **确实支持数字 ID**！但 `_resolve_path` 只在特定路径模式中使用它（project name、mini name），从不用于裸数字 ID。

### 7.3 根因

`_resolve_path` (line 1114) 只支持路径名解析。`cd 28729` 被当作 path component 而非 object ID 处理。`resolve_object_id` 支持数字查询，但 `cd` 流程未调用它。

### 7.4 建议修复

在 `cd` 中增加 object ID 检测（在 path 解析之前）：

```python
def cd(self, target):
    # 新增：检测是否为数字 ID
    if re.match(r'^#?\d+$', target):
        obj_id = target.lstrip('#')
        obj = self.repo.get_object(int(obj_id))
        if obj:
            obj_type = obj['object_type']
            if obj_type == 'mini_project':
                # 导航到 /mini/<title>
                ...
            elif obj_type == 'task':
                # 在 ShellContext 中设置 current_object
                ...
    # 原有逻辑继续...
```

---

## 8. Issue 7: object context 下 note 不能省略 target

### 8.1 用户描述

希望进入 mini project 后直接 `note "备注"`，而非 `note 28729 "备注"`。

### 8.2 调查过程

**第一步：当前 ShellContext 结构**

```python
@dataclass
class ShellContext:
    path: str = "/today"
    project_ref: Optional[str] = None      # 如 "课程-ECE564-Mobile-Application"
    project_node_id: Optional[str] = None  # 如 "node_123"
    mini_ref: Optional[str] = None         # 如 "再测试一下?"
    # 注意：没有 current_object_id !
```

**第二步：note 的目标解析**

`append_marker()` (service.py:402-416)：

```python
def append_marker(self, command, args):
    if len(args) < 2:
        return f"Usage: {command} <object-id> \"text\""
    target = self.resolve_target(args[0], allow_types={"task", "idea", "mini_project", "project"})
    # args[0] 必须是 object ID
```

`note` 总是需要 `<object-id>` 参数。如果不提供 → 报错。没有从 `self.context` 推断 target 的逻辑。

**第三步：确认 _has_write_context**

```python
def _has_write_context(self):
    return bool(self.context.project_ref or self.context.project_node_id or self.context.mini_ref)
```

`_has_write_context()` 用于确定写入位置（项目页/日志），但**不用于推断 object target**。

### 8.3 根因

`ShellContext` 只有目录级上下文（project/node/mini），没有具体 object 上下文。`note` 不检查 `self.context` 是否有可用的当前 object。

### 8.4 建议修复

在 `ShellContext` 中增加 `current_object_id` 和 `current_object_type`：

```python
@dataclass
class ShellContext:
    ...
    current_object_id: Optional[int] = None
    current_object_type: Optional[str] = None  # "task", "mini_project", "idea"
```

然后修改 `note`/`done`/`edit` 等命令，缺少 target 时优先使用当前 object context：

```python
def note(self, args):
    if len(args) == 1:
        # 只有一个参数 → 推断 target 为当前 object
        if self.context.current_object_id:
            target_id = self.context.current_object_id
            text = args[0]
        else:
            return "Usage: note <object-id> \"text\"  (or cd to an object first)"
    else:
        target_id = args[0]
        text = args[1]
```

---

## 9. Issue 8: preview 不可读

### 9.1 用户描述

```
diff:
--- /Users/.../pages/课程-ECE564-Mobile-Application.md
+++ /Users/.../pages/课程-ECE564-Mobile-Application.md
@@ -518,7 +518,7 @@
                                - save之后振动倒计时，upload发射
                                - TODO-list
                                  id:: 67ba5e0c-...
-                                       - TODO 明确项目要做的内容，建立基础的完成和拓展的完成
+                                       - TODO 你好
                                        - TODO 结合之前的课程仓库，对相关知识点进行整理
```

缩进太深、上下文太多、难读。

### 9.2 调查过程

**第一步：当前 preview 的实现**

`_location_preview()` (service.py:972-989)：

```python
def _location_preview(self, operation, preview, target, content):
    return "\n".join([
        "将写入：",
        f"graph: {self.settings.logseq_graph_path}",
        f"file: {rel}",
        f"target: {target}",
        f"operation: {operation}",
        f"line: {preview.line_start or ''}",
        "content:",
        f"  - {content}",
        "diff:",
        preview.diff[:1200],    # ← 原始 unified diff，截断到 1200 字符
    ])
```

**第二步：preview.diff 的生成**

`_preview()` (logseq_writer.py:222-233)：

```python
diff = "\n".join(
    difflib.unified_diff(
        old_text_lines,
        new_text_lines,
        fromfile=str(path),
        tofile=str(path),
    )
)
```

标准 unified diff，**默认显示 3 行上下文**（前后各 3 行）。

**第三步：问题分析**

对于深度嵌套的 Logseq block（如 line 518 在 7 层缩进下），diff 输出中：
- 每行前有 30+ 字符的缩进
- 3 行前置上下文包含不相关内容
- raw unified diff 格式包含元数据（`---`、`+++`、`@@`）

**第四步：没有 human-friendly 摘要**

整个 preview 路径中没有提取 "old text → new text" 进行简化显示的逻辑。只有 `difflib.unified_diff` → 截断 1200 字符。

### 9.3 根因

`_location_preview` 直接输出原始 unified diff，没有 human-friendly 摘要层。深度缩进 + 3 行上下文 + raw diff 格式 → 不可读。

### 9.4 建议修复

创建简化的 human preview：

```python
def _human_preview(self, operation, preview, target, content):
    # 提取 old line 和 new line（只显示变化行）
    old_line = extract_changed_line(preview.diff, old=True)
    new_line = extract_changed_line(preview.diff, old=False)
    return "\n".join([
        f"{operation} #{target}",
        f"  old: {old_line.strip()}",
        f"  new: {new_line.strip()}",
        f"  file: {rel}:{preview.line_start}",
        "  [y/N]",
    ])
```

Raw diff 移到 `detail on` 模式或 `--detail` 标志。

---

## 10. Issue 9: object context 下 edit title/status 不能省略 target

### 10.1 用户描述

希望：
```text
cd 15141
edit title "你好"
edit status waiting
note "这是备注"
result "形成成果"
```

### 10.2 调查过程

`_edit_task()` (service.py:622-637)：

```python
def _edit_task(self, args):
    if len(args) < 3:
        return "Usage: edit task <target> title|content|status <value>"
    target_ref = args[0]  # ← 总是需要 target
    ...
```

`edit task` 总是需要 target 参数。与 Issue 7 相同——缺少 object context 机制。

### 10.3 根因

与 Issue 7 相同。

### 10.4 建议修复

与 Issue 7 一起解决。当 `ShellContext.current_object_id` 被设置时，`edit task`、`note`、`done`、`result` 等命令自动使用当前 object 作为 target。

---

## 11. Issue 10: clarify 太冗余

### 11.1 用户描述

每个条目问题很多（9 个），也许应该引入 AI 提问。

### 11.2 调查过程

**第一步：定位问题模板**

`BASIC_QUESTIONS` (clarify/service.py:22-32)：

```python
BASIC_QUESTIONS = [
    {"id": "value", "text": "这个条目现在还有价值吗？"},
    {"id": "classification", "text": "它更像：行动 / 想法 / 资源 / 等待 / 未来可能 / 已完成 / 丢弃？"},
    {"id": "project", "text": "它是否属于某个项目？"},
    {"id": "mini_project", "text": "它是否需要拆成小任务？"},
    {"id": "waiting", "text": "它是否需要等待别人或外部条件？"},
    {"id": "result", "text": "它完成后是否需要成果标注？"},
    {"id": "handling", "text": "你希望如何处理它？"},
    {"id": "project_node", "text": "如果它属于项目，更像挂在哪个工作流 / 小任务 / 具体事务下？"},
    {"id": "resource_boundary", "text": "它是否只是资源，而不是行动？"},
]
```

**9 个问题，每个条目全部询问。**

**第二步：检查是否有 quick mode**

搜索 "quick" 在 clarify/ 目录 → **零结果**。没有 quick mode。

**第三步：检查 AI 问题支持**

在 `providers/base.py:275-296`（`parse_provider_response`）：

```python
if isinstance(raw, dict):
    questions = raw.get("questions_for_user")
    if questions is not None:
        result.raw_summary["questions_for_user_count"] = len(questions)
```

**Provider 已经支持生成 `questions_for_user`！** 系统提示（line 336）包含 `questions_for_user:[{question,why}]` 的 JSON schema。

但是在 `clarify/service.py` 的 `run_review()` 中，**provider 返回的 `questions_for_user` 从未被用于询问用户**。它只被记录在统计中。

**第四步：答案存储位置**

```
review_items.metadata_json = {
    "clarify": {
        "status": "answered",
        "questions": BASIC_QUESTIONS,
        "answers": [{"question_id": "freeform", "question": "...", "answer": "<user_input>"}]
    }
}
```

**所有 9 个问题对应一个自由文本答案**，不是逐问题回答。答案存储在 `ReviewSessionService.record_answer()` (reviews/service.py:55)。

### 11.3 根因

1. **9 个固定问题全部显示**，无 quick mode
2. **Provider 的 `questions_for_user` 已解析但未使用**
3. **每个条目只有一个自由文本回答**，不是逐问题交互

### 11.4 建议修复

1. **Quick mode**: `clarify quick` → 只问 1-2 个核心问题（value + handling）
2. **AI questions**: 使用 provider 的 `questions_for_user`（已支持解析），由 AI 根据条目内容生成针对性问题
3. **问题数量限制**: 可配置每个条目最多问几个问题
4. **跳过支持**: 允许逐条 skip

---

## 12. 数据库发现

### 12.1 重复对象 (3313 vs 6705)

| 字段 | #3313 | #6705 |
|------|-------|-------|
| object_type | task | task |
| title | 上次移动的那个他们反应上不去，看一下情况 | 同上 |
| status | **todo** | **done** |
| source_item_id | `...:47:87f5bfa7acdf28eb` | `...:47:0cd7d5e51f3e964d` |
| file_path | journals/2026_04_07.md | 同上 |
| line_start | 47 | 47 |
| definition record | #88702 (TODO 版本) | #177945 (DONE 版本) |
| belongs_to 关系 | 无 | 无 |

### 12.2 项目下对象的关系

```
项目 #1534 (课程-ECE564-Mobile-Application)
├── #15141 (task: 结合之前的课程仓库...)  belongs_to #1534
├── #25330 (mini_project: 未命名小任务)   belongs_to #1534
├── #25331 (mini_project: 搞点东西吃吃)   belongs_to #1534
└── #28729 (mini_project: 再测试一下?)    belongs_to #1534
```

journal TODO (#3313, #6705) 与项目 #1534 **无关系**。

### 12.3 错误提取

对象 #1564: type=task, title=`-list`, status=todo, line=519  
这是把 `TODO-list` 行中的 `-list` 部分误提取为 task。`TODO-list` 是结构性标记，不是独立 task。

### 12.4 大量重复提取

同一 source line 被多次提取（例如 line 512 的内容被提取了 3 次，source_record 245468, 423957, 66982）。说明历史 sync 产生了重复 source_records（可能因 block UUID 变化或 page 重命名）。

---

## 13. Logseq 文件发现

### 13.1 项目页前 80 行

```
 1  PARA:: [[PARA/Archive]] 
 2  Areas:: NA
 3  state:: 已完成
 4  priority:: [[A]]
 ...
 9  - TODO [#A] Mobile Application Development #项目清单
10    type:: [[项目]]
11		- **[具体目标]**:<待完成的目标>          ← Tab 缩进
12			- **[目标]** 有着良好的参与度...      ← 双层 Tab 缩进
```

- 第 1 行：`PARA:: [[PARA/Archive]]` — 项目已被归档
- 第 3 行：`state:: 已完成` — 项目状态已完成
- 第 9 行：`#项目清单` — 标签可识别为项目
- Tab 缩进普遍使用

### 13.2 项目页 500-610 行

```
514  - TODO 完成项目Readme的撰写
515  - [[564-hw6]](更改存储结构)
519    - TODO-list
520      id:: 67ba5e0c-87a6-433f-b8bd-cd52d5d116a2
521      - TODO 明确项目要做的内容...
522      - TODO 结合之前的课程仓库...
...
585  - **[头脑风暴]**:<事务执行过程中你的想法>
594  - **[小任务]**
595      - **[小任务]** 搞点东西吃吃
596      - **[小任务]** 再测试一下?
```

- Line 519 `TODO-list` 有 `id::` 属性 — 这是 Logseq 的结构性标记节点
- Line 520 是 block UUID — parser 将其识别为属性
- Line 521-522 是 TODO 子节点 — 属于父节点 519-520
- Line 594 `**[小任务]**` — 语义标记，应该是 mini projects
- 所有缩进使用 **Tab 字符**（在 nl 输出中不可见，但 parser 证实了这一点）

### 13.3 Journal 2026_04_07 第 35-60 行

```
43  - 同类型的问题在不同的章节重复出现
44  - 以上是我归纳的几个问题...
46  - **[注]** 上次的光衰还是link的相关的，告警的严重程度搞一下
47  - DONE 上次移动的那个他们反应上不去，看一下情况   ← done 命令修改后的状态
48  - ## 下午
49  - DONE 测试一下报告的撰写...
53  - TODO 有个zabbix相关的开通
54  - TODO 托管上面加一台机器...
```

Line 47 已成功从 `TODO` 变为 `DONE` — 写回生效。

---

## 14. 风险评估

| 修复项 | 风险 | 影响范围 | 说明 |
|--------|------|---------|------|
| indent_level 修复 (Issue 2) | **低** | parser.py 1行 | 纯 parser 修改。需更新使用空格缩进的测试。 |
| _resync 优化 (Issue 5) | **中** | service.py + sync.py | 涉及 sync 逻辑。需要仔细测试 DB 一致性。 |
| 去除重复 object (Issue 3) | **中** | merger.py + service.py | 两处需改。可能影响已有重复数据。 |
| find 上下文过滤 (Issue 4) | **低** | service.py find() | 纯查询修改。 |
| cd by id (Issue 6) | **低** | service.py cd() | 新增路径解析逻辑。 |
| object context (Issues 7, 9) | **高** | service.py + inventory.py | ShellContext 数据结构变更，多个命令需修改。需仔细设计。 |
| preview 优化 (Issue 8) | **低** | service.py _location_preview | 纯展示层修改。 |
| clarify quick/AI (Issue 10) | **中** | clarify/service.py | 涉及 clarify 流程和 provider 集成。 |
| ls tasks 数据源扩展 (Issue 1) | **中** | inventory.py + merger.py | 增加 belongs_to 自动建立逻辑影响 ingestion。 |

---

## 15. 建议修复优先级

### P0 — 必须最先修复

| # | Issue | 修复点 | 预计改动 |
|---|-------|--------|---------|
| 1 | Tree flat | `parser.py:indent_level()` 支持 Tab 缩进 | 1行修改 + 测试更新 |
| 2 | done/show 不一致 + 重复 object | writeback 后直接 DB UPDATE + merger stable identity | merger.py + service.py |
| 3 | Direct Actions 慢 | 状态变更跳过全量 resync，改为直接 DB UPDATE | service.py _resync → _resync_light |
| 4 | find 上下文 | 添加 context-aware 搜索 | service.py find() |
| 5 | ls tasks 为空 | 扩展 inventory 数据源 | inventory.py |

### P1 — 强烈建议修

| # | Issue | 修复点 | 预计改动 |
|---|-------|--------|---------|
| 6 | cd by object ID | cd 中增加数字 ID 检测 | service.py cd() |
| 7 | Object context | ShellContext 增加 current_object_id | service.py + inventory.py |
| 8 | note/edit 省略 target | 利用 object context 推断 | service.py |
| 9 | Preview humanization | human-friendly preview + --detail | service.py |

### P2 — 体验增强

| # | Issue | 修复点 | 预计改动 |
|---|-------|--------|---------|
| 10 | Clarify quick/AI | quick mode + 使用 provider questions_for_user | clarify/service.py |
| 11 | Smarter completion | object ID completion + context-aware | completion.py |

---

## 附录 A: 调查工具链

本报告使用了以下调查手段：

1. **代码探索** (3个 Explore 子代理)：
   - shell/inventory 系统、commands 实现
   - writeback/direct actions 管道
   - project tree 和 clarify 系统

2. **数据库查询** (SQLite)：
   - Object 查询：3313, 6705, 15141, 28729, 25331, 25330
   - Relation 分析：belongs_to 覆盖统计
   - Source record 去重分析

3. **程序化 Shell 复现**：
   - cd + ls tasks/todo/mini
   - find 移动、show 3313/6705
   - 操作计时

4. **文件检查**：
   - 项目页 1-80行、500-610行
   - Journal 2026_04_07 35-60行
   - Done 写回结果验证

5. **Tab vs Space 验证**：
   - indent_level 行为测试
   - 对比测试树 vs 真实项目树（3个项目）

---

## 附录 B: 关键代码路径索引

| 功能 | 文件 | 行号 |
|------|------|------|
| indent_level | adapters/logseq/parser.py | 128-130 |
| parse_logseq_file | adapters/logseq/parser.py | 156-188 |
| LogseqBlock (data class) | adapters/logseq/parser.py | 25-33 |
| ProjectTreeService.build | projects/tree.py | 58-91 |
| ProjectTreeService.render_markdown | projects/tree.py | 93-105 |
| ShellContext | shell/service.py | 30-41 |
| HumanShellService.__init__ | shell/service.py | 59-72 |
| cd | shell/service.py | 168-195 |
| _resolve_path | shell/service.py | 1114-1150 |
| ls | shell/service.py | 197-252 |
| find | shell/service.py | 365-380 |
| tree | shell/service.py | 337-341 |
| show | shell/service.py | 343-354 |
| change_task_marker | shell/service.py | 418-440 |
| append_marker (note) | shell/service.py | 402-416 |
| _edit_task | shell/service.py | 622-637 |
| _edit_task_title | shell/service.py | 639-661 |
| _edit_task_status | shell/service.py | 667-683 |
| _apply_direct_preview | shell/service.py | 891-896 |
| _resync | shell/service.py | 1082-1083 |
| _location_preview | shell/service.py | 972-989 |
| resolve_target | shell/service.py | 903-925 |
| build_inventory | shell/inventory.py | 14-52 |
| _inventory_project_context | shell/inventory.py | 304-369 |
| _get_project_children | shell/inventory.py | 524-547 |
| _flatten_tree_nodes | shell/inventory.py | 372-394 |
| LogseqWriter.preview_update_task_marker | writes/logseq_writer.py | 84-104 |
| LogseqWriter._preview | writes/logseq_writer.py | 222-233 |
| Merger.ingest | ingest/merger.py | 32-64 |
| Repository.upsert_object | storage/repositories.py | 112-147 |
| Repository.resolve_object_id | storage/repositories.py | 242-250 |
| SyncService.sync_logseq | ingest/sync.py | 19 |
| BASIC_QUESTIONS | clarify/service.py | 22-32 |
| ClarifyService.run_review | clarify/service.py | 88-194 |
| ClarifyService._prompt_answer | clarify/service.py | 457-464 |
| parse_provider_response (questions_for_user) | providers/base.py | 275-296 |
| ShellCompleter | shell/completion.py | 35-155 |
