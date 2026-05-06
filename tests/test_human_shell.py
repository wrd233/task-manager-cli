import os
import subprocess
from datetime import date
from pathlib import Path

from task_manager_cli.adapters.logseq.adapter import LogseqAdapter
from task_manager_cli.config.settings import Settings
from task_manager_cli.ingest.merger import Merger
from task_manager_cli.proposals.service import ProposalService
from task_manager_cli.shell.service import HumanShellService
from task_manager_cli.storage.database import connect, init_db
from task_manager_cli.storage.repositories import Repository


ROOT = Path(__file__).resolve().parents[1]


def loaded_shell(tmp_path):
    graph = tmp_path / "graph"
    pages = graph / "pages"
    journals = graph / "journals"
    pages.mkdir(parents=True)
    journals.mkdir()
    today = date.today().strftime("%Y_%m_%d")
    (pages / "项目-韩国旅行.md").write_text(
        "PARA:: [[PARA/Project]]\n\n"
        "- **[工作流]** 出行交通\n"
        "    - **[具体事务]**\n"
        "        - TODO 已有项目任务\n"
        "    - **[资源]**\n"
        "    - **[想法]**\n"
        "    - **[小任务]** 整理打车攻略\n"
        "        - TODO 查询 Kakao T\n",
        encoding="utf-8",
    )
    (journals / f"{today}.md").write_text("- TODO 今日已有任务 #inbox\n", encoding="utf-8")
    conn = connect(tmp_path / "tm.sqlite3")
    init_db(conn)
    repo = Repository(conn)
    Merger(repo).ingest(LogseqAdapter(graph).scan())
    conn.commit()
    settings = Settings(
        app_dir=tmp_path / "app",
        database_path=tmp_path / "tm.sqlite3",
        logseq_graph_path=graph,
        write_mode="guarded",
        write_backup_dir=tmp_path / "backups",
    )
    return HumanShellService(conn, settings), repo, graph, conn


def test_shell_cli_starts_help_and_exit(tmp_path):
    shell, _repo, graph, conn = loaded_shell(tmp_path)
    conn.close()
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    env["TM_APP_DIR"] = str(tmp_path / "app")
    env["TM_DATABASE_PATH"] = str(tmp_path / "tm.sqlite3")
    env["TM_LOGSEQ_GRAPH"] = str(graph)
    proc = subprocess.run(
        ["python3", "-m", "task_manager_cli.cli.main", "shell"],
        cwd=ROOT,
        env=env,
        input="help\npwd\nexit\n",
        text=True,
        capture_output=True,
        check=True,
    )
    assert "Human Shell v1" in proc.stdout
    assert "Human Shell commands" in proc.stdout
    assert "/today" in proc.stdout


def test_shell_navigation_and_tree(tmp_path):
    shell, _repo, _graph, _conn = loaded_shell(tmp_path)
    assert shell.run_line("pwd") == "/today"
    assert shell.run_line("cd /projects") == "/projects"
    assert "项目-韩国旅行" in shell.run_line("ls")
    assert shell.run_line("cd /projects/项目-韩国旅行") == "/projects/项目-韩国旅行"
    assert "项目树" in shell.run_line("tree")
    assert shell.run_line("cd 工作流/出行交通") == "/projects/项目-韩国旅行/工作流/出行交通"
    assert shell.run_line("cd ..") == "/projects/项目-韩国旅行/工作流"
    assert shell.run_line("cd -") == "/projects/项目-韩国旅行/工作流/出行交通"
    assert "Path not found" in shell.run_line("cd /projects/不存在")


def test_shell_direct_actions_write_resync_and_undo(tmp_path):
    shell, repo, graph, _conn = loaded_shell(tmp_path)
    today_path = graph / "journals" / f"{date.today().strftime('%Y_%m_%d')}.md"
    assert "written" in shell.run_line('todo "确认韩国打车 App 是否需要韩国手机号"')
    assert "TODO 确认韩国打车 App" in today_path.read_text(encoding="utf-8")
    assert any("确认韩国打车 App" in item["title"] for item in repo.list_objects("task", limit=100))
    assert "Undone op" in shell.run_line("undo")
    assert "确认韩国打车 App" not in today_path.read_text(encoding="utf-8")

    shell.run_line("cd /projects/项目-韩国旅行")
    page = graph / "pages" / "项目-韩国旅行.md"
    shell.run_line('todo "整理项目页落位"')
    shell.run_line('idea "返点公司可以做一个风险评分表"')
    shell.run_line('mini "整理出行交通方案"')
    shell.run_line('resource "Kakao T 官方说明 https://example.com"')
    text = page.read_text(encoding="utf-8")
    assert "TODO 整理项目页落位" in text
    assert "**[想法]** 返点公司可以做一个风险评分表" in text
    assert "**[小任务]** 整理出行交通方案" in text
    assert "**[资源]** Kakao T 官方说明" in text
    assert not any("Kakao T 官方说明" in item["title"] for item in repo.list_objects("task", limit=200))


