from tests.test_human_shell import loaded_shell


def test_default_preview_is_human_old_new_not_raw_diff(tmp_path):
    shell, repo, _graph, _conn = loaded_shell(tmp_path)
    task = next(item for item in repo.list_objects("task", limit=50) if item["title"] == "已有项目任务")
    preview = shell._location_preview(
        "edit task title",
        shell.writer.preview_modify_block_text(
            task["file_path"],
            line_start=task["line_start"],
            new_text="你好",
            preserve_task_marker=True,
        ),
        f"object:{task['id']}",
        "你好",
    )
    assert "old:" in preview
    assert "new:" in preview
    assert "--- " not in preview
    assert "+++ " not in preview


def test_detail_preview_shows_raw_diff(tmp_path):
    shell, repo, _graph, _conn = loaded_shell(tmp_path)
    shell.run_line("detail on")
    task = next(item for item in repo.list_objects("task", limit=50) if item["title"] == "已有项目任务")
    preview = shell._location_preview(
        "edit task title",
        shell.writer.preview_modify_block_text(
            task["file_path"],
            line_start=task["line_start"],
            new_text="你好",
            preserve_task_marker=True,
        ),
        f"object:{task['id']}",
        "你好",
    )
    assert "diff:" in preview
    assert "--- " in preview
