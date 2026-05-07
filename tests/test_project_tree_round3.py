import json
import os
import subprocess
import sys
from pathlib import Path

from task_manager_cli.adapters.logseq.adapter import LogseqAdapter
from task_manager_cli.clarify.service import ClarifyService
from task_manager_cli.config.settings import Settings
from task_manager_cli.ingest.merger import Merger
from task_manager_cli.projects.membership import ProjectMembershipService
from task_manager_cli.projects.tree import ProjectTreeService
from task_manager_cli.proposals.service import ProposalService
from task_manager_cli.storage.database import connect, init_db
from task_manager_cli.storage.repositories import Repository


ROOT = Path(__file__).resolve().parents[1]


def write_round3_graph(tmp_path):
    graph = tmp_path / "graph"
    pages = graph / "pages"
    journals = graph / "journals"
    pages.mkdir(parents=True)
    journals.mkdir(parents=True)
    (pages / "项目-旅行.md").write_text(
        "PARA:: [[PARA/Project]]\n\n"
        "- **[目标]** 完成旅行准备，降低不确定性\n"
        "    - **[工作流]** 出行交通\n"
        "        - **[小任务]** 整理打车攻略\n"
        "            - TODO 查询 Kakao T 使用方式\n"
        "            - 普通备注：确认手机号要求\n"
        "            - **[资源]** Kakao T 官网 https://example.com\n"
        "            - **[想法]** 可以做风险评分\n"
        "            - **[注]** 用户判断\n"
        "            - **[AI注]** 等待审核\n"
        "    - **[成果]** 已整理清单\n",
        encoding="utf-8",
    )
    (journals / "2026_05_05.md").write_text(
        "- **[小任务]** 临时整理行李清单\n"
        "    - TODO 买转换插头\n"
        "- TODO [[项目-旅行]] 询问机场接送\n"
        "- **[资源]** [[项目-旅行]] 机场交通链接 #reference\n",
        encoding="utf-8",
    )
    conn = connect(tmp_path / "tm.sqlite3")
    init_db(conn)
    repo = Repository(conn)
    Merger(repo).ingest(LogseqAdapter(graph).scan())
    conn.commit()
    settings = Settings(
        app_dir=tmp_path / "app",
        database_path=tmp_path / "tm.sqlite3",
        logseq_graph_path=graph,
        write_mode="guarded",
        write_backup_dir=tmp_path / "backups",
    )
    return graph, conn, repo, settings


def test_mini_project_marker_enters_system_without_becoming_project(tmp_path):
    _graph, _conn, repo, _settings = write_round3_graph(tmp_path)
    mini_projects = repo.list_objects("mini_project", limit=20)
    titles = {item["title"] for item in mini_projects}
    assert "整理打车攻略" in titles
    assert "临时整理行李清单" in titles
    assert not [item for item in mini_projects if item["object_type"] == "project"]
    tasks = {item["title"] for item in repo.list_objects("task", limit=20)}
    assert "查询 Kakao T 使用方式" in tasks
    assert "Kakao T 官网 https://example.com" not in tasks


def test_project_tree_read_model_markdown_json_and_agent_context(tmp_path):
    _graph, conn, _repo, settings = write_round3_graph(tmp_path)
    service = ProjectTreeService(conn, settings)
    tree = service.build("项目-旅行", detail=False)
    assert tree["summary"]["has_structured_markers"] is True
    flat = json.dumps(tree, ensure_ascii=False)
    assert '"node_type": "objective"' in flat
    assert '"node_type": "workflow"' in flat
    assert '"node_type": "mini_project"' in flat
    assert '"node_type": "resource"' in flat
    assert '"node_type": "idea"' in flat
    assert '"node_type": "result"' in flat
    assert "raw_text" not in flat
    assert '"node_type": "unknown"' not in flat
    assert '"node_type": "action_item"' not in flat
    assert "查询 Kakao T 使用方式" not in flat
    assert "普通备注：确认手机号要求" not in flat
    markdown = service.render_markdown(tree)
    assert "# 项目树：项目-旅行" in markdown
    assert "[小任务] 整理打车攻略" in markdown
    assert "未识别" not in markdown
    assert "TODO 查询 Kakao T" not in markdown
    agent = service.agent_view("项目-旅行", detail=True)
    assert agent["agent_context"]["omitted_by_default"]
    assert "raw_text" in json.dumps(agent, ensure_ascii=False)


