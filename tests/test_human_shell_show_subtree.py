from tests.test_human_shell import loaded_shell


def test_mini_context_show_renders_full_raw_subtree(tmp_path):
    shell, repo, _graph, _conn = loaded_shell(tmp_path)
    mini = next(item for item in repo.list_objects("mini_project", limit=50) if item["title"] == "整理打车攻略")

    assert shell.run_line(f"cd /mini/{mini['title']}").startswith("/mini/")
    output = shell.run_line("show")

    assert f"Mini Project #{mini['id']}" in output
    assert "项目：项目-韩国旅行" in output
    assert "当前内容：" in output
    assert "**[小任务]** 整理打车攻略" in output
    assert "TODO 查询 Kakao T" in output
    assert "普通 mini 备注" in output
    assert "**[资源]** Kakao T 官网" in output

    tree_output = shell.run_line("tree")
    assert "[资源] Kakao T 官网" in tree_output
    assert "普通 mini 备注" not in tree_output


def test_project_node_context_show_renders_full_raw_subtree_and_brief_context(tmp_path):
    shell, _repo, _graph, _conn = loaded_shell(tmp_path)

    shell.run_line("cd /projects/项目-韩国旅行")
    assert shell.run_line("cd 整理打车攻略").endswith("/小任务/整理打车攻略")
    output = shell.run_line("show")

    assert "Project Node" in output
    assert "项目：项目-韩国旅行" in output
    assert "上下文：" in output
    assert "当前内容：" in output
    assert "**[小任务]** 整理打车攻略" in output
    assert "TODO 查询 Kakao T" in output
    assert "普通 mini 备注" in output
    assert output.count("Project: 项目-韩国旅行") == 1

    node_id = shell.context.project_node_id
    by_id = shell.run_line(f"show {node_id}")
    assert "Project Node" in by_id
    assert "普通 mini 备注" in by_id


def test_project_node_tree_shows_semantic_subtree_or_show_hint(tmp_path):
    shell, _repo, _graph, _conn = loaded_shell(tmp_path)

    shell.run_line("cd /projects/项目-韩国旅行")
    shell.run_line("cd 整理打车攻略")
    mini_tree = shell.run_line("tree")
    assert "[资源] Kakao T 官网" in mini_tree
    assert "普通 mini 备注" not in mini_tree

    shell.run_line("cd /projects/项目-韩国旅行")
    shell.run_line("cd /projects/项目-韩国旅行/具体事务/[具体事务]")
    empty_tree = shell.run_line("tree")
    assert "可使用 show 查看完整 Logseq 子树" in empty_tree
