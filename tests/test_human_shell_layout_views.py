from tests.test_human_shell import loaded_shell


def test_workspace_views_render(tmp_path):
    shell, _repo, _graph, _conn = loaded_shell(tmp_path)
    shell.run_line("layout on")
    assert "Main View: today" in shell.run_line("view today")
    assert "Main View: dashboard" in shell.run_line("view dashboard")
    shell.run_line("cd /projects/项目-韩国旅行")
    assert "Main View: tree" in shell.run_line("view tree")
    assert "Main View: show" in shell.run_line("view show")
    assert "Main View: tasks" in shell.run_line("view tasks")
    assert "Main View: proposals" in shell.run_line("view proposals")
    assert "Main View: health" in shell.run_line("view health")
    assert "Main View: preview" in shell.run_line("view preview")
    assert "Main View: edit" in shell.run_line("view edit")


def test_view_health_requires_project(tmp_path):
    shell, _repo, _graph, _conn = loaded_shell(tmp_path)
    output = shell.run_line("view health")
    assert "requires a project context" in output
    assert "cd /projects" in output


def test_focus_and_select_do_not_change_path(tmp_path):
    shell, repo, _graph, _conn = loaded_shell(tmp_path)
    task = next(item for item in repo.list_objects("task", limit=50) if item["title"] == "已有项目任务")
    path = shell.context.path
    assert "Focus:" in shell.run_line(f"focus {task['id']}")
    assert shell.context.path == path
    assert str(task["id"]) in shell.run_line("select")
