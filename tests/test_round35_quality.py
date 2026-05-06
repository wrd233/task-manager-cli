import json
import os
import subprocess
from pathlib import Path

import pytest

from task_manager_cli.adapters.logseq.adapter import LogseqAdapter
from task_manager_cli.clarify.service import ClarifyService
from task_manager_cli.config.settings import Settings
from task_manager_cli.ingest.merger import Merger
from task_manager_cli.projects.membership import ProjectMembershipService
from task_manager_cli.projects.quality import ProjectQualityService
from task_manager_cli.projects.tree import ProjectTreeService
from task_manager_cli.proposals.service import ProposalService
from task_manager_cli.storage.database import connect, init_db
from task_manager_cli.storage.repositories import Repository


ROOT = Path(__file__).resolve().parents[1]


def write_round35_graph(tmp_path):
    graph = tmp_path / "graph"
    pages = graph / "pages"
    journals = graph / "journals"
    pages.mkdir(parents=True)
    journals.mkdir(parents=True)
    (pages / "项目-完整.md").write_text(
        "PARA:: [[PARA/Project]]\n\n"
        "- [目标] 完成稳定版本\n"
        "    - [里程碑] Alpha\n"
        "        - **[工作流]** 验证\n"
        "            - [小任务] 扩展 fixture\n"
        "                - TODO 补质量报告测试\n"
        "                - [资源] pytest 文档 https://example.com\n"
        "                    - TODO 这个是资源页里的示例，不应进入行动流\n"
        "                - [成果] 覆盖 Round 3.5\n"
        "            - [具体事务] 发布前检查\n"
        "                - DONE 跑完整测试\n"
        "                    - [成果] baseline 通过\n"
        "    - [想法] 后续可以加可视化树\n"
        "    - [注] 用户保留原结构\n"
        "    - [AI注] 仅做诊断\n"
        "    - [待澄清] 是否进入 Round 4\n",
        encoding="utf-8",
    )
    (pages / "项目-凌乱.md").write_text(
        "PARA:: [[PARA/Project]]\n\n"
        "- 普通开头，没有结构化父节点\n"
        "    - TODO [[项目-凌乱]] 补一个任务\n"
        "- [资源] 资料区\n"
        "    - https://example.com/reference\n"
        "- [想法] 也许做成模板\n",
        encoding="utf-8",
    )
    (pages / "项目-空.md").write_text("PARA:: [[PARA/Project]]\n", encoding="utf-8")
    (pages / "普通页面.md").write_text(
        "- [目标] 这只是普通笔记，不应成为 Project\n"
        "    - TODO 普通页面待办\n",
        encoding="utf-8",
    )
    for day in range(1, 6):
        extra = ""
        if day == 1:
            extra = "- TODO [[项目-完整]] Daily 明确项目引用\n- #reference [[项目-完整]] 参考资料\n"
        if day == 2:
            extra = "- [小任务] Journal 小任务\n    - TODO Journal 子行动\n    - [资源] Journal 资源 https://example.com\n"
        if day == 3:
            extra = "- TODO 完整 这个弱关键词候选不要直接 proposal\n- TODO [[项目-凌乱]] Daily 凌乱项目任务 #inbox\n"
        if day == 4:
            extra = "- DONE [[项目-完整]] 已完成但无成果\n- TODO 等外部反馈 #waiting\n"
        if day == 5:
            extra = "- [想法] [[项目-完整]] 设计一个更轻的报告视图\n- TODO someday item #someday\n"
        (journals / f"2026_05_0{day}.md").write_text(extra, encoding="utf-8")
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


def test_round35_project_tree_quality_markdown_json_and_marker_variants(tmp_path):
    _graph, conn, repo, settings = write_round35_graph(tmp_path)
    service = ProjectQualityService(conn, settings)
    report = service.project_tree_quality()
    assert report["recognized_project_pages"] == 3
    assert report["skipped_non_project_pages"] == 1
    assert report["project_pages_with_structured_markers"] >= 2
    assert report["node_type_distribution"]["mini_project"] >= 1
    assert report["node_type_distribution"]["resource"] >= 1
    assert report["node_type_distribution"]["idea"] >= 1
    assert report["projects_with_empty_tree"]
    assert report["source_location_mismatch_count"] == 0
    markdown = service.markdown(report)
    assert "# Project Tree Quality" in markdown
    tree = ProjectTreeService(conn, settings).build("项目-完整")
    rendered = json.dumps(tree, ensure_ascii=False)
    assert '"marker": "小任务"' in rendered
    assert "pytest 文档" in rendered
    flat = []
    ProjectTreeService(conn, settings)._flatten(tree["tree"], flat)
    resource_child = next(node for node in flat if node["title"] == "这个是资源页里的示例，不应进入行动流")
    assert resource_child["node_type"] == "resource"
    assert resource_child["object_id"] is None
    assert resource_child["status"] is None
    assert not [obj for obj in repo.list_objects("project", limit=50) if obj["title"] == "普通页面"]


def test_round35_mini_project_quality_and_resource_boundary(tmp_path):
    _graph, conn, repo, settings = write_round35_graph(tmp_path)
    titles = {item["title"] for item in repo.list_objects("mini_project", limit=50)}
    assert "扩展 fixture" in titles
    assert "Journal 小任务" in titles
    task_titles = {item["title"] for item in repo.list_objects("task", limit=100)}
    assert "补质量报告测试" in task_titles
    assert "Journal 子行动" in task_titles
    assert "这个是资源页里的示例，不应进入行动流" not in task_titles
    mini = next(item for item in repo.list_objects("mini_project", limit=50) if item["title"] == "扩展 fixture")
    linked_resource_texts = [record["raw_text"] for record in repo.records_for_object(mini["id"], limit=50) if record.get("role") == "resource"]
    assert any("这个是资源页里的示例" in text for text in linked_resource_texts)
    report = ProjectQualityService(conn, settings).mini_project_quality()
    assert report["mini_project_count"] == 2
    assert report["mini_projects_from_project_pages"] == 1
    assert report["mini_projects_from_journals"] == 1
    assert report["mini_projects_with_resources"] >= 2
    assert report["mini_projects_wrongly_promoted_to_project"] == 0