def test_raw_subtree_keeps_unrecognized_blocks_and_todo(tmp_path):
    _graph, conn, _repo, settings = write_round3_graph(tmp_path)
    service = ProjectTreeService(conn, settings)
    tree = service.build("项目-旅行", detail=True)
    flat = []
    service._flatten(tree["tree"], flat)
    mini = next(node for node in flat if node["node_type"] == "mini_project")

    raw = service.raw_subtree_for_node("项目-旅行", mini["id"], detail=True)

    assert raw is not None
    assert "**[小任务]** 整理打车攻略" in raw
    assert "TODO 查询 Kakao T 使用方式" in raw
    assert "普通备注：确认手机号要求" in raw
    assert "(line:" in raw


def test_tree_rendering_spacing_detail_and_color(tmp_path):
    graph = tmp_path / "graph"
    pages = graph / "pages"
    pages.mkdir(parents=True)
    (pages / "项目-渲染.md").write_text(
        "PARA:: [[PARA/Project]]\n\n"
        "- **[目标]** A\n"
        "- [资源] B\n"
        "- 普通块不进 tree\n",
        encoding="utf-8",
    )
    conn = connect(tmp_path / "tm.sqlite3")
    init_db(conn)
    repo = Repository(conn)
    Merger(repo).ingest(LogseqAdapter(graph).scan())
    conn.commit()
    settings = Settings(app_dir=tmp_path / "app", database_path=tmp_path / "tm.sqlite3", logseq_graph_path=graph)
    service = ProjectTreeService(conn, settings)
    tree = service.build("项目-渲染", detail=True)

    plain = service.render_markdown(tree, detail=False, color=False)
    detail = service.render_markdown(tree, detail=True, color=False)
    colored = service.render_markdown(tree, color=True)

    assert "[目标] A\n\n[资源] B" in plain
    assert "普通块不进 tree" not in plain
    assert "id:" in detail and "type:" in detail and "line:" in detail
    assert "\033[1;33m[目标]\033[0m" in colored


def test_no_color_environment_disables_ansi(tmp_path, monkeypatch):
    _graph, conn, _repo, settings = write_round3_graph(tmp_path)
    service = ProjectTreeService(conn, settings)
    tree = service.build("项目-旅行")

    class Tty:
        def isatty(self):
            return True

    monkeypatch.setattr(sys, "stdout", Tty())
    monkeypatch.delenv("NO_COLOR", raising=False)
    assert "\033[1;33m" in service.render_markdown(tree)
    monkeypatch.setenv("NO_COLOR", "1")
    assert "\033[1;33m" not in service.render_markdown(tree)


def test_non_project_page_without_para_is_not_project_even_with_marker(tmp_path):
    graph = tmp_path / "graph"
    pages = graph / "pages"
    pages.mkdir(parents=True)
    (pages / "普通页面.md").write_text("- **[目标]** 只是普通笔记里的目标\n", encoding="utf-8")
    result = LogseqAdapter(graph).scan()
    assert not [obj for obj in result.objects if obj.object_type == "project"]


def test_project_membership_proposal_apply_and_rollback_internal_relation(tmp_path):
    _graph, conn, repo, settings = write_round3_graph(tmp_path)
    task = next(item for item in repo.list_objects("task", limit=20) if "询问机场接送" in item["title"])
    project = next(item for item in repo.list_objects("project", limit=20) if item["title"] == "项目-旅行")
    proposal_service = ProposalService(conn, settings)
    proposal_id = ProjectMembershipService(conn, proposal_service).propose(str(task["id"]), str(project["id"]), reason="Daily log explicitly links project.")
    proposal = proposal_service.get(proposal_id)
    assert proposal["proposal_type"] == "link_to_project"
    assert proposal["risk"] == "low"
    proposal_service.accept(proposal_id)
    applied = proposal_service.apply(proposal_id)
    assert applied["applied_record"]["internal_only"] is True
    relation = conn.execute(
        "SELECT * FROM relations WHERE from_object_id=? AND to_object_id=? AND relation_type='belongs_to'",
        (task["id"], project["id"]),
    ).fetchone()
    assert relation is not None
    proposal_service.rollback(proposal_id)
    rolled = proposal_service.get(proposal_id)
    assert rolled["status"] == "rolled_back"


