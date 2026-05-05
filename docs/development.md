# Development

## 本地运行

```bash
python3 -m pip install -e ".[dev]"
tm --help
python3 -m pytest
```

未安装时：

```bash
PYTHONPATH=src python3 -m task_manager_cli.cli.main --help
```

## 设计约束

- `core/` 不依赖任何具体 adapter。
- `adapters/` 只读外部来源，输出标准候选数据。
- `ingest/` 负责幂等合并和 sync run。
- `query/` 不直接读取 Logseq 原文件。
- `annotations/` 只写内部数据库。
- `cli/` 不堆业务逻辑。

## 新 adapter 边界

新增 adapter 应输出 `AdapterResult`，包含 objects、records、links、relations、warnings。不要直接写 SQLite，也不要把来源格式泄漏到 core/query。

## 数据库

第一版使用内置 schema 初始化，没有独立迁移框架。后续 schema 变化应提升 `SCHEMA_VERSION` 并增加显式迁移脚本。

## 写入能力

写入相关代码在 `src/task_manager_cli/writes/`。写入必须默认禁用、proposal 优先、append-only、apply 前检查文件 hash、写前备份，并且不能把写入逻辑放进 adapter、query 或 annotation 层。
