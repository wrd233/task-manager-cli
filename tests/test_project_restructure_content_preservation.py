from task_manager_cli.projects.physical_restructure import metrics, preservation_warnings, restructure_text


def test_restructure_preserves_content_counters_and_ids():
    original = (
        "PARA:: [[PARA/Project]]\n\n"
        "- TODO 项目根 #项目清单\n"
        "  id:: abc-def\n"
        "\t- **[具体事务]**\n"
        "\t\t- TODO 第一件事 [[资料]]\n"
        "\t\t  id:: task-id\n"
        "\t\t- DONE 已完成 https://example.com\n"
        "\t- 普通备注不会丢\n"
    )
    updated, _renamed, _added = restructure_text(original, project_title="项目-保全", classification="active")
    before = metrics(original)
    after = metrics(updated)

    assert preservation_warnings(before, after) == []
    assert "普通备注不会丢" in updated
    assert "id:: abc-def" in updated
    assert "id:: task-id" in updated
    assert after.non_empty_line_count >= before.non_empty_line_count
    assert after.task_count == before.task_count
    assert after.link_count == before.link_count
    assert after.id_property_count == before.id_property_count


def test_archive_pages_are_normalized_without_forcing_project_para():
    original = (
        "PARA:: [[PARA/Archive]]\n"
        "state:: 已完成\n\n"
        "- TODO 历史项目 #项目清单\n"
        "\t- **[资源列表]**:<资源>\n"
        "\t\t- [[历史资料]]\n"
    )
    updated, renamed, added = restructure_text(original, project_title="课程-历史", classification="historical")

    assert "PARA:: [[PARA/Archive]]" in updated
    assert "status:: active" not in updated
    assert renamed == {"资源列表": 1}
    assert "**[资源]**:<资源>" in updated
    assert "历史资料" in updated
    assert "目标" in added
