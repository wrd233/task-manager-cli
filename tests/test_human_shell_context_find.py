import json

from task_manager_cli.adapters.logseq.adapter import LogseqAdapter
from task_manager_cli.ingest.merger import Merger
from tests.test_human_shell import loaded_shell


def test_find_is_context_first_and_global_flag_keeps_global(tmp_path):
    shell, repo, _graph, conn = loaded_shell(tmp_path)
    unrelated = repo.list_objects("task", limit=50)[0]
    loc_id = conn.execute(
        """
        INSERT INTO locations(source_type, source_item_id, file_path, page_name, line_start)
        VALUES('logseq', 'manual:global', '/tmp/global.md', 'Global', 1)
        """
    ).lastrowid
    conn.execute(
        """
        INSERT INTO objects(object_type, title, status, canonical_source, source_item_id, canonical_location_id, confidence, metadata_json)
        VALUES('task', 'Kakao 全局噪声', 'todo', 'logseq', 'manual:global', ?, 1.0, '{}')
        """,
        (loc_id,),
    )
    conn.commit()

    shell.run_line("cd /projects/项目-韩国旅行")
    local = shell.run_line("find Kakao")
    global_result = shell.run_line("find --global Kakao")

    assert "查询 Kakao T" in local
    assert "Kakao 全局噪声" not in local.splitlines()[0]
    assert "[global]" in global_result


def test_find_dedupes_same_source_location(tmp_path):
    shell, repo, _graph, conn = loaded_shell(tmp_path)
    task = next(item for item in repo.list_objects("task", limit=50) if item["title"] == "已有项目任务")
    loc_id = conn.execute(
        """
        INSERT INTO locations(source_type, source_item_id, file_path, page_name, line_start)
        VALUES('logseq', 'dup:loc', ?, ?, ?)
        """,
        (task["file_path"], task["page_name"], task["line_start"]),
    ).lastrowid
    conn.execute(
        """
        INSERT INTO objects(object_type, title, status, canonical_source, source_item_id, canonical_location_id, confidence, metadata_json)
        VALUES('task', ?, 'todo', 'logseq', 'dup:obj', ?, 1.0, ?)
        """,
        (task["title"], loc_id, json.dumps({})),
    )
    conn.commit()

    output = shell.run_line("find 已有项目任务")
    assert output.count("已有项目任务") == 1
    assert "duplicate source-location objects hidden" in output


def test_ls_tasks_includes_project_page_relation_and_journal_link(tmp_path):
    shell, repo, graph, conn = loaded_shell(tmp_path)
    (graph / "journals" / "2026_05_05.md").write_text(
        "- TODO [[项目-韩国旅行]] journal linked task\n"
        "- TODO unrelated journal task\n",
        encoding="utf-8",
    )
    Merger(repo).ingest(LogseqAdapter(graph).scan())
    conn.commit()

    shell.run_line("cd /projects/项目-韩国旅行")
    output = shell.run_line("ls tasks")
    assert "已有项目任务" in output
    assert "journal linked task" in output
    assert "unrelated journal task" not in output
    assert "[relation]" in output or "[page]" in output
    assert "[journal-link]" in output
