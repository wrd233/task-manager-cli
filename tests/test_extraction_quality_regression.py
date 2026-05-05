from pathlib import Path

from task_manager_cli.adapters.logseq.adapter import LogseqAdapter
from task_manager_cli.adapters.logseq.extractors import parse_idea, suspicious_idea_reason
from task_manager_cli.ingest.merger import Merger
from task_manager_cli.query.agent_views import AgentViewService
from task_manager_cli.query.service import QueryService
from task_manager_cli.storage.database import connect, init_db
from task_manager_cli.storage.repositories import Repository


FIXTURE = Path(__file__).parent / "fixtures" / "logseq_graph"


def load_repo(tmp_path):
    conn = connect(tmp_path / "tm.sqlite3")
    init_db(conn)
    repo = Repository(conn)
    Merger(repo).ingest(LogseqAdapter(FIXTURE, ignored_embed_uuids=["dddddddd-1111-1111-1111-111111111111"]).scan())
    conn.commit()
    return conn, repo


def test_idea_marker_parser_rejects_wiki_links_and_fragments():
    assert parse_idea("- **[想法]** 韩国旅行可以加入书店") == "韩国旅行可以加入书店"
    assert parse_idea("- [随想] 日语学习可以和旅行结合") == "日语学习可以和旅行结合"
    assert parse_idea("- [[想法]]") is None
    assert parse_idea("- [[随想]]：这个是 wiki link 解释") is None
    assert parse_idea("- 检查[[想法]]页面") is None
    assert parse_idea("- Readwise highlight: 有想法两个字") is None
    assert parse_idea("- [想法] ]") is None
    assert suspicious_idea_reason("- [[想法]]") == "wiki_link_marker_only"


def test_adapter_does_not_create_broken_idea_titles_or_structural_embed_tasks():
    result = LogseqAdapter(FIXTURE, ignored_embed_uuids=["dddddddd-1111-1111-1111-111111111111"]).scan()
    ideas = [obj for obj in result.objects if obj.object_type == "idea"]
    titles = [obj.title for obj in ideas]
    assert all(not title.startswith("]") for title in titles)
    assert "这个是 wiki link 解释，不应该抽成 idea" not in titles
    tasks = [obj.title for obj in result.objects if obj.object_type == "task"]
    assert tasks.count("模板任务不要因 embed 复制到 journal") == 1


def test_definition_record_location_matches_canonical_location(tmp_path):
    conn, repo = load_repo(tmp_path)
    mismatches = repo.quality_metrics()["source_location_mismatches"]
    missing = repo.quality_metrics()["missing_definition_records"]
    assert mismatches == 0
    assert missing == 0
    for obj in repo.list_objects(limit=1000):
        definition = repo.definition_record_for_object(int(obj["id"]))
        full = repo.get_object(int(obj["id"]))
        assert definition is not None
        assert definition["file_path"] == full["file_path"]
        assert definition["line_start"] == full["line_start"]


def test_block_source_ids_do_not_cross_file_collide(tmp_path):
    conn, repo = load_repo(tmp_path)
    idea = next(obj for obj in repo.list_objects("idea", limit=200) if obj["title"] == "可以把行程拆成首尔和釜山两段")
    definition = repo.definition_record_for_object(int(idea["id"]))
    assert definition["page_name"] == "项目-韩国旅行"
    assert definition["block_uuid"] == "aaaaaaaa-2222-2222-2222-222222222222"
    assert "((11111111" not in definition["raw_text"]


def test_relation_inference_for_project_pages_task_ideas_and_journal_wikilinks(tmp_path):
    conn, repo = load_repo(tmp_path)
    project = next(obj for obj in repo.list_objects("project", limit=100) if obj["title"] == "项目-韩国旅行")
    relations = repo.relations_for_object(int(project["id"]))
    related_titles = {rel["from_title"] for rel in relations if rel["relation_type"] == "belongs_to"}
    assert "办理签证材料" in related_titles
    assert "尝试安排一天咖啡馆路线" in related_titles
    assert "继续推进 [[项目-韩国旅行]] 的签证材料" in related_titles
    task = next(obj for obj in repo.list_objects("task", limit=200) if obj["title"] == "办理签证材料")
    task_relations = repo.relations_for_object(int(task["id"]))
    assert any(rel["from_title"] == "可以把行程拆成首尔和釜山两段" for rel in task_relations)
    records = repo.records_for_object(int(task["id"]), limit=50)
    assert any(record["role"] == "journal_exposure" for record in records)


def test_agent_views_and_quality_report_are_redacted(tmp_path):
    conn, repo = load_repo(tmp_path)
    service = AgentViewService(conn)
    today = service.today_context(days=3000, limit=20, redact=True)
    project = service.project_context("项目-韩国旅行", days=3000, redact=True)
    inbox = service.inbox_context(days=3000, redact=True)
    quality = service.extraction_quality_report()
    text = service.markdown(today) + service.markdown(project) + service.markdown(inbox)
    assert "travel-secret" not in text
    assert "journal-token-secret" not in text
    assert "sessionid-secret-value" not in text
    assert today["recent_objects"]
    assert project["unfinished_tasks"]
    assert "unlinked_ideas" in inbox
    assert quality["metrics"]["source_location_mismatches"] == 0
