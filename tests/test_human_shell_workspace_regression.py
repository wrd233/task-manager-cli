from tests.test_human_shell import loaded_shell


def test_plain_repl_still_returns_plain_output(tmp_path):
    shell, _repo, _graph, _conn = loaded_shell(tmp_path)
    assert shell.run_line("pwd") == "/today"
    output = shell.run_line("ls")
    assert "Context" not in output
    assert "Main View:" not in output


def test_completion_knows_workspace_commands(tmp_path):
    shell, _repo, _graph, _conn = loaded_shell(tmp_path)
    result = shell.completer.complete_line("layout ")
    assert "on" in result.candidates
    result = shell.completer.complete_line("view ")
    assert "dashboard" in result.candidates
    result = shell.completer.complete_line("insert ")
    assert "subtree" in result.candidates


def test_layout_keeps_current_view_after_direct_action(tmp_path):
    shell, _repo, _graph, _conn = loaded_shell(tmp_path)
    shell.run_line("layout on")
    shell.run_line("cd /projects/项目-韩国旅行")
    shell.run_line("tree")
    output = shell.run_line('todo "刷新但不切走"')
    assert "Main View: tree" in output
    assert "Last Message" in output
