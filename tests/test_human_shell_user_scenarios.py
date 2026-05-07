from task_manager_cli.projects.lifecycle import ProjectLifecycleService
from task_manager_cli.shell.service import HumanShellService
from task_manager_cli.config.settings import Settings
from task_manager_cli.storage.database import connect, init_db
from task_manager_cli.storage.repositories import Repository


def lifecycle_env(tmp_path):
    graph = tmp_path / "graph"
    (graph / "pages").mkdir(parents=True)
    (graph / "journals").mkdir()
    conn = connect(tmp_path / "tm.sqlite3")
    init_db(conn)
    settings = Settings(
        app_dir=tmp_path / "app",
        database_path=tmp_path / "tm.sqlite3",
        logseq_graph_path=graph,
        write_mode="guarded",
        write_backup_dir=tmp_path / "backups",
        write_require_confirm=False,
    )
    return graph, conn, Repository(conn), settings


def test_shell_project_creation_enters_project_and_show_is_contextual(tmp_path):
    graph, conn, repo, settings = lifecycle_env(tmp_path)
    shell = HumanShellService(conn, settings)

    assert shell.run_line("cd /today") == "/today"
    assert "Context:" in shell.run_line("ls") or "Journal" in shell.run_line("ls")
    assert shell.run_line("cd /dashboard") == "/dashboard"
    assert "No tasks" in shell.run_line("ls tasks") or "Tasks" in shell.run_line("ls tasks") or "Active Tasks" in shell.run_line("ls tasks")
    assert shell.run_line("cd /projects") == "/projects"
    created = shell.run_line('project create "用户测试项目"')

    assert "project created" in created
    assert shell.context.path == "/projects/用户测试项目"
    assert "current: /projects/用户测试项目" in created

    shell.run_line('todo "第一个任务"')
    shell.run_line('idea "一个想法"')
    shell.run_line('resource "一个资源 https://example.com"')
    shell.run_line('result "一个成果"')
    page_text = (graph / "pages" / "用户测试项目.md").read_text(encoding="utf-8")

    assert "TODO 第一个任务" in page_text
    assert "**[想法]** 一个想法" in page_text
    assert "**[资源]** 一个资源" in page_text
    assert "**[成果]** 一个成果" in page_text
    assert "Project #" in shell.run_line("show")
    assert "项目树" in shell.run_line("tree")
    assert "第一个任务" in shell.run_line("ls unplaced")


def test_shell_object_context_edit_note_result_done_undo(tmp_path):
    graph, conn, repo, settings = lifecycle_env(tmp_path)
    answers = iter(["y"])
    shell = HumanShellService(conn, settings, input_func=lambda _prompt: next(answers, "y"))
    shell.run_line('project create "对象测试项目" --enter')
    shell.run_line('todo "需要处理的任务"')
    task = next(item for item in repo.list_objects("task", limit=100) if item["title"] == "需要处理的任务")

    assert shell.run_line(f"cd {task['id']}").endswith(f"/task/{task['id']}")
    assert "当前内容" in shell.run_line("show")
    assert "note appended" in shell.run_line('note "补一条备注"')
    assert "Task #" in shell.run_line('edit title "改过标题"')
    assert "WAITING" in shell.run_line("edit status waiting")
    assert "DONE" in shell.run_line("done")
    assert "result appended" in shell.run_line('result "形成一个结果"')
    assert "Undone op" in shell.run_line("undo")

    text = (graph / "pages" / "对象测试项目.md").read_text(encoding="utf-8")
    assert "**[注]** 补一条备注" in text
    assert "WAITING 改过标题" in text or "DONE 改过标题" in text


def test_shell_clarify_proposal_apply_and_rollback_shortcut(tmp_path):
    _graph, conn, repo, settings = lifecycle_env(tmp_path)
    shell = HumanShellService(conn, settings)
    shell.run_line('project create "提案测试项目" --enter')
    shell.run_line('todo "需要归位的任务"')

    clarify = shell.run_line("clarify unplaced")
    assert "Project clarify completed" in clarify
    listing = shell.run_line("proposals")
    assert "link_object_to_node" in listing
    assert "Accepted proposal" in shell.run_line("accept 1")
    assert "link_object_to_node" in shell.run_line("preview 1")
    assert "Applied proposal" in shell.run_line("apply 1")
    assert "Rolled back proposal" in shell.run_line("rollback 1")

    health = ProjectLifecycleService(conn, settings).project_health(str(repo.resolve_object_id("提案测试项目")))
    assert health["unplaced_count"] >= 1
