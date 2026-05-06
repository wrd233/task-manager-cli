from task_manager_cli.adapters.logseq.extractors import parse_task


def test_todo_list_headings_are_not_tasks():
    assert parse_task("- TODO-list") is None
    assert parse_task("- TODO list") is None
    assert parse_task("- TODO-list:") is None
    assert parse_task("- 这是普通文本 TODO 不是任务") is None


def test_real_logseq_task_marker_still_extracts():
    assert parse_task("- TODO 真任务") == ("TODO", "真任务")
    assert parse_task("- DONE 已完成") == ("DONE", "已完成")
