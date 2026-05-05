import shutil
from pathlib import Path

import pytest

from task_manager_cli.adapters.logseq.adapter import LogseqAdapter
from task_manager_cli.config.settings import Settings
from task_manager_cli.core.errors import TaskManagerError
from task_manager_cli.ingest.merger import Merger
from task_manager_cli.proposals.service import ProposalService, classify_risk
from task_manager_cli.storage.database import connect, init_db
from task_manager_cli.storage.repositories import Repository


FIXTURE = Path(__file__).parent / "fixtures" / "logseq_graph"


def loaded_service(tmp_path, mode="guarded"):
    graph = tmp_path / "graph"
    shutil.copytree(FIXTURE, graph)
    conn = connect(tmp_path / "tm.sqlite3")
    init_db(conn)
    repo = Repository(conn)
    Merger(repo).ingest(LogseqAdapter(graph).scan())
    conn.commit()
    settings = Settings(app_dir=tmp_path / "app", database_path=tmp_path / "tm.sqlite3", logseq_graph_path=graph, write_mode=mode, write_backup_dir=tmp_path / "backups")
    return ProposalService(conn, settings), repo, graph, conn


def test_annotation_proposal_lifecycle_and_rollback(tmp_path):
    service, repo, _graph, conn = loaded_service(tmp_path)
    task = next(obj for obj in repo.list_objects("task", limit=20) if obj["title"] == "搭建索引器")
    proposal_id = service.create_annotation("内部注，不是 proposal 本身", target_object_ref=str(task["id"]))
    assert service.get(proposal_id)["risk"] == "low"

    service.accept(proposal_id)
    applied = service.apply(proposal_id)
    conn.commit()
    assert applied["status"] == "applied"
    assert service.get(proposal_id)["events"][-1]["event_type"] == "applied"
    assert repo.list_annotations(target_object_id=task["id"])

    rolled = service.rollback(proposal_id)
    conn.commit()
    assert rolled["status"] == "rolled_back"
    assert not repo.list_annotations(target_object_id=task["id"])


def test_reject_and_apply_requires_acceptance(tmp_path):
    service, repo, _graph, _conn = loaded_service(tmp_path)
    task = next(obj for obj in repo.list_objects("task", limit=20) if obj["title"] == "搭建索引器")
    proposal_id = service.create_annotation("x", target_object_ref=str(task["id"]))
    with pytest.raises(TaskManagerError):
        service.apply(proposal_id)
    service.reject(proposal_id)
    assert service.get(proposal_id)["status"] == "rejected"


def test_logseq_marker_preview_apply_and_rollback(tmp_path):
    service, repo, graph, conn = loaded_service(tmp_path)
    task = next(obj for obj in repo.list_objects("task", limit=20) if obj["title"] == "搭建索引器")
    target = graph / "pages" / "项目-Alpha.md"
    before = target.read_text(encoding="utf-8")
    proposal_id = service.create_logseq_marker("AI注", "先确认边界", target_object_ref=str(task["id"]))
    preview = service.preview(proposal_id)
    assert "+        - **[AI注]** 先确认边界" in preview["preview_diff"]
    assert target.read_text(encoding="utf-8") == before

    service.accept(proposal_id)
    service.apply(proposal_id, confirmed=True)
    conn.commit()
    assert "**[AI注]** 先确认边界" in target.read_text(encoding="utf-8")
    service.rollback(proposal_id)
    assert target.read_text(encoding="utf-8") == before


def test_marker_variants_and_task_marker_resync(tmp_path):
    service, repo, graph, conn = loaded_service(tmp_path)
    task = next(obj for obj in repo.list_objects("task", limit=20) if obj["title"] == "搭建索引器")
    for marker in ["注", "待澄清", "成果", "无成果"]:
        proposal_id = service.create_logseq_marker(marker, f"{marker} 内容", target_object_ref=str(task["id"]))
        service.preview(proposal_id)
        service.accept(proposal_id)
        service.apply(proposal_id, confirmed=True)
    marker_id = service.create_task_marker("WAITING", target_object_ref=str(task["id"]))
    service.preview(marker_id)
    service.accept(marker_id)
    service.apply(marker_id, confirmed=True)
    conn.commit()

    text = (graph / "pages" / "项目-Alpha.md").read_text(encoding="utf-8")
    assert "**[注]** 注 内容" in text
    assert "**[待澄清]** 待澄清 内容" in text
    assert "**[成果]** 成果 内容" in text
    assert "**[无成果]** 无成果 内容" in text
    resynced = LogseqAdapter(graph).scan()
    assert any(obj.status == "waiting" and obj.title == "搭建索引器" for obj in resynced.objects)
    assert any(rec.metadata.get("semantic_marker") == "成果" for rec in resynced.records)


def test_high_risk_cannot_batch_apply(tmp_path):
    service, _repo, _graph, _conn = loaded_service(tmp_path)
    high_id = service.create("delete", "Dangerous delete", {}, risk=classify_risk("delete"))
    service.accept(high_id)
    with pytest.raises(TaskManagerError):
        service.apply_many([high_id])
