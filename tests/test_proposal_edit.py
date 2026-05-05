import shutil
from pathlib import Path

import pytest

from task_manager_cli.adapters.logseq.adapter import LogseqAdapter
from task_manager_cli.config.settings import Settings
from task_manager_cli.core.errors import TaskManagerError
from task_manager_cli.ingest.merger import Merger
from task_manager_cli.proposals.service import ProposalService
from task_manager_cli.storage.database import connect, init_db
from task_manager_cli.storage.repositories import Repository


FIXTURE = Path(__file__).parent / "fixtures" / "logseq_graph"


def loaded_service(tmp_path):
    graph = tmp_path / "graph"
    shutil.copytree(FIXTURE, graph)
    conn = connect(tmp_path / "tm.sqlite3")
    init_db(conn)
    repo = Repository(conn)
    Merger(repo).ingest(LogseqAdapter(graph).scan())
    conn.commit()
    settings = Settings(app_dir=tmp_path / "app", database_path=tmp_path / "tm.sqlite3", logseq_graph_path=graph, write_mode="guarded", write_backup_dir=tmp_path / "backups")
    return ProposalService(conn, settings), repo, conn


def test_edit_unsafely_does_not_apply_and_history_is_kept(tmp_path):
    service, repo, conn = loaded_service(tmp_path)
    task = next(obj for obj in repo.list_objects("task", limit=20) if obj["title"] == "搭建索引器")
    proposal_id = service.create_logseq_marker("AI注", "old", target_object_ref=str(task["id"]))
    edited = service.edit(proposal_id, content="new", risk="medium")
    assert edited["status"] == "edited"
    assert edited["payload"]["content"] == "new"
    assert any(event["event_type"] == "edited" for event in service.get(proposal_id)["events"])
    service.preview(proposal_id)
    service.accept(proposal_id)
    assert service.apply(proposal_id, confirmed=True)["status"] == "applied"
    with pytest.raises(TaskManagerError):
        service.edit(proposal_id, content="silent")


def test_supersede_old_proposal_and_apply_new(tmp_path):
    service, repo, conn = loaded_service(tmp_path)
    task = next(obj for obj in repo.list_objects("task", limit=20) if obj["title"] == "搭建索引器")
    old_id = service.create_annotation("old", target_object_ref=str(task["id"]))
    new_id = service.create_annotation("new", target_object_ref=str(task["id"]))
    service.supersede(old_id, new_id)
    assert service.get(old_id)["status"] == "superseded"
    service.accept(new_id)
    service.apply(new_id)
    conn.commit()
    assert repo.list_annotations(target_object_id=task["id"])[0]["content"] == "new"
