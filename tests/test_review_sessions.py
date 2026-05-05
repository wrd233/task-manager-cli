import shutil
from pathlib import Path

from task_manager_cli.adapters.logseq.adapter import LogseqAdapter
from task_manager_cli.config.settings import Settings
from task_manager_cli.ingest.merger import Merger
from task_manager_cli.proposals.service import ProposalService
from task_manager_cli.reviews.service import ReviewSessionService
from task_manager_cli.storage.database import connect, init_db
from task_manager_cli.storage.repositories import Repository


FIXTURE = Path(__file__).parent / "fixtures" / "logseq_graph"


def loaded_services(tmp_path):
    graph = tmp_path / "graph"
    shutil.copytree(FIXTURE, graph)
    conn = connect(tmp_path / "tm.sqlite3")
    init_db(conn)
    repo = Repository(conn)
    Merger(repo).ingest(LogseqAdapter(graph).scan())
    conn.commit()
    settings = Settings(app_dir=tmp_path / "app", database_path=tmp_path / "tm.sqlite3", logseq_graph_path=graph, write_mode="guarded")
    return ReviewSessionService(conn), ProposalService(conn, settings), repo, conn


def test_review_session_lifecycle_and_proposals(tmp_path):
    reviews, proposals, repo, conn = loaded_services(tmp_path)
    task = next(obj for obj in repo.list_objects("task", limit=20) if obj["title"] == "搭建索引器")
    review_id = reviews.start("selected", item_refs=[str(task["id"])])
    proposal_id = proposals.create_annotation("审核时发现的注", target_object_ref=str(task["id"]), review_session_id=review_id)
    reviews.attach_proposal(review_id, proposal_id)
    reviews.set_status(review_id, "in_progress")
    reviews.set_status(review_id, "paused")
    reviews.set_status(review_id, "in_progress")
    reviews.close(review_id)
    conn.commit()

    shown = reviews.show(review_id)
    assert shown["status"] == "completed"
    assert shown["items"][0]["object_id"] == task["id"]
    assert shown["proposals"][0]["id"] == proposal_id
    assert any(event["event_type"] == "status_paused" for event in shown["events"])
    assert reviews.list(status="completed")[0]["id"] == review_id
