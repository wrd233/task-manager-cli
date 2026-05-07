from tests.test_human_shell import loaded_shell


def test_sync_status_after_write_and_undo(tmp_path):
    shell, _repo, _graph, _conn = loaded_shell(tmp_path)
    shell.run_line("layout on")
    output = shell.run_line('todo "状态栏测试"')
    assert "File: synced" in output
    assert "Index: fresh" in output
    assert "Rollback: op #1" in output
    output = shell.run_line("undo")
    assert "Undone op" in output


def test_sync_status_buffer_dirty_from_edit_buffer(tmp_path):
    shell, repo, _graph, _conn = loaded_shell(tmp_path)
    task = next(item for item in repo.list_objects("task", limit=50) if item["title"] == "已有项目任务")
    buffer = shell.inline_editor.create_buffer([str(task["id"]), "line"])
    buffer.insert_text(" x")
    shell.layout_state.sync_status.mark_buffer(buffer.dirty)
    assert "Buffer: dirty" in shell.layout_state.sync_status.format_line()
    shell.layout_state.sync_status.mark_conflict("changed")
    assert "conflict" in shell.layout_state.sync_status.format_line()


def test_sync_status_write_failed_is_visible(tmp_path):
    shell, _repo, _graph, _conn = loaded_shell(tmp_path)
    shell.layout_state.sync_status.mark_write_failed("boom")
    assert "write failed" in shell.layout_state.sync_status.format_line()
    assert shell.layout_state.sync_status.index_status == "unchanged"
