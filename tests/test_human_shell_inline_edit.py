from pathlib import Path

from tests.test_human_shell import loaded_shell


def test_edit_buffer_cursor_and_paste(tmp_path):
    shell, repo, _graph, _conn = loaded_shell(tmp_path)
    task = next(item for item in repo.list_objects("task", limit=50) if item["title"] == "已有项目任务")
    buffer = shell.inline_editor.create_buffer([str(task["id"]), "line"])
    buffer.home()
    buffer.insert_text("X")
    buffer.move_right()
    buffer.move_left()
    buffer.end()
    buffer.paste("\nchild one\nchild two")
    assert buffer.dirty
    assert any("child two" in line for line in buffer.buffer_lines)


def test_insert_line_save_preview_and_rollback(tmp_path):
    shell, repo, _graph, _conn = loaded_shell(tmp_path)
    task = next(item for item in repo.list_objects("task", limit=50) if item["title"] == "已有项目任务")
    file_path = Path(task["file_path"])
    shell.run_line(f"focus {task['id']}")
    answers = iter([":set         - TODO inline changed", ":save", "y"])
    shell.input_func = lambda prompt="": next(answers)
    result = shell.run_line("insert line")
    assert "Inline edit saved" in result
    assert "inline changed" in file_path.read_text(encoding="utf-8")
    assert "Undone op" in shell.run_line("undo")
    assert "inline changed" not in file_path.read_text(encoding="utf-8")


def test_insert_subtree_save(tmp_path):
    shell, repo, _graph, _conn = loaded_shell(tmp_path)
    mini = next(item for item in repo.list_objects("mini_project", limit=50) if item["title"] == "整理打车攻略")
    file_path = Path(mini["file_path"])
    replacement = "    - **[小任务]** 整理打车攻略\n        - TODO 新子任务\n        - 追加备注"
    answers = iter([":set " + replacement, ":save", "y"])
    shell.input_func = lambda prompt="": next(answers)
    result = shell.run_line(f"insert {mini['id']} subtree")
    assert "Inline edit saved" in result
    text = file_path.read_text(encoding="utf-8")
    assert "TODO 新子任务" in text
    assert "追加备注" in text


def test_insert_cancel_no_write(tmp_path):
    shell, repo, _graph, _conn = loaded_shell(tmp_path)
    task = next(item for item in repo.list_objects("task", limit=50) if item["title"] == "已有项目任务")
    file_path = Path(task["file_path"])
    original = file_path.read_text(encoding="utf-8")
    shell.run_line(f"focus {task['id']}")
    answers = iter([":set         - TODO should not write", ":cancel", "y"])
    shell.input_func = lambda prompt="": next(answers)
    assert "Edit canceled" in shell.run_line("insert line")
    assert file_path.read_text(encoding="utf-8") == original


def test_insert_rejects_project_root_today_dashboard(tmp_path):
    shell, _repo, _graph, _conn = loaded_shell(tmp_path)
    assert "No editable focus" in shell.run_line("insert")
    shell.run_line("cd /projects/项目-韩国旅行")
    assert "No editable focus" in shell.run_line("insert")
    shell.run_line("cd /dashboard")
    assert "No editable focus" in shell.run_line("insert")
