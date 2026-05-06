from task_manager_cli.proposals.service import ProposalService
from task_manager_cli.shell.completion import ShellCompleter
from tests.test_human_shell import loaded_shell


def test_target_selection_fuzzy_single_multi_cancel_and_context_priority(tmp_path):
    shell, repo, _graph, _conn = loaded_shell(tmp_path)
    assert shell.resolve_target("已有项目任务", allow_types={"task"})["object"]["title"] == "已有项目任务"
    shell.run_line('todo "打车候选 A"')
    shell.run_line('todo "打车候选 B"')
    shell.input_func = lambda prompt="": "2"
    chosen = shell.resolve_target("打车候选", allow_types={"task"})
    assert chosen["object"]["title"] in {"打车候选 A", "打车候选 B"}
    shell.input_func = lambda prompt="": "q"
    assert shell.resolve_target("打车候选", allow_types={"task"}) is None
    assert shell.resolve_target("不存在", allow_types={"task"}) is None


def test_operation_history_commands_and_undo_by_number(tmp_path):
    shell, _repo, graph, _conn = loaded_shell(tmp_path)
    page = graph / "journals" / __import__("datetime").date.today().strftime("%Y_%m_%d.md")
    shell.run_line('todo "history one"')
    shell.run_line('todo "history two"')
    text = shell.run_line("history --detail")
    assert "[1]" in text and "[2]" in text
    assert "history one" in text
    assert "Undone op #1" in shell.run_line("undo 1")
    assert "history one" not in page.read_text(encoding="utf-8")
    assert "already undone" in shell.run_line("undo 1")
    assert "todo" in shell.run_line("commands")
    shell.run_line("provider api_key sk-secret")
    assert "[redacted sensitive command]" in shell.run_line("commands")
    assert "cleared" in shell.run_line("clear-history")
    assert "No command history" in shell.run_line("commands")


def test_writeback_preview_where_and_confirm(tmp_path):
    shell, _repo, graph, _conn = loaded_shell(tmp_path)
    today = graph / "journals" / __import__("datetime").date.today().strftime("%Y_%m_%d.md")
    before = today.read_text(encoding="utf-8")
    where = shell.run_line('where todo "preview task"')
    assert "将写入" in where and "preview task" in where
    assert today.read_text(encoding="utf-8") == before
    assert "将写入" in shell.run_line('todo "preview only" --preview')
    assert "preview only" not in today.read_text(encoding="utf-8")
    shell.run_line("preview on")
    shell.input_func = lambda prompt="": "n"
    assert "Cancelled" in shell.run_line('todo "cancelled preview"')
    assert "cancelled preview" not in today.read_text(encoding="utf-8")
    shell.input_func = lambda prompt="": "y"
    assert "written" in shell.run_line('todo "confirmed preview"')
    assert "confirmed preview" in today.read_text(encoding="utf-8")


def test_cd_candidate_selection_and_proposal_edit_supersede(tmp_path):
    shell, repo, _graph, conn = loaded_shell(tmp_path)
    shell.input_func = lambda prompt="": "1"
    assert shell.run_line("cd /projects/韩国").startswith("/projects/")
    assert shell.run_line("cd 出行").endswith("出行交通")
    task = next(item for item in repo.list_objects("task", limit=50) if item["title"] == "已有项目任务")
    service = ProposalService(conn, shell.settings)
    first = service.create_logseq_marker("AI注", "old", target_object_ref=str(task["id"]))
    second = service.create_logseq_marker("AI注", "newer", target_object_ref=str(task["id"]))
    conn.commit()
    shell.run_line("proposals")
    assert "Edited proposal" in shell.run_line('edit 1 content "edited content"')
    assert service.get(first)["payload"]["content"] == "edited content"
    assert "Edited proposal" in shell.run_line("edit 1 risk low")
    service.accept(first)
    service.preview(first)
    service.apply(first, confirmed=True)
    conn.commit()
    assert "Error" in shell.run_line('edit 1 content "nope"')
    assert "Superseded" in shell.run_line("supersede 2 1")


def test_clarify_resume_status_eval_quality_shortcuts(tmp_path):
    shell, _repo, _graph, _conn = loaded_shell(tmp_path)
    shell.run_line("provider off")
    answers = iter(["有", "quit"])
    shell.input_func = lambda prompt="": next(answers)
    paused = shell.run_line("clarify")
    assert "paused" in paused
    assert "review id" in shell.run_line("clarify status")
    answers = iter(["行动", "是", "否", "否", "否", "记录", "具体事务", "否"] * 3)
    shell.input_func = lambda prompt="": next(answers)
    assert "Clarify completed" in shell.run_line("clarify resume")
    assert "Clarify review" in shell.run_line("clarify eval")
    assert "Project Tree Quality" in shell.run_line("quality project-tree")
    assert "Mini Project Quality" in shell.run_line("quality mini")
    assert "Membership Quality" in shell.run_line("quality membership")
    assert "Shell Quality Summary" in shell.run_line("quality all")


def test_completion_pure_logic(tmp_path):
    shell, repo, _graph, conn = loaded_shell(tmp_path)
    comp = ShellCompleter(shell)
    assert "cd" in comp.complete_line("c").candidates
    assert "/projects" in comp.complete_line("cd /p").candidates
    assert "/projects/项目-韩国旅行" in comp.complete_line("cd /projects/项目").candidates
    shell.run_line("cd /projects/项目-韩国旅行")
    assert any("出行交通" in item for item in comp.complete_line("cd 出").candidates)
    assert "mock" in comp.complete_line("provider m").candidates
    assert "membership" in comp.complete_line("quality m").candidates
    assert "on" in comp.complete_line("preview o").candidates
    task = next(item for item in repo.list_objects("task", limit=50) if item["title"] == "已有项目任务")
    proposal_id = ProposalService(conn, shell.settings).create_logseq_marker("AI注", "completion", target_object_ref=str(task["id"]))
    conn.commit()
    shell.run_line("proposals")
    assert "1" in comp.complete_line("accept ").candidates
    assert comp.complete_line("provider zz").candidates == []