def test_promote_to_mini_project_proposal_is_reviewable(tmp_path):
    _graph, conn, repo, settings = write_round3_graph(tmp_path)
    task = next(item for item in repo.list_objects("task", limit=20) if item["title"] == "买转换插头")
    proposal_service = ProposalService(conn, settings)
    proposal_id = ProjectMembershipService(conn, proposal_service).propose_promote_to_mini_project(str(task["id"]))
    assert proposal_service.get(proposal_id)["proposal_type"] == "promote_to_mini_project"
    proposal_service.accept(proposal_id)
    proposal_service.apply(proposal_id)
    assert repo.list_annotations(target_object_id=task["id"])[0]["annotation_type"] == "mini_project_candidate"
    proposal_service.rollback(proposal_id)
    assert not repo.list_annotations(target_object_id=task["id"])


def test_clarify_selected_with_project_context_generates_membership_proposal(tmp_path):
    _graph, conn, repo, settings = write_round3_graph(tmp_path)
    task = next(item for item in repo.list_objects("task", limit=20) if "询问机场接送" in item["title"])
    service = ClarifyService(conn, settings)
    preview = service.start_selected([str(task["id"])], answer="属于这个项目", provider_name="dry-run", project_ref="项目-旅行")
    rendered = json.dumps(preview["payload_previews"], ensure_ascii=False)
    assert "project_context" in rendered
    assert "项目-旅行" in rendered

    result = service.start_selected([str(task["id"])], answer="属于这个项目，需要纳管", provider_name="mock", project_ref="项目-旅行")
    proposal_types = {item["proposal_type"] for item in result["proposals"]}
    assert "link_to_project" in proposal_types
    assert "logseq_append_marker" in proposal_types


def test_append_only_mini_project_writeback_preview_apply_resync_rollback(tmp_path):
    graph, conn, repo, settings = write_round3_graph(tmp_path)
    mini = next(item for item in repo.list_objects("mini_project", limit=20) if item["title"] == "整理打车攻略")
    target = graph / "pages" / "项目-旅行.md"
    before = target.read_text(encoding="utf-8")
    service = ProposalService(conn, settings)
    proposal_id = service.create_logseq_marker("小任务", "追加一个最小小任务节点", target_object_ref=str(mini["id"]))
    preview = service.preview(proposal_id)
    assert "+            - **[小任务]** 追加一个最小小任务节点" in preview["preview_diff"]
    assert target.read_text(encoding="utf-8") == before
    service.accept(proposal_id)
    service.apply(proposal_id, confirmed=True)
    assert "**[小任务]** 追加一个最小小任务节点" in target.read_text(encoding="utf-8")
    resynced = LogseqAdapter(graph).scan()
    assert any(obj.object_type == "mini_project" and obj.title == "追加一个最小小任务节点" for obj in resynced.objects)
    service.rollback(proposal_id)
    assert target.read_text(encoding="utf-8") == before


def test_project_tree_cli(tmp_path):
    graph, conn, _repo, _settings = write_round3_graph(tmp_path)
    conn.close()
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    env["TM_APP_DIR"] = str(tmp_path / "app")
    env["TM_DATABASE_PATH"] = str(tmp_path / "tm.sqlite3")
    env["TM_LOGSEQ_GRAPH"] = str(graph)
    proc = subprocess.run(
        ["python3", "-m", "task_manager_cli.cli.main", "project", "tree", "项目-旅行", "--format", "json"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    data = json.loads(proc.stdout)
    assert data["project"]["title"] == "项目-旅行"
    assert data["summary"]["has_structured_markers"] is True
