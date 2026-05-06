from tests.test_human_shell import loaded_shell


def test_cd_object_id_and_targetless_actions(tmp_path):
    shell, repo, graph, _conn = loaded_shell(tmp_path)
    task = next(item for item in repo.list_objects("task", limit=50) if item["title"] == "已有项目任务")

    assert shell.run_line(f"cd #{task['id']}").endswith(f"/task/{task['id']}")
    assert f"#{task['id']} task" in shell.run_line("show")
    assert "note appended" in shell.run_line('note "对象上下文备注"')
    assert "result appended" in shell.run_line('result "对象上下文成果"')
    assert "DONE" in shell.run_line("done")
    shell.input_func = lambda prompt="": "y"
    assert "title updated" in shell.run_line('edit title "对象上下文标题"')
    text = (graph / "pages" / "项目-韩国旅行.md").read_text(encoding="utf-8")
    assert "**[注]** 对象上下文备注" in text
    assert "**[成果]** 对象上下文成果" in text
    assert repo.get_object(task["id"])["title"] == "对象上下文标题"


def test_cd_mini_id_and_todo_writes_under_mini(tmp_path):
    shell, repo, graph, _conn = loaded_shell(tmp_path)
    mini = next(item for item in repo.list_objects("mini_project", limit=50) if item["title"] == "整理打车攻略")

    assert shell.run_line(f"cd mini {mini['id']}").endswith(f"/mini/{mini['id']}")
    assert "written" in shell.run_line('todo "mini 下的对象上下文任务"')
    assert "\t- TODO mini 下的对象上下文任务" in (graph / "pages" / "项目-韩国旅行.md").read_text(encoding="utf-8") or "TODO mini 下的对象上下文任务" in (graph / "pages" / "项目-韩国旅行.md").read_text(encoding="utf-8")
    assert shell.run_line("cd ..") in {"/mini", "/"}
