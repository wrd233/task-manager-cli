# Claude Code 使用说明

本文说明 Claude Code 在 `task-manager-cli` 项目中的推荐角色、常用命令、提示词和安全边界。

## Claude Code 的角色

在本项目中，Claude Code 默认应扮演以下角色：

1. `tm` CLI 使用者
2. 行动上下文分析者
3. 必要时的开发者

优先顺序应为：

- 先作为 CLI 使用者读取事实和上下文
- 再作为分析者给出解释和建议
- 只有用户明确要求时，才作为开发者修改代码、测试或文档

## 日常推荐命令

### 今天做什么

```bash
tm agent today-context --days 14 --format json
tm report recent-unresolved-tasks --days 14 --format json
tm report active-projects --format json
```

### 诊断单个项目

```bash
tm agent project-context "<项目名或对象 id>" --format json
```

如项目不明确，可先：

```bash
tm report active-projects --format json
```

### 整理最近想法

```bash
tm agent inbox-context --days 30 --format json
```

### 检查抽取质量

```bash
tm report extraction-quality --format json
python3 -m pytest
python3 -m compileall -q src
```

如 `tm` 不在 PATH，可使用：

```bash
PYTHONPATH=src python3 -m task_manager_cli.cli.main ...
```

## 推荐提示词

以下提示词适合直接交给 Claude Code：

### 今天做什么

```text
请用 tm-agent-today skill，基于最近 14 天上下文分析今天最值得处理的 3-5 件事，区分 CLI 事实和你的建议，不要写 annotation。
```

### 诊断项目

```text
请用 tm-project-diagnose skill，诊断“项目-韩国旅行”当前状态、证据、可能卡点和下一步建议，不要修改 Logseq，也不要写 annotation。
```

### 整理想法

```text
请用 tm-inbox-review skill，整理最近 30 天的 inbox ideas，分类为可转项目、可转事务、可并入已有项目、暂时保留、可归档、疑似误抽。
```

### 保存批注

```text
请用 tm-annotation skill，把这条判断写入对象 12 的 annotation：判断、依据、建议下一步和置信度都要写清楚，不要写回 Logseq。
```

### 检查抽取质量

```text
请用 tm-extraction-audit skill，检查当前抽取质量，重点看 suspicious ideas、source/location mismatch、definition record 缺失、redaction 和 relation count。
```

### 修复 CLI

```text
请用 tm-dev-fix skill，先复现问题，再补测试，做最小安全修复，最后跑 pytest 和 compileall，并更新相关文档。
```

## 安全边界

Claude Code 在本项目里必须遵守以下边界：

- 不写 Logseq
- annotation 写入 tm 内部数据库
- 默认 redaction
- 不使用 full dump 做日常 Agent 输入

更具体地说：

- 不默认执行 `tm sync logseq`
- 不默认执行 `tm annotation add`
- 不默认执行 `tm write apply`
- 不默认执行任何 `--no-redact`
- 优先使用 `tm agent ...` ，而不是自己去拼接大范围原始记录

## 为什么优先用 `tm agent ...`

`task-manager-cli` 的设计目标是给外部 Agent 提供稳定、薄而可追溯的上下文层。

因此日常问答和行动分析时，优先使用：

- `tm agent today-context`
- `tm agent project-context`
- `tm agent inbox-context`

不要直接把全量导出、全量项目列表或原始 Logseq dump 当作默认输入。那样既更重，也更容易模糊“CLI
提供事实、Agent 负责解释”的边界。

## Annotation 原则

如果用户要求“保存判断”“记录建议”“沉淀批注”，应使用 `tm annotation ...` 。

批注写入位置是 `task-manager-cli` 内部数据库，而不是 Logseq 原始 Markdown。这样可以保持：

- 原始记录层稳定
- Agent 判断层独立
- 批注可查询、可更新状态、可审计

推荐批注格式：

- 判断
- 依据
- 建议下一步
- 置信度

## 开发者模式

只有在用户明确要求修复代码、测试或文档时，Claude Code 才应进入开发者模式。

推荐流程：

1. 先复现
2. 补测试
3. 做最小安全修复
4. 跑 `python3 -m pytest`
5. 跑 `python3 -m compileall -q src`
6. 更新文档

开发过程中也必须继续遵守：

- 不削弱 redaction
- 不把 annotation 改成写回 Logseq
- 不把优先级判断硬编码进 CLI
