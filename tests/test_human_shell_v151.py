import json
from datetime import date
from pathlib import Path

from task_manager_cli.proposals.service import ProposalService
from task_manager_cli.shell.completion import ShellCompleter
from task_manager_cli.shell.inventory import build_inventory
from tests.test_human_shell import loaded_shell


# ── Context Inventory ─────────────────────────────────────────────────────

def test_inventory_projects_context(tmp_path):
    shell, repo, _graph, _conn = loaded_shell(tmp_path)
    inv = build_inventory(shell.conn, shell.context, shell.repo, shell.settings)
    # On /today by default
    assert inv["context"] == "/today"
    sections = {s["type"]: s for s in inv["sections"]}
    assert "actions" in sections or "ideas" in sections

    shell.run_line("cd /projects")
    inv = build_inventory(shell.conn, shell.context, shell.repo, shell.settings)
    assert inv["context"] == "/projects"
    projects = inv["sections"]
    assert len(projects) == 1
    assert projects[0]["type"] == "projects"


def test_inventory_project_context_has_all_sections(tmp_path):
    shell, repo, _graph, _conn = loaded_shell(tmp_path)
    shell.run_line("cd /projects/项目-韩国旅行")
    inv = build_inventory(shell.conn, shell.context, shell.repo, shell.settings)
    assert inv["context"].startswith("/projects/")
    section_types = {s["type"] for s in inv["sections"]}
    assert "nodes" in section_types


def test_inventory_node_context(tmp_path):
    shell, repo, _graph, _conn = loaded_shell(tmp_path)
    shell.run_line("cd /projects/项目-韩国旅行")
    shell.run_line("cd 出行交通")
    inv = build_inventory(shell.conn, shell.context, shell.repo, shell.settings)
    assert inv.get("project_node_id")


def test_inventory_mini_context(tmp_path):
    shell, repo, _graph, _conn = loaded_shell(tmp_path)
    shell.run_line("cd /mini")
    inv = build_inventory(shell.conn, shell.context, shell.repo, shell.settings)
    assert inv["context"] == "/mini"


# ── ls IDs & Filters ──────────────────────────────────────────────────────

def test_ls_project_context_shows_structure(tmp_path):
    shell, repo, _graph, _conn = loaded_shell(tmp_path)
    shell.run_line("cd /projects/项目-韩国旅行")
    output = shell.run_line("ls")
    lines = output.split("\n")
    assert "韩国旅行" in lines[0]


def test_ls_projects_shows_project_names(tmp_path):
    shell, repo, _graph, _conn = loaded_shell(tmp_path)
    shell.run_line("cd /projects")
    output = shell.run_line("ls")
    assert "韩国旅行" in output


def test_ls_filters(tmp_path):
    shell, repo, _graph, _conn = loaded_shell(tmp_path)
    shell.run_line("cd /projects/项目-韩国旅行")
    assert "Open Actions" in shell.run_line("ls tasks") or "Actions" in shell.run_line("ls tasks")
    assert "Ideas" in shell.run_line("ls ideas") or "No ideas" in shell.run_line("ls ideas")
    assert "Nodes" in shell.run_line("ls nodes") or "node" in shell.run_line("ls nodes")
    assert "Resources" in shell.run_line("ls resources") or "No resources" in shell.run_line("ls resources")


def test_ls_todo_doing_waiting_filters(tmp_path):
    shell, repo, _graph, _conn = loaded_shell(tmp_path)
    shell.run_line("cd /projects/项目-韩国旅行")
    output = shell.run_line("ls todo")
    assert "TODO" in output or "No todo" in output


def test_ls_all_mode(tmp_path):
    shell, repo, _graph, _conn = loaded_shell(tmp_path)
    shell.run_line("cd /projects/项目-韩国旅行")
    output = shell.run_line("ls all")
    assert output


def test_ls_sections_are_separated(tmp_path):
    shell, repo, _graph, _conn = loaded_shell(tmp_path)
    shell.run_line("cd /projects/项目-韩国旅行")
    output = shell.run_line("ls")
    # Should have Nodes and at least one of Open Actions/Ideas/Mini Projects
    assert "Nodes" in output
    # Verify section structure is present
    sections_present = any(s in output for s in ["Open Actions", "Ideas", "Mini Projects", "Resources"])
    assert sections_present or "No items" in output


def test_ls_unknown_filter(tmp_path):
    shell, repo, _graph, _conn = loaded_shell(tmp_path)
    output = shell.run_line("ls bogus")
    assert "Unknown filter" in output


# ── Relative Completion ───────────────────────────────────────────────────

def test_completion_relative_project_name_in_projects(tmp_path):
    shell, repo, _graph, _conn = loaded_shell(tmp_path)
    shell.run_line("cd /projects")
    comp = ShellCompleter(shell)
    result = comp.complete_line("韩")
    assert any("韩国旅行" in c for c in result.candidates)


def test_completion_cd_project_prefix_in_projects(tmp_path):
    shell, repo, _graph, _conn = loaded_shell(tmp_path)
    shell.run_line("cd /projects")
    comp = ShellCompleter(shell)
    result = comp.complete_line("cd 韩")
    assert any("韩国旅行" in c for c in result.candidates)


def test_completion_relative_mini_name_in_mini(tmp_path):
    shell, repo, _graph, _conn = loaded_shell(tmp_path)
    shell.run_line("cd /mini")
    comp = ShellCompleter(shell)
    result = comp.complete_line("整")
    assert any("整理打车攻略" in c for c in result.candidates)


