from datetime import date

from task_manager_cli.adapters.logseq.adapter import LogseqAdapter
from task_manager_cli.config.settings import Settings
from task_manager_cli.ingest.merger import Merger
from task_manager_cli.proposals.service import ProposalService
from task_manager_cli.reviews.service import ReviewSessionService
from task_manager_cli.shell.service import HumanShellService
from task_manager_cli.storage.database import connect, init_db
from task_manager_cli.storage.repositories import Repository


def dashboard_shell(tmp_path):
    graph = tmp_path / "graph"
    pages = graph / "pages"
    journals = graph / "journals"
    pages.mkdir(parents=True)
    journals.mkdir()
    today = date.today().strftime("%Y_%m_%d")
    (pages / "项目-仪表盘.md").write_text(
        "PARA:: [[PARA/Project]]\n\n"
        "- **[工作流]** 全局工作\n"
        "    - TODO 全局旧任务\n"
        "        id:: 11111111-1111-1111-1111-111111111111\n"
        "    - TODO 全局未暴露任务\n"
        "    - WAITING 等待外部回复\n",
        encoding="utf-8",
    )
    (journals / f"{today}.md").write_text(
        "- TODO 今日直接任务\n"
        "- **[想法]** 今日想法\n"
        "- **[成果]** 今日成果\n"
        "- ((11111111-1111-1111-1111-111111111111))\n",
        encoding="utf-8",
    )
    conn = connect(tmp_path / "tm.sqlite3")
    init_db(conn)
    repo = Repository(conn)
    Merger(repo).ingest(LogseqAdapter(graph).scan())
    settings = Settings(
        app_dir=tmp_path / "app",
        database_path=tmp_path / "tm.sqlite3",
        logseq_graph_path=graph,
        write_mode="guarded",
        write_backup_dir=tmp_path / "backups",
    )
    proposal_id = ProposalService(conn, settings).create_annotation("需要审核", target_object_ref=str(repo.list_objects("task", limit=10)[0]["id"]))
    review_id = ReviewSessionService(conn).start("shell:clarify", item_refs=[], title="Open clarify")
    conn.commit()
    return HumanShellService(conn, settings), repo, proposal_id, review_id


def test_today_is_journal_fact_view_not_global_task_pool(tmp_path):
    shell, _repo, _proposal_id, _review_id = dashboard_shell(tmp_path)
    shell.run_line("cd /today")

    default = shell.run_line("ls")
    assert "Journal" in default
    assert "今日直接任务" in default
    assert "今日想法" in default
    assert "今日成果" in default
    assert "全局未暴露任务" not in default

    tasks = shell.run_line("ls tasks")
    assert "今日直接任务" in tasks
    assert "全局旧任务" not in tasks
    assert "全局未暴露任务" not in tasks


def test_today_subviews_exposed_results_ideas_and_empty_state(tmp_path):
    shell, _repo, _proposal_id, _review_id = dashboard_shell(tmp_path)
    shell.run_line("cd /today")
    assert "全局旧任务" in shell.run_line("ls exposed")
    assert "今日成果" in shell.run_line("ls results")
    assert "今日想法" in shell.run_line("ls ideas")

    shell.context.journal_date = "2099-01-01"
    empty = shell.run_line("ls")
    assert "Today journal not found or empty" in empty


def test_dashboard_carries_global_active_view_and_completion(tmp_path):
    shell, _repo, proposal_id, review_id = dashboard_shell(tmp_path)
    assert shell.run_line("cd /dashboard") == "/dashboard"

    default = shell.run_line("ls")
    assert "Active Projects" in default
    assert "Active Tasks" in default
    assert "Pending Proposals" in default
    assert "Open Reviews" in default

    assert "全局旧任务" in shell.run_line("ls tasks")
    assert "项目-仪表盘" in shell.run_line("ls projects")
    assert "等待外部回复" in shell.run_line("ls waiting")
    assert f"proposal:{proposal_id}" in shell.run_line("ls proposals")
    assert f"#{review_id}" in shell.run_line("ls reviews")

    completion = shell.run_line("complete cd /d")
    assert "/dashboard" in completion
