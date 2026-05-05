# Flomo Adapter

Flomo adapter 尚未完整实现。预期边界：

- memo 映射为 `SourceRecord(record_type=memo)`。
- 默认生成 `Idea` candidate。
- 如果 memo 中有明确 TODO 标记，可生成 `Task` candidate。
- `Location` 保存 memo id、created_at 和 external url。
- 不改变 core、query、annotation 层。
