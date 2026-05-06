import json
from pathlib import Path

from task_manager_cli.adapters.logseq.adapter import LogseqAdapter
from task_manager_cli.adapters.logseq.parser import parse_logseq_file
from task_manager_cli.config.settings import Settings
from task_manager_cli.ingest.merger import Merger
from task_manager_cli.projects.tree import ProjectTreeService
from task_manager_cli.storage.database import connect, init_db
from task_manager_cli.storage.repositories import Repository


def test_tab_indentation_builds_parent_children(tmp_path):
    page = tmp_path / "Tab.md"
    page.write_text("- 根节点\n\t- 子节点\n\t\t- 孙节点\n    \t- 混合缩进\n", encoding="utf-8")

    parsed = parse_logseq_file(page)
    root = parsed.blocks[0]
    assert root.children[0].text == "子节点"
    assert root.children[0].children[0].text == "孙节点"
    assert parsed.blocks[-1].parent is root.children[0]


def test_project_tree_tabs_render_nested_markdown_and_json(tmp_path):
    graph = tmp_path / "graph"
    pages = graph / "pages"
    pages.mkdir(parents=True)
    (pages / "项目-Tab.md").write_text(
        "PARA:: [[PARA/Project]]\n\n"
        "- **[目标]** 根目标\n"
        "\t- **[工作流]** 子流程\n"
        "\t\t- TODO 孙任务\n",
        encoding="utf-8",
    )
    conn = connect(tmp_path / "tm.sqlite3")
    init_db(conn)
    repo = Repository(conn)
    Merger(repo).ingest(LogseqAdapter(graph).scan())
    conn.commit()
    settings = Settings(app_dir=tmp_path / "app", database_path=tmp_path / "tm.sqlite3", logseq_graph_path=graph)

    service = ProjectTreeService(conn, settings)
    tree = service.build("项目-Tab")
    rendered = service.render_markdown(tree)
    data = json.dumps(tree, ensure_ascii=False)

    assert "  [工作流] 子流程" in rendered
    assert "    [行动] TODO 孙任务" in rendered
    assert '"children": [' in data
    assert tree["summary"]["node_count"] == 3
