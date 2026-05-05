from pathlib import Path

from task_manager_cli.adapters.logseq.adapter import LogseqAdapter
from task_manager_cli.adapters.logseq.extractors import parse_idea, semantic_marker, semantic_tags


FIXTURE = Path(__file__).parent / "fixtures" / "logseq_graph"


def test_semantic_marker_recognition_is_explicit():
    assert semantic_marker("- **[想法]** 做一个设计对象") == "想法"
    assert semantic_marker("- **[待澄清]** 目标还不清楚") == "待澄清"
    assert semantic_marker("- **[注]** 用户自己的判断") == "注"
    assert semantic_marker("- **[AI注]** 模型建议") == "AI注"
    assert semantic_marker("- **[成果]** 已沉淀") == "成果"
    assert semantic_marker("- **[无成果]** 无可复用输出") == "无成果"
    assert semantic_marker("- **[小任务]** 整理多步骤事务") == "小任务"
    assert semantic_marker("- **[目标]** 完成项目方向") == "目标"
    assert semantic_marker("- **[工作流]** 出行交通") == "工作流"
    assert semantic_marker("- **[资源]** 官网链接") == "资源"
    assert "inbox" in semantic_tags("- TODO 做事 #inbox #waiting")
    assert "waiting" in semantic_tags("- TODO 做事 #inbox #waiting")
    assert "reference" in semantic_tags("- 资料 #reference")


def test_wikilink_or_plain_idea_text_is_not_an_idea_marker():
    assert parse_idea("- [[想法]] 页面链接") is None
    assert parse_idea("- 这是一个普通想法") is None


def test_reference_tag_does_not_enter_action_flow(tmp_path):
    graph = tmp_path / "graph"
    pages = graph / "pages"
    pages.mkdir(parents=True)
    (pages / "Reference.md").write_text(
        "- TODO 阅读资料 #reference\n"
        "- **[想法]** 资料里的产品点 #reference\n"
        "- **[注]** 用户注\n"
        "- **[AI注]** AI 注\n"
        "- **[成果]** 一条成果\n"
        "- **[无成果]** 暂无成果\n",
        encoding="utf-8",
    )
    result = LogseqAdapter(graph).scan()
    assert not [obj for obj in result.objects if obj.object_type in {"task", "idea"}]
    metadata = [rec.metadata for rec in result.records if rec.record_type == "block"]
    assert any(item["semantic_marker"] == "注" for item in metadata)
    assert any(item["semantic_marker"] == "AI注" for item in metadata)
    assert any(item["semantic_marker"] == "成果" for item in metadata)
