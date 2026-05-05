import json
import os
import shutil
import subprocess
from pathlib import Path

from task_manager_cli.adapters.logseq.adapter import LogseqAdapter
from task_manager_cli.clarify.service import ClarifyService
from task_manager_cli.config.settings import Settings
from task_manager_cli.ingest.merger import Merger
from task_manager_cli.storage.database import connect, init_db
from task_manager_cli.storage.repositories import Repository


FIXTURE = Path(__file__).parent / "fixtures" / "logseq_graph"
ROOT = Path(__file__).resolve().parents[1]


def loaded_clarify(tmp_path):
    graph = tmp_path / "graph"
    shutil.copytree(FIXTURE, graph)
    conn = connect(tmp_path / "tm.sqlite3")
    init_db(conn)
    repo = Repository(conn)
    Merger(repo).ingest(LogseqAdapter(graph).scan())
    conn.commit()
    settings = Settings(app_dir=tmp_path / "app", database_path=tmp_path / "tm.sqlite3", logseq_graph_path=graph, write_mode="guarded", write_backup_dir=tmp_path / "backups")
    return ClarifyService(conn, settings), repo, conn, graph


def test_clarify_selected_records_questions_answers_and_generates_proposals(tmp_path):
    service, repo, conn, graph = loaded_clarify(tmp_path)
    task = next(obj for obj in repo.list_objects("task", limit=20) if obj["title"] == "搭建索引器")
    target = graph / "pages" / "项目-Alpha.md"
    before = target.read_text(encoding="utf-8")

    result = service.start_selected([str(task["id"])], answer="仍有价值，先沉淀 AI 注", provider_name="mock")
    conn.commit()

    review = service.reviews.show(result["review_id"])
    clarify = review["items"][0]["metadata"]["clarify"]
    assert clarify["status"] == "proposal_generated"
    assert len(clarify["questions"]) >= 7
    assert clarify["answers"][0]["answer"] == "仍有价值，先沉淀 AI 注"
    assert review["proposals"]
    assert "accept / reject / edit / apply" in result["table"]
    assert review["proposals"][0]["status"] == "suggested"
    assert target.read_text(encoding="utf-8") == before
    assert repo.get_object(task["id"])["status"] == task["status"]


def test_clarify_skip_and_provider_failure_can_resume(tmp_path):
    service, repo, conn, _graph = loaded_clarify(tmp_path)
    tasks = repo.list_objects("task", limit=20)[:2]

    skipped = service.start_selected([str(tasks[0]["id"])], skip_reason="not now", provider_name="mock")
    failed = service.start_selected([str(tasks[1]["id"])], answer="会触发失败", provider_name="invalid-json")
    conn.commit()

    assert service.reviews.show(skipped["review_id"])["items"][0]["metadata"]["clarify"]["status"] == "skipped"
    failed_item = service.reviews.show(failed["review_id"])["items"][0]
    assert failed_item["metadata"]["clarify"]["status"] == "failed"
    resumed = service.resume(failed["review_id"], answer="重试并生成建议", provider_name="mock")
    assert resumed["proposals"]


def test_clarify_dry_run_payload_preview_is_redacted_and_does_not_generate_proposals(tmp_path):
    service, repo, conn, _graph = loaded_clarify(tmp_path)
    task = next(obj for obj in repo.list_objects("task", limit=20) if obj["title"] == "搭建索引器")

    result = service.start_selected(
        [str(task["id"])],
        answer="token=abc123 password=secret cookie: session_id api key: sk-1234567890abcdef",
        provider_name="dry-run",
    )
    conn.commit()

    rendered = json.dumps(result["payload_previews"], ensure_ascii=False)
    assert "[REDACTED]" in rendered
    assert "abc123" not in rendered
    assert "secret" not in rendered
    assert "sk-1234567890abcdef" not in rendered
    assert result["proposals"] == []


def test_clarify_cli_selected_creates_review(tmp_path):
    service, repo, conn, graph = loaded_clarify(tmp_path)
    task = next(obj for obj in repo.list_objects("task", limit=20) if obj["title"] == "搭建索引器")
    conn.close()
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    env["TM_APP_DIR"] = str(tmp_path / "app")
    env["TM_DATABASE_PATH"] = str(tmp_path / "tm.sqlite3")
    env["TM_LOGSEQ_GRAPH"] = str(graph)
    proc = subprocess.run(
        [
            "python3",
            "-m",
            "task_manager_cli.cli.main",
            "clarify",
            "selected",
            "--ids",
            str(task["id"]),
            "--answer",
            "CLI clarify answer",
            "--provider",
            "mock",
            "--format",
            "json",
        ],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    data = json.loads(proc.stdout)
    assert data["review_id"]
    assert data["proposals"]
