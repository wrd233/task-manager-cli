from task_manager_cli.adapters.logseq.extractors import semantic_marker
from task_manager_cli.adapters.logseq.adapter import LogseqAdapter
from task_manager_cli.projects.physical_restructure import metrics, restructure_text, section_names


def test_physical_restructure_standardizes_legacy_project_sections():
    original = (
        "PARA:: [[PARA/Project]]\n\n"
        "- TODO [#A] 项目-旧模板 #项目清单\n"
        "  type:: [[项目]]\n"
        "\t- **[具体目标]**:<待完成的目标>\n"
        "\t- **[具体事务]**:<一些明确要做的内容>\n"
        "\t\t- TODO 保留任务\n"
        "\t- **[资源列表]**:<资源>\n"
        "\t\t- https://example.com\n"
        "\t- **[头脑风暴]**:<想法>\n"
        "\t\t- **[想法]** 保留想法\n"
    )
    updated, renamed, added = restructure_text(original, project_title="项目-旧模板", classification="active")

    assert renamed == {"具体目标": 1, "资源列表": 1, "头脑风暴": 1}
    assert "**[目标]**" in updated
    assert "**[资源]**" in updated
    assert "**[想法]**:<想法>" in updated
    assert "**[项目收件箱]**" in updated
    assert "**[成果]**" in updated
    assert "TODO 保留任务" in updated
    assert "https://example.com" in updated
    assert set(added) == {"项目收件箱", "小任务", "成果", "反思"}
    assert metrics(updated).task_count == metrics(original).task_count
    assert metrics(updated).link_count == metrics(original).link_count


def test_semantic_marker_aliases_are_canonicalized_for_tree_parser():
    assert semantic_marker("- **[具体目标]**:<待完成的目标>") == "目标"
    assert semantic_marker("- **[资源列表]**:<资源>") == "资源"
    assert semantic_marker("- **[头脑风暴]**:<想法>") == "想法"
    assert semantic_marker("- **[复盘]** 下次减少上下文切换") == "反思"
    assert semantic_marker("- **[交付物]** 报告") == "成果"


def test_physical_restructure_adds_project_properties_for_malformed_prefix_page():
    original = "- TODO 做一件事\n"
    updated, _renamed, added = restructure_text(original, project_title="任务-临时项目", classification="malformed")

    assert updated.startswith("PARA:: [[PARA/Project]]\nstatus:: active\n")
    assert "**[项目收件箱]**" in updated
    assert "TODO 做一件事" in updated
    assert set(added) == set(["目标", "项目收件箱", "具体事务", "小任务", "资源", "成果", "想法", "反思"])
    assert set(section_names(updated)) >= set(["目标", "项目收件箱", "具体事务", "资源", "成果", "想法", "反思"])


def test_empty_mini_project_section_is_not_extracted_as_object(tmp_path):
    graph = tmp_path / "graph"
    pages = graph / "pages"
    pages.mkdir(parents=True)
    (graph / "journals").mkdir()
    (pages / "项目-空小任务.md").write_text(
        "PARA:: [[PARA/Project]]\n\n"
        "- Project\n"
        "    - **[小任务]**\n"
        "    - **[小任务]** 有标题的小任务\n",
        encoding="utf-8",
    )

    result = LogseqAdapter(graph).scan()
    minis = [obj for obj in result.objects if obj.object_type == "mini_project"]
    assert [obj.title for obj in minis] == ["有标题的小任务"]


def test_placeholder_section_headers_are_not_extracted_as_idea_or_resource(tmp_path):
    graph = tmp_path / "graph"
    pages = graph / "pages"
    pages.mkdir(parents=True)
    (graph / "journals").mkdir()
    (pages / "项目-占位说明.md").write_text(
        "PARA:: [[PARA/Project]]\n\n"
        "- Project\n"
        "    - **[想法]**:<事务执行过程中你的想法>\n"
        "    - **[资源]**:<事务处理过程中你可以用到的资源>\n"
        "    - **[想法]** 真实想法\n"
        "    - **[资源]** 真实资源 https://example.com\n",
        encoding="utf-8",
    )

    result = LogseqAdapter(graph).scan()
    assert [obj.title for obj in result.objects if obj.object_type == "idea"] == ["真实想法"]
    assert [obj.title for obj in result.objects if obj.object_type == "reference"] == ["真实资源 https://example.com"]
