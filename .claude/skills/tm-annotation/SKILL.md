---
name: tm-annotation
description: "在用户明确授权后，把 Agent 判断写入 task-manager-cli 内部 annotation 数据库，而不是写回 Logseq。"
disable-model-invocation: true
---

# tm-annotation

此 skill 有副作用，只能在用户明确要求“保存批注”“写 annotation”“更新 annotation 状态”时手动调用。

## 作用范围

支持：

- 对象级 annotation add/list/status
- record 级 annotation add/list

不支持：

- 写回 Logseq
- 自动代替用户做长期记录决策

## 常用命令

对象级新增：

```bash
tm annotation add <object-id> "判断；依据；建议下一步；置信度=0.72" --author claude --type suggestion
```

对象级查询：

```bash
tm annotation list --object <object-id> --format json
```

record 级新增：

```bash
tm annotation add --record <record-id> "判断；依据；建议下一步；置信度=0.61" --author claude --type comment
```

record 级查询：

```bash
tm annotation list --record <record-id> --format json
```

状态更新：

```bash
tm annotation status <annotation-id> accepted
tm annotation status <annotation-id> rejected
tm annotation status <annotation-id> archived
tm annotation status <annotation-id> open
```

如 `tm` 不在 PATH，可改用 `PYTHONPATH=src python3 -m task_manager_cli.cli.main ...` 的等价形式。

## 批注内容要求

批注内容应尽量包含：

- 判断
- 依据
- 建议下一步
- 置信度

不要把批注伪装成“用户原始记录”。

## 安全边界

- annotation 写入 tm 内部数据库，不写回 Logseq
- 未经明确授权，不要执行 `tm annotation add`
- 未经明确授权，不要执行 `tm annotation status`
- 不要使用 `--no-redact`
