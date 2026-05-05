from pathlib import Path

from task_manager_cli.adapters.logseq.adapter import LogseqAdapter
from task_manager_cli.annotations.service import AnnotationService
from task_manager_cli.ingest.merger import Merger
from task_manager_cli.storage.database import connect, init_db
from task_manager_cli.storage.repositories import Repository


FIXTURE = Path(__file__).parent / "fixtures" / "logseq_graph"


def test_annotation_add_list_update(tmp_path):
    conn = connect(tmp_path / "tm.sqlite3")
    init_db(conn)
    repo = Repository(conn)
    Merger(repo).ingest(LogseqAdapter(FIXTURE).scan())
    conn.commit()
    task = next(obj for obj in repo.list_objects("task", limit=20) if obj["title"] == "搭建索引器")
    service = AnnotationService(conn)
    ann_id = service.add(str(task["id"]), "建议继续保持只读边界", author="agent", annotation_type="suggestion")
    service.update_status(ann_id, "accepted")
    items = service.list(str(task["id"]))
    assert items[0]["status"] == "accepted"
    assert "只读边界" in items[0]["content"]


def test_annotation_can_target_record_and_context_can_omit_annotations(tmp_path):
    conn = connect(tmp_path / "tm.sqlite3")
    init_db(conn)
    repo = Repository(conn)
    Merger(repo).ingest(LogseqAdapter(FIXTURE).scan())
    conn.commit()
    task = next(obj for obj in repo.list_objects("task", limit=20) if obj["title"] == "搭建索引器")
    record = repo.definition_record_for_object(int(task["id"]))
    service = AnnotationService(conn)
    ann_id = service.add(None, "record-level note", author="agent", annotation_type="comment", target_record_ref=str(record["id"]))
    items = service.list(target_record_ref=str(record["id"]))
    assert items[0]["id"] == ann_id
    context = __import__("task_manager_cli.query.service", fromlist=["QueryService"]).QueryService(conn).object_context(str(task["id"]), include_annotations=False)
    assert context["annotations"] == []
