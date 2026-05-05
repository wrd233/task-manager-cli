import shutil
from pathlib import Path

import pytest

from task_manager_cli.adapters.logseq.adapter import LogseqAdapter
from task_manager_cli.config.settings import Settings
from task_manager_cli.ingest.merger import Merger
from task_manager_cli.storage.database import connect, init_db
from task_manager_cli.storage.repositories import Repository
from task_manager_cli.writes.logseq_writer import WriteError
from task_manager_cli.writes.service import WriteService


FIXTURE = Path(__file__).parent / "fixtures" / "logseq_graph"


def loaded_write_service(tmp_path, mode="proposal"):
    graph = tmp_path / "graph"
    shutil.copytree(FIXTURE, graph)
    conn = connect(tmp_path / "tm.sqlite3")
    init_db(conn)
    repo = Repository(conn)
    Merger(repo).ingest(LogseqAdapter(graph).scan())
    conn.commit()
    settings = Settings(
        app_dir=tmp_path / "app",
        database_path=tmp_path / "tm.sqlite3",
        logseq_graph_path=graph,
        write_mode=mode,
        write_backup_dir=tmp_path / "backups",
    )
    return WriteService(conn, settings), repo, graph, conn


def test_append_child_proposal_does_not_write_until_apply(tmp_path):
    service, repo, graph, conn = loaded_write_service(tmp_path, mode="proposal")
    task = next(obj for obj in repo.list_objects("task", limit=20) if obj["title"] == "搭建索引器")
    target = graph / "pages" / "项目-Alpha.md"
    before = target.read_text(encoding="utf-8")

    proposal_id = service.create_append_child_proposal("[Agent建议] 先做写入预览", target_object_ref=str(task["id"]))
    conn.commit()

    assert target.read_text(encoding="utf-8") == before
    proposal = service.preview(proposal_id)
    assert "+        - [Agent建议] 先做写入预览" in proposal["preview_diff"]


def test_guarded_apply_appends_and_creates_backup(tmp_path):
    service, repo, graph, conn = loaded_write_service(tmp_path, mode="guarded")
    task = next(obj for obj in repo.list_objects("task", limit=20) if obj["title"] == "搭建索引器")
    proposal_id = service.create_append_child_proposal("[Agent建议] 可以安全追加", target_object_ref=str(task["id"]))
    result = service.apply(proposal_id, confirmed=True)
    conn.commit()

    text = (graph / "pages" / "项目-Alpha.md").read_text(encoding="utf-8")
    assert "        - [Agent建议] 可以安全追加" in text
    assert result["backup_path"]
    assert Path(result["backup_path"]).exists()


def test_apply_refuses_when_file_changed_after_proposal(tmp_path):
    service, repo, graph, conn = loaded_write_service(tmp_path, mode="guarded")
    task = next(obj for obj in repo.list_objects("task", limit=20) if obj["title"] == "搭建索引器")
    proposal_id = service.create_append_child_proposal("[Agent建议] 会被拒绝", target_object_ref=str(task["id"]))
    target = graph / "pages" / "项目-Alpha.md"
    target.write_text(target.read_text(encoding="utf-8") + "\n- 外部修改\n", encoding="utf-8")

    with pytest.raises(WriteError):
        service.apply(proposal_id, confirmed=True)


def test_append_section_and_create_page_proposals(tmp_path):
    service, repo, graph, conn = loaded_write_service(tmp_path, mode="guarded")
    project = repo.list_objects("project", limit=1)[0]
    section_id = service.create_append_page_section_proposal("[Agent反思] 保持 append-only", "[反思]", target_object_ref=str(project["id"]))
    page_id = service.create_page_proposal("Agent Inbox", "[Agent建议] 新页面")
    service.apply(section_id, confirmed=True)
    service.apply(page_id, confirmed=True)
    conn.commit()

    assert "[Agent反思] 保持 append-only" in (graph / "pages" / "项目-Alpha.md").read_text(encoding="utf-8")
    assert (graph / "pages" / "Agent Inbox.md").exists()
