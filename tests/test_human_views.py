from pathlib import Path

from task_manager_cli.adapters.logseq.adapter import LogseqAdapter
from task_manager_cli.ingest.merger import Merger
from task_manager_cli.query.human_views import HumanViewService
from task_manager_cli.storage.database import connect, init_db
from task_manager_cli.storage.repositories import Repository


FIXTURE = Path(__file__).parent / "fixtures" / "logseq_graph"


def loaded_view(tmp_path):
    conn = connect(tmp_path / "tm.sqlite3")
    init_db(conn)
    repo = Repository(conn)
    Merger(repo).ingest(LogseqAdapter(FIXTURE, ignored_embed_uuids=["dddddddd-1111-1111-1111-111111111111"]).scan())
    conn.commit()
    return HumanViewService(conn), repo


def assert_human_view(text: str):
    assert "metadata" not in text.lower()
    assert "confidence" not in text.lower()
    assert "canonical_source" not in text
    assert '"objects"' not in text
    assert "{" not in text


def test_today_view_is_short_and_grouped(tmp_path):
    view, repo = loaded_view(tmp_path)
    text = view.today(limit=5)
    assert "Today" in text
    assert "Recent unfinished" in text
    assert "Active projects" in text
    assert "tm show" in text
    assert_human_view(text)


def test_project_view_has_stats_without_full_records(tmp_path):
    view, repo = loaded_view(tmp_path)
    text = view.project("项目-韩国旅行", limit=5)
    assert "Project #" in text
    assert "Tasks todo/doing/done" in text
    assert "Open tasks" in text
    assert "tm context" in text
    assert_human_view(text)


def test_tasks_ideas_inbox_projects_views(tmp_path):
    view, repo = loaded_view(tmp_path)
    outputs = [
        view.projects(limit=5),
        view.tasks(limit=5),
        view.ideas(limit=5),
        view.inbox(limit=5),
    ]
    assert any("项目-韩国旅行" in text for text in outputs)
    assert any("Tasks" in text for text in outputs)
    assert any("Ideas" in text for text in outputs)
    assert any("Inbox" in text for text in outputs)
    for text in outputs:
        assert_human_view(text)


def test_detail_view_adds_attention_signals_but_not_metadata(tmp_path):
    view, repo = loaded_view(tmp_path)
    text = view.project("项目-韩国旅行", limit=5, detail=True)
    assert "activity" in text or "notes" in text
    assert_human_view(text)