def test_shell_project_node_mini_status_markers_and_undo(tmp_path):
    shell, repo, graph, _conn = loaded_shell(tmp_path)
    shell.run_line("cd /projects/项目-韩国旅行/工作流/出行交通")
    assert "written" in shell.run_line('todo "查询海外信用卡"')
    page = graph / "pages" / "项目-韩国旅行.md"
    assert "    - TODO 查询海外信用卡" in page.read_text(encoding="utf-8")

    task = next(item for item in repo.list_objects("task", limit=100) if item["title"] == "查询海外信用卡")
    assert "DOING" in shell.run_line(f"doing {task['id']}")
    assert "DOING 查询海外信用卡" in page.read_text(encoding="utf-8")
    assert "DONE" in shell.run_line(f"done {task['id']}")
    assert "可输入 result" in shell.run_line(f"done {task['id']}")
    assert "WAITING" in shell.run_line(f'wait {task["id"]} "等客服回复"')
    assert "**[注]** 等客服回复" in page.read_text(encoding="utf-8")
    assert "result appended" in shell.run_line(f'result {task["id"]} "形成初稿"')
    assert "**[成果]** 形成初稿" in page.read_text(encoding="utf-8")
    assert "noresult appended" in shell.run_line(f'noresult {task["id"]} "无需沉淀"')
    assert "note appended" in shell.run_line(f'note {task["id"]} "先查官方"')
    assert "ainote appended" in shell.run_line(f'ainote {task["id"]} "建议比较方案"')
    assert "Undone op" in shell.run_line("undo")
    assert "**[AI注]** 建议比较方案" not in page.read_text(encoding="utf-8")

    mini = next(item for item in repo.list_objects("mini_project", limit=50) if item["title"] == "整理打车攻略")
    assert shell.run_line(f"cd /mini/{mini['title']}").startswith("/mini/")
    assert "written" in shell.run_line('todo "补充 mini 子任务"')
    assert "TODO 补充 mini 子任务" in page.read_text(encoding="utf-8")


def test_shell_today_journal_creation_and_proposal_shortcuts(tmp_path):
    shell, repo, graph, conn = loaded_shell(tmp_path)
    today_path = graph / "journals" / f"{date.today().strftime('%Y_%m_%d')}.md"
    today_path.unlink()
    assert "written" in shell.run_line('todo "创建今日 journal"')
    assert today_path.exists()
    assert "创建今日 journal" in today_path.read_text(encoding="utf-8")
    assert "Undone op" in shell.run_line("undo")
    assert not today_path.exists()

    task = next(item for item in repo.list_objects("task", limit=100) if item["title"] == "已有项目任务")
    proposal_id = ProposalService(conn, shell.settings).create_logseq_marker("AI注", "proposal note", target_object_ref=str(task["id"]))
    conn.commit()
    listing = shell.run_line("proposals")
    assert f"#{proposal_id}" in listing
    assert "Accepted" in shell.run_line("accept 1")
    assert "proposal note" in shell.run_line("preview 1")
    assert "Applied proposal" in shell.run_line("apply 1")
    assert "Rolled back proposal" in shell.run_line("undo")


def test_shell_clarify_provider_off_dry_run_and_mock(tmp_path):
    shell, repo, _graph, _conn = loaded_shell(tmp_path)
    answers = iter(["有", "行动", "是", "否", "否", "否", "记录", "具体事务", "否", "quit"])
    shell.input_func = lambda prompt="": next(answers)
    shell.run_line("provider off")
    result = shell.run_line("clarify")
    assert "Clarify paused" in result or "Clarify completed" in result

    shell.run_line("provider dry-run")
    answers = iter(["有", "行动", "是", "否", "否", "否", "记录", "具体事务", "否", "quit"])
    shell.input_func = lambda prompt="": next(answers)
    result = shell.run_line("clarify")
    assert "Payload previews" in result or "Clarify paused" in result

    shell.run_line("cd /projects/项目-韩国旅行")
    shell.run_line("provider mock")
    answers = iter(["有", "行动", "项目纳管", "否", "否", "否", "记录", "具体事务", "否"] * 5)
    shell.input_func = lambda prompt="": next(answers)
    result = shell.run_line("clarify")
    assert "Clarify completed" in result
    assert "link_to_project" in result or "logseq_append_marker" in result