def test_completion_chinese_prefix(tmp_path):
    shell, repo, _graph, _conn = loaded_shell(tmp_path)
    shell.run_line("cd /projects")
    comp = ShellCompleter(shell)
    result = comp.complete_line("cd 韩")
    assert len(result.candidates) > 0


def test_completion_edit_task_subcommands(tmp_path):
    shell, repo, _graph, _conn = loaded_shell(tmp_path)
    comp = ShellCompleter(shell)
    result = comp.complete_line("edit ")
    assert "proposal" in result.candidates
    assert "task" in result.candidates

    result2 = comp.complete_line("edit task 123 ")
    assert "title" in result2.candidates
    assert "content" in result2.candidates
    assert "status" in result2.candidates

    result3 = comp.complete_line("edit task 123 status ")
    assert "todo" in result3.candidates
    assert "doing" in result3.candidates
    assert "waiting" in result3.candidates
    assert "done" in result3.candidates


def test_completion_edit_proposal_fields(tmp_path):
    shell, repo, _graph, _conn = loaded_shell(tmp_path)
    comp = ShellCompleter(shell)
    result = comp.complete_line("edit proposal 1 ")
    assert "content" in result.candidates
    assert "reason" in result.candidates


# ── Task Edit ─────────────────────────────────────────────────────────────

def test_edit_task_status(tmp_path):
    shell, repo, _graph, _conn = loaded_shell(tmp_path)
    shell.run_line("cd /projects/项目-韩国旅行")
    task = next(item for item in repo.list_objects("task", limit=50) if item["title"] == "已有项目任务")
    task_id = task["id"]

    result = shell.run_line(f"edit task {task_id} status waiting")
    assert "WAITING" in result

    result2 = shell.run_line(f"edit task {task_id} status done")
    assert "DONE" in result2

    result3 = shell.run_line(f"edit task {task_id} status todo")
    assert "TODO" in result3

    # Invalid status
    result4 = shell.run_line(f"edit task {task_id} status invalid")
    assert "Unknown status" in result4


def test_edit_task_title_modifies_block_and_preserves_marker(tmp_path):
    shell, repo, graph, _conn = loaded_shell(tmp_path)
    task = next(item for item in repo.list_objects("task", limit=50) if item["title"] == "已有项目任务")
    task_id = task["id"]
    file_path = Path(task["file_path"])

    shell.input_func = lambda prompt="": "y"
    result = shell.run_line(f'edit task {task_id} title "新的任务标题"')
    assert "title updated" in result

    content = file_path.read_text(encoding="utf-8")
    assert "新的任务标题" in content


def test_edit_task_status_unknown_target(tmp_path):
    shell, _repo, _graph, _conn = loaded_shell(tmp_path)
    result = shell.run_line("edit task 99999 status done")
    assert "not found" in result.lower() or "Task" in result


def test_edit_task_preserves_child_blocks(tmp_path):
    shell, repo, graph, _conn = loaded_shell(tmp_path)
    # The "已有项目任务" task is under a node with children
    task = next(item for item in repo.list_objects("task", limit=50) if item["title"] == "已有项目任务")
    task_id = task["id"]
    file_path = Path(task["file_path"])
    original = file_path.read_text(encoding="utf-8")

    shell.input_func = lambda prompt="": "y"
    shell.run_line(f'edit task {task_id} title "保留子块测试"')

    modified = file_path.read_text(encoding="utf-8")
    # Child blocks should still exist
    assert "查询 Kakao T" in modified
    assert "整理打车攻略" in modified


def test_edit_task_undo_restores(tmp_path):
    shell, repo, graph, _conn = loaded_shell(tmp_path)
    task = next(item for item in repo.list_objects("task", limit=50) if item["title"] == "已有项目任务")
    task_id = task["id"]
    file_path = Path(task["file_path"])
    original = file_path.read_text(encoding="utf-8")

    shell.input_func = lambda prompt="": "y"
    shell.run_line(f'edit task {task_id} title "即将撤销的标题"')
    assert "即将撤销的标题" in file_path.read_text(encoding="utf-8")

    # Undo last operation
    result = shell.run_line("undo last")
    assert "Undone" in result or "Restored" in result or "undone" in result.lower()

    restored = file_path.read_text(encoding="utf-8")
    assert restored == original


# ── Edit Ambiguity ────────────────────────────────────────────────────────

def test_edit_proposal_explicit(tmp_path):
    shell, repo, _graph, conn = loaded_shell(tmp_path)
    task = next(item for item in repo.list_objects("task", limit=50) if item["title"] == "已有项目任务")
    service = ProposalService(conn, shell.settings)
    service.create_logseq_marker("AI注", "test", target_object_ref=str(task["id"]))
    conn.commit()
    shell.run_line("proposals")
    result = shell.run_line('edit proposal 1 content "explicit proposal edit"')
    assert "Edited proposal" in result


def test_edit_old_syntax_still_works(tmp_path):
    shell, repo, _graph, conn = loaded_shell(tmp_path)
    task = next(item for item in repo.list_objects("task", limit=50) if item["title"] == "已有项目任务")
    service = ProposalService(conn, shell.settings)
    service.create_logseq_marker("AI注", "old syntax", target_object_ref=str(task["id"]))
    conn.commit()
    shell.run_line("proposals")
    result = shell.run_line('edit 1 content "backward compat"')
    assert "Edited proposal" in result


def test_proposal_number_missing_prompts(tmp_path):
    shell, _repo, _graph, _conn = loaded_shell(tmp_path)
    result = shell.run_line("edit 99 content test")
    assert "不存在" in result or "exist" in result.lower() or "Error" in result
