from pathlib import Path

from task_manager_cli.adapters.logseq.adapter import LogseqAdapter
from task_manager_cli.ingest.merger import Merger
from task_manager_cli.query.service import QueryService
from task_manager_cli.storage.database import connect, init_db
from task_manager_cli.storage.repositories import Repository


FIXTURE = Path(__file__).parent / "fixtures" / "logseq_graph"


def loaded_service(tmp_path):
    conn = connect(tmp_path / "tm.sqlite3")
    init_db(conn)
    Merger(Repository(conn)).ingest(LogseqAdapter(FIXTURE).scan())
    conn.commit()
    return QueryService(conn)


def test_object_context_contains_child_records(tmp_path):
    service = loaded_service(tmp_path)
    task = next(obj for obj in service.list_objects("task", limit=20) if obj["title"] == "搭建索引器")
    context = service.object_context(str(task["id"]), redact=True)
    raw = "\n".join(record["raw_text"] for record in context["records"])
    normalized = "\n".join(record["normalized_text"] for record in context["records"])
    assert "SQLite schema" in raw
    assert "[REDACTED" in raw
    assert "supersecret" not in normalized


def test_agent_context_json_shape(tmp_path):
    service = loaded_service(tmp_path)
    context = service.agent_context(object_type="project", limit=5)
    assert context["packages"]
    assert context["packages"][0]["objects"][0]["object_type"] == "project"
