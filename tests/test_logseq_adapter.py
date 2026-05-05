from pathlib import Path

from task_manager_cli.adapters.logseq.adapter import LogseqAdapter


FIXTURE = Path(__file__).parent / "fixtures" / "logseq_graph"


def test_adapter_extracts_project_task_idea_and_refs():
    result = LogseqAdapter(FIXTURE, ignored_embed_uuids=["63834265-4f84-4c7c-bd14-2b497928dd91"]).scan()
    objects = {(obj.object_type, obj.title): obj for obj in result.objects}
    assert ("project", "项目-Alpha") in objects
    assert ("task", "搭建索引器") in objects
    assert ("idea", "未来接入 Flomo") in objects
    assert any(rel.relation_type == "belongs_to" for rel in result.relations)


def test_structural_embed_does_not_generate_journal_task():
    result = LogseqAdapter(FIXTURE, ignored_embed_uuids=["63834265-4f84-4c7c-bd14-2b497928dd91"]).scan()
    titles = [obj.title for obj in result.objects if obj.object_type == "task"]
    assert "模板里的任务不应因为 embed 生成 journal task" in titles
    assert titles.count("模板里的任务不应因为 embed 生成 journal task") == 1
