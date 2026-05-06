from tests.test_human_shell import loaded_shell


def test_clarify_quick_asks_one_question_before_next_item(tmp_path):
    shell, _repo, _graph, _conn = loaded_shell(tmp_path)
    shell.run_line("provider off")
    answers = iter(["行动", "quit"])
    prompts = []

    def input_func(prompt=""):
        prompts.append(prompt)
        return next(answers)

    shell.input_func = input_func
    result = shell.run_line("clarify quick")
    assert "Clarify paused" in result or "Clarify completed" in result
    assert sum("问题" in prompt for prompt in prompts) <= 2


def test_clarify_ai_uses_provider_questions_without_proposals(tmp_path):
    shell, _repo, _graph, conn = loaded_shell(tmp_path)
    shell.run_line("provider mock")
    answers = iter(["下一步", "否", "quit"])
    shell.input_func = lambda prompt="": next(answers)
    result = shell.run_line("clarify ai")
    proposal_count = conn.execute("SELECT COUNT(*) AS c FROM proposals").fetchone()["c"]
    assert "Clarify paused" in result or "Clarify completed" in result
    assert proposal_count == 0
