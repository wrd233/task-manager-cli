---
name: tm-dev-fix
description: "在用户明确要求修复代码、测试或文档时，按最小安全修复流程推进开发工作。"
disable-model-invocation: true
---

# tm-dev-fix

此 skill 可能修改代码，必须在用户明确要求修复 bug、补测试、改文档或实现小范围开发任务时手动调用。

## 工作流程

1. 先复现
2. 补测试或确认现有测试缺口
3. 做最小安全修复
4. 跑 `python3 -m pytest`
5. 跑 `python3 -m compileall -q src`
6. 更新相关文档
7. 输出 implementation report

## 开发原则

- 优先补能稳定复现问题的测试
- 修复应尽量局部，避免顺手重构无关模块
- 涉及 CLI 行为变更时同步更新文档
- 禁止修改 Logseq
- 禁止削弱 redaction
- 禁止把 annotation 改成写回 Logseq
- 禁止把优先级判断硬编码进 CLI

## 建议命令

```bash
python3 -m pytest
python3 -m compileall -q src
git status
git diff
```

如需 CLI 复现，可优先使用：

```bash
PYTHONPATH=src python3 -m task_manager_cli.cli.main --help
```

## 输出要求

implementation report 至少应包含：

1. 问题如何复现
2. 新增或修改了哪些测试
3. 代码修复点
4. 验证结果
5. 仍然存在的限制
