from pathlib import Path

from tests.test_human_shell import loaded_shell


def test_inline_edit_conflict_detection(tmp_path):
    shell, repo, _graph, _conn = loaded_shell(tmp_path)
    task = next(item for item in repo.list_objects("task", limit=50) if item["title"] == "已有项目任务")
    buffer = shell.inline_editor.create_buffer([str(task["id"]), "line"])
    buffer.set_text("        - TODO changed in buffer")
    path = Path(task["file_path"])
    path.write_text(path.read_text(encoding="utf-8") + "\n- external change\n", encoding="utf-8")
    result = shell.inline_editor.save(buffer)
    assert "Conflict detected" in result
    assert "Mode: CONFLICT" in shell.layout_state.sync_status.format_line()