def test_round35_membership_quality_duplicate_and_existing_relation_behavior(tmp_path):
    _graph, conn, repo, settings = write_round35_graph(tmp_path)
    proposal_service = ProposalService(conn, settings)
    membership = ProjectMembershipService(conn, proposal_service)
    task = next(item for item in repo.list_objects("task", limit=100) if item["title"] == "[[项目-完整]] Daily 明确项目引用")
    project = next(item for item in repo.list_objects("project", limit=20) if item["title"] == "项目-完整")
    first = membership.propose(str(task["id"]), str(project["id"]))
    second = membership.propose(str(task["id"]), str(project["id"]))
    assert first == second
    proposal_service.accept(first)
    proposal_service.apply(first)
    with pytest.raises(Exception, match="already exists"):
        membership.propose(str(task["id"]), str(project["id"]))
    report = ProjectQualityService(conn, settings).membership_quality()
    assert report["candidate_count"] >= 3
    assert report["high_confidence_count"] >= 1
    assert report["low_confidence_candidate_count"] >= 1
    assert report["low_confidence_not_promoted_count"] >= 1
    assert report["duplicate_proposal_count"] == 0
    assert report["existing_applied_relation_count"] >= 1


def test_round35_clarify_payload_short_and_low_confidence_provider_membership_skipped(tmp_path):
    _graph, conn, repo, settings = write_round35_graph(tmp_path)
    task = next(item for item in repo.list_objects("task", limit=100) if "Daily 明确项目引用" in item["title"])
    service = ClarifyService(conn, settings)
    preview = service.start_selected([str(task["id"])], answer="属于项目-完整", provider_name="dry-run", project_ref="项目-完整")
    payload = preview["payload_previews"][0]["payload"]
    rendered = json.dumps(payload, ensure_ascii=False)
    assert "project_context" in rendered
    assert "完成稳定版本" in rendered
    assert "PARA::" not in rendered
    assert payload["payload_size_chars"] < 6000
    fake_result = type(
        "FakeResult",
        (),
        {
            "summary": "low confidence",
            "proposal_candidates": [
                {
                    "proposal_type": "link_to_project",
                    "risk": "low",
                    "target": {"object_id": str(task["id"]), "project_id": 1},
                    "payload": {"target_project_id": 1},
                    "confidence": 0.4,
                    "reasoning_summary": "weak keyword only",
                    "needs_user_confirmation": True,
                }
            ],
            "confidence": 0.4,
            "reasoning_summary": "weak",
            "needs_user_confirmation": True,
        },
    )()
    assert service._result_to_proposals(1, int(task["id"]), fake_result) == []


def test_round35_append_only_repeated_writeback_apply_resync_rollback(tmp_path):
    graph, conn, repo, settings = write_round35_graph(tmp_path)
    mini = next(item for item in repo.list_objects("mini_project", limit=20) if item["title"] == "扩展 fixture")
    target = graph / "pages" / "项目-完整.md"
    before = target.read_text(encoding="utf-8")
    service = ProposalService(conn, settings)
    first = service.create_append_child("((block-round35-ref))", target_object_ref=str(mini["id"]))
    service.preview(first)
    service.accept(first)
    service.apply(first, confirmed=True)
    after_first = target.read_text(encoding="utf-8")
    second = service.create_logseq_marker("资源", "追加资源 https://example.com/round35", target_object_ref=str(mini["id"]))
    service.preview(second)
    service.accept(second)
    service.apply(second, confirmed=True)
    assert "追加资源" in target.read_text(encoding="utf-8")
    resynced = LogseqAdapter(graph).scan()
    assert any(obj.title == "扩展 fixture" for obj in resynced.objects if obj.object_type == "mini_project")
    service.rollback(second)
    assert target.read_text(encoding="utf-8") == after_first
    service.rollback(first)
    assert target.read_text(encoding="utf-8") == before


def test_round35_quality_cli_commands(tmp_path):
    graph, conn, _repo, _settings = write_round35_graph(tmp_path)
    conn.close()
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    env["TM_APP_DIR"] = str(tmp_path / "app")
    env["TM_DATABASE_PATH"] = str(tmp_path / "tm.sqlite3")
    env["TM_LOGSEQ_GRAPH"] = str(graph)
    for command in ("project-tree-quality", "mini-project-quality", "membership-quality"):
        proc = subprocess.run(
            ["python3", "-m", "task_manager_cli.cli.main", "report", command, "--format", "json"],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=True,
        )
        assert json.loads(proc.stdout)["view"] == command


def test_round35_sync_accepts_temporary_graph_argument(tmp_path):
    graph, conn, _repo, _settings = write_round35_graph(tmp_path)
    conn.close()
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    env["TM_APP_DIR"] = str(tmp_path / "fresh-app")
    env["TM_DATABASE_PATH"] = str(tmp_path / "fresh.sqlite3")
    proc = subprocess.run(
        ["python3", "-m", "task_manager_cli.cli.main", "sync", "logseq", "--graph", str(graph)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    data = json.loads(proc.stdout)
    assert data["files_scanned"] >= 9
    assert data["objects_seen"] >= 1
