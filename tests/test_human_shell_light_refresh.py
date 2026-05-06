from unittest.mock import patch

from tests.test_human_shell import loaded_shell


def test_done_and_edit_title_do_not_call_full_sync(tmp_path):
    shell, repo, _graph, _conn = loaded_shell(tmp_path)
    task = next(item for item in repo.list_objects("task", limit=50) if item["title"] == "已有项目任务")
    with patch("task_manager_cli.ingest.sync.SyncService.sync_logseq", side_effect=AssertionError("full sync called")):
        assert "DONE" in shell.run_line(f"done {task['id']}")
        assert repo.get_object(task["id"])["status"] == "done"
        shell.input_func = lambda prompt="": "y"
        assert "title updated" in shell.run_line(f'edit task {task["id"]} title "轻量刷新标题"')
        assert repo.get_object(task["id"])["title"] == "轻量刷新标题"


def test_todo_create_and_undo_refresh_current_index(tmp_path):
    shell, repo, graph, _conn = loaded_shell(tmp_path)
    shell.run_line("cd /projects/项目-韩国旅行")
    assert "written" in shell.run_line('todo "轻量刷新新增任务"')
    assert any(item["title"] == "轻量刷新新增任务" for item in repo.list_objects("task", limit=100))
    assert "Undone" in shell.run_line("undo")
    assert "轻量刷新新增任务" not in (graph / "pages" / "项目-韩国旅行.md").read_text(encoding="utf-8")
