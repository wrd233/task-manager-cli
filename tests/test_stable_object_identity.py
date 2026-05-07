from pathlib import Path

from task_manager_cli.adapters.logseq.adapter import LogseqAdapter
from task_manager_cli.ingest.merger import Merger
from tests.test_human_shell import loaded_shell


def test_status_writeback_keeps_object_id_and_show_updates(tmp_path):
    shell, repo, graph, conn = loaded_shell(tmp_path)
    task = next(item for item in repo.list_objects("task", limit=50) if item["title"] == "已有项目任务")
    task_id = task["id"]

    assert "DONE" in shell.run_line(f"done {task_id}")
    shown = shell.run_line(f"show {task_id}")
    assert f"#{task_id} task done" in shown

    Merger(repo).ingest(LogseqAdapter(graph).scan())
    conn.commit()
    same = repo.get_object(task_id)
    assert same["status"] == "done"
    same_line = conn.execute(
        """
        SELECT COUNT(*) AS c
        FROM objects o JOIN locations l ON l.id=o.canonical_location_id
        WHERE o.object_type='task' AND l.file_path=? AND l.line_start=?
        """,
        (task["file_path"], task["line_start"]),
    ).fetchone()["c"]
    assert same_line == 1


def test_edit_title_keeps_object_id_and_relations(tmp_path):
    shell, repo, _graph, conn = loaded_shell(tmp_path)
    task = next(item for item in repo.list_objects("task", limit=50) if item["title"] == "已有项目任务")
    project = next(item for item in repo.list_objects("project", limit=20) if item["title"] == "项目-韩国旅行")
    rel_before = conn.execute("SELECT COUNT(*) AS c FROM relations WHERE from_object_id=? AND to_object_id=?", (task["id"], project["id"])).fetchone()["c"]

    shell.input_func = lambda prompt="": "y"
    assert "title updated" in shell.run_line(f'edit task {task["id"]} title "稳定身份标题"')
    updated = repo.get_object(task["id"])
    rel_after = conn.execute("SELECT COUNT(*) AS c FROM relations WHERE from_object_id=? AND to_object_id=?", (task["id"], project["id"])).fetchone()["c"]

    assert updated["title"] == "稳定身份标题"
    assert rel_after == rel_before


def test_legacy_content_hash_source_id_matches_by_location(tmp_path):
    shell, repo, graph, conn = loaded_shell(tmp_path)
    task = next(item for item in repo.list_objects("task", limit=50) if item["title"] == "已有项目任务")
    legacy_source = f"{task['source_item_id']}:oldhash"
    conn.execute("UPDATE objects SET source_item_id=? WHERE id=?", (legacy_source, task["id"]))
    conn.commit()

    Merger(repo).ingest(LogseqAdapter(graph).scan())
    conn.commit()

    assert repo.get_object(task["id"])["source_item_id"] == task["source_item_id"]


def test_location_identity_does_not_update_into_existing_source_id(tmp_path):
    shell, repo, graph, conn = loaded_shell(tmp_path)
    task = next(item for item in repo.list_objects("task", limit=50) if item["title"] == "已有项目任务")
    conn.execute("UPDATE objects SET source_item_id=? WHERE id=?", (f"{task['source_item_id']}:oldhash", task["id"]))
    conn.execute(
        """
        INSERT INTO objects(object_type, title, status, canonical_source, source_item_id, canonical_location_id, confidence, metadata_json)
        VALUES ('idea', 'same source old type', 'captured', 'logseq', ?, ?, 0.5, '{}')
        """,
        (task["source_item_id"], task["canonical_location_id"]),
    )
    conn.commit()

    Merger(repo).ingest(LogseqAdapter(graph).scan())
    conn.commit()

    rows = conn.execute("SELECT id, object_type, source_item_id FROM objects WHERE source_item_id=?", (task["source_item_id"],)).fetchall()
    assert len(rows) == 1
    assert rows[0]["object_type"] == "task"
