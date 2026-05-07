import sys

from task_manager_cli.output.colors import strip_ansi
from task_manager_cli.projects.tree import ProjectTreeService

from tests.test_human_shell import loaded_shell


class Tty:
    def isatty(self):
        return True


def test_ls_tasks_colors_status_markers_and_no_color_disables(tmp_path, monkeypatch):
    shell, repo, _graph, _conn = loaded_shell(tmp_path)
    task = next(item for item in repo.list_objects("task", limit=100) if item["title"] == "已有项目任务")
    shell.repo.update_object_after_writeback(task["id"], status="doing")
    _conn.commit()

    monkeypatch.setattr(sys, "stdout", Tty())
    monkeypatch.delenv("NO_COLOR", raising=False)
    shell.run_line("cd /dashboard")
    colored = shell.run_line("ls tasks")
    assert "\033[38;5;" in colored
    assert "DOING" in strip_ansi(colored)

    monkeypatch.setenv("NO_COLOR", "1")
    plain = shell.run_line("ls tasks")
    assert "\033[" not in plain
    assert "DOING" in plain


def test_raw_subtree_and_preview_color_task_markers(tmp_path, monkeypatch):
    shell, _repo, _graph, _conn = loaded_shell(tmp_path)
    monkeypatch.setattr(sys, "stdout", Tty())
    monkeypatch.delenv("NO_COLOR", raising=False)
    shell.run_line("cd /projects/项目-韩国旅行")
    shell.run_line("cd 整理打车攻略")

    raw = shell.run_line("show")
    assert "\033[38;5;25mTODO\033[0m 查询 Kakao T" in raw

    preview = shell.run_line('where todo "预览状态颜色"')
    assert "\033[38;5;25mTODO\033[0m 预览状态颜色" in preview


def test_done_waiting_and_tree_no_color_paths(tmp_path, monkeypatch):
    shell, repo, _graph, _conn = loaded_shell(tmp_path)
    task = next(item for item in repo.list_objects("task", limit=100) if item["title"] == "已有项目任务")
    monkeypatch.setattr(sys, "stdout", Tty())
    monkeypatch.delenv("NO_COLOR", raising=False)

    assert "\033[38;5;90mDOING\033[0m" in shell.run_line(f"doing {task['id']}")
    assert "\033[38;5;136mWAITING\033[0m" in shell.run_line(f"wait {task['id']}")
    assert "\033[38;5;28mDONE\033[0m" in shell.run_line(f"done {task['id']}")

    service = ProjectTreeService(shell.conn, shell.settings)
    tree = service.build("项目-韩国旅行")
    colored = service.render_markdown(tree, color=True)
    plain = service.render_markdown(tree, color=False)
    assert "\033[1;33m" in colored
    assert "\033[" not in plain
