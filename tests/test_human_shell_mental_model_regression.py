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


def test_shell_help_names_the_core_mental_model(tmp_path):
    _graph, conn, _repo, settings = lifecycle_env(tmp_path)
    shell = HumanShellService(conn, settings)
    help_text = shell.run_line("help")

    assert "/today 今日现场" in help_text
    assert "/dashboard 全局态势" in help_text
    assert "/projects 项目空间" in help_text
    assert "tree 看结构" in help_text
    assert "ls 看可操作对象" in help_text
    assert "show 看当前内容" in help_text
    assert "find 在当前上下文搜索" in help_text
    assert "rollback" in help_text


def test_show_without_target_uses_current_context(tmp_path):
    _graph, conn, _repo, settings = lifecycle_env(tmp_path)
    shell = HumanShellService(conn, settings)

    assert "Context:" in shell.run_line("show") or "empty" in shell.run_line("show")
    shell.run_line("cd /projects")
    shell.run_line('project create "上下文展示项目"')
    output = shell.run_line("show")

    assert "Project #" in output
    assert "结构：" in output
