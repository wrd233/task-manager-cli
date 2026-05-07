from task_manager_cli.adapters.logseq.adapter import LogseqAdapter
from task_manager_cli.config.settings import Settings
from task_manager_cli.ingest.merger import Merger
from task_manager_cli.shell.service import HumanShellService
from task_manager_cli.storage.database import connect, init_db
from task_manager_cli.storage.repositories import Repository


def semantic_shell(tmp_path):
    graph = tmp_path / "graph"
    pages = graph / "pages"
    pages.mkdir(parents=True)
    (pages / "项目-节点展示.md").write_text(
        "PARA:: [[PARA/Project]]\n\n"
        "- **[目标]** 目标一\n"
        "    - **[里程碑]** 重复标题\n"
        "        id:: aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa\n"
        "        - **[工作流]** 重复标题\n"
        "            id:: bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb\n"
        "            - TODO 节点内 TODO\n"
        "            - 普通备注保留\n"
        "            - **[资源]** 资料链接\n"
        "            - **[成果]** 交付物\n"
        "            - **[想法]** 一个想法\n"
        "    - **[项目收件箱]** 暂存\n"
        "        - 普通 inbox 条目\n",
        encoding="utf-8",
    )
    conn = connect(tmp_path / "tm.sqlite3")
    init_db(conn)
    repo = Repository(conn)
    Merger(repo).ingest(LogseqAdapter(graph).scan())
    settings = Settings(app_dir=tmp_path / "app", database_path=tmp_path / "tm.sqlite3", logseq_graph_path=graph)
    conn.commit()
    return HumanShellService(conn, settings), repo


def test_milestone_workflow_resource_result_idea_and_inbox_nodes_show(tmp_path):
    shell, _repo = semantic_shell(tmp_path)
    shell.run_line("cd /projects/项目-节点展示")

    milestone = shell.run_line("show block:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    assert "Project Node block:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" in milestone
    assert "类型：里程碑" in milestone
    assert "上级上下文：" in milestone
    assert "**[里程碑]** 重复标题" in milestone

    workflow = shell.run_line("show block:bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
    assert "类型：工作流" in workflow
    assert "Project: 项目-节点展示" in workflow
    assert "TODO 节点内 TODO" in workflow
    assert "普通备注保留" in workflow
    assert "**[资源]** 资料链接" in workflow
    assert "**[成果]** 交付物" in workflow
    assert "**[想法]** 一个想法" in workflow
    assert "PARA::" not in workflow

    assert "类型：资源" in shell.run_line("show 资料链接")
    assert "类型：成果" in shell.run_line("show 交付物")
    assert "类型：想法" in shell.run_line("show 一个想法")
    assert "类型：项目收件箱" in shell.run_line("show 暂存")


def test_repeated_title_can_cd_by_stable_node_id_and_object_show_still_works(tmp_path):
    shell, repo = semantic_shell(tmp_path)
    shell.run_line("cd /projects/项目-节点展示")

    assert shell.run_line("cd block:bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb").endswith("/工作流/重复标题")
    output = shell.run_line("show")
    assert "类型：工作流" in output
    assert "**[工作流]** 重复标题" in output
    assert "**[里程碑]** 重复标题" not in output.split("当前内容：", 1)[1]

    task = next(item for item in repo.list_objects("task", limit=20) if item["title"] == "节点内 TODO")
    obj_output = shell.run_line(f"show {task['id']}")
    assert f"#{task['id']} task" in obj_output
    assert "TODO 节点内 TODO" in obj_output

    tree = shell.run_line("tree")
    assert "普通备注保留" not in tree
