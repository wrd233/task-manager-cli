import os

from tests.test_human_shell import loaded_shell


def test_layout_on_off_and_panes(tmp_path):
    shell, _repo, _graph, _conn = loaded_shell(tmp_path)
    output = shell.run_line("layout on")
    assert "Context" in output
    assert "Main View: today" in output
    assert "Actionable List:" in output
    assert "Last Message" in output
    assert "File: synced" in output
    assert "ta:/today>" in output
    assert "layout: off" == shell.run_line("layout off")


def test_layout_density_modes(tmp_path):
    shell, _repo, _graph, _conn = loaded_shell(tmp_path)
    assert "Density: compact" in shell.run_line("layout compact")
    compact = shell.run_line("layout refresh")
    assert "Actionable List:" not in compact
    assert "Density: standard" in shell.run_line("layout standard")
    assert "Density: full" in shell.run_line("layout full")


def test_layout_no_color_is_plain(monkeypatch, tmp_path):
    monkeypatch.setenv("NO_COLOR", "1")
    shell, _repo, _graph, _conn = loaded_shell(tmp_path)
    output = shell.run_line("layout on")
    assert "\x1b[" not in output
    assert "=" * 20 in output


def test_layout_auto_view_after_commands(tmp_path):
    shell, _repo, _graph, _conn = loaded_shell(tmp_path)
    shell.run_line("layout on")
    assert "Main View: tree" in shell.run_line("cd /projects/项目-韩国旅行")
    assert "Main View: tasks" in shell.run_line("ls tasks")
    assert "Main View: search" in shell.run_line("find Kakao")
    assert "Main View: health" in shell.run_line("quality project")
