import json
from pathlib import Path

import pytest

from task_manager_cli.adapters.logseq.adapter import LogseqAdapter
from task_manager_cli.config.settings import Settings
from task_manager_cli.core.errors import TaskManagerError
from task_manager_cli.ingest.merger import Merger
from task_manager_cli.projects.lifecycle import ProjectLifecycleService
from task_manager_cli.proposals.service import ProposalService
from task_manager_cli.shell.service import HumanShellService
from task_manager_cli.storage.database import connect, init_db
from task_manager_cli.storage.repositories import Repository


def lifecycle_env(tmp_path):
    graph = tmp_path / "graph"
    (graph / "pages").mkdir(parents=True)
    (graph / "journals").mkdir()
    conn = connect(tmp_path / "tm.sqlite3")
    init_db(conn)
    settings = Settings(
        app_dir=tmp_path / "app",
        database_path=tmp_path / "tm.sqlite3",
        logseq_graph_path=graph,
        write_mode="guarded",
        write_backup_dir=tmp_path / "backups",
        write_require_confirm=False,
    )
    return graph, conn, Repository(conn), settings


def test_project_create_templates_goal_shell_undo(tmp_path):
    graph, conn, repo, settings = lifecycle_env(tmp_path)
    service = ProjectLifecycleService(conn, settings)
    preview = service.create_project("测试项目", template="minimal", preview=True)
    assert "Project" in preview["preview_diff"]
    result = service.create_project("测试项目", template="standard", goal="形成第一版成果")
    conn.commit()
    page = graph / "pages" / "测试项目.md"
    text = page.read_text(encoding="utf-8")
    assert "PARA:: [[PARA/Project]]" in text
    assert "形成第一版成果" in text
    assert repo.resolve_object_id("测试项目")
    with pytest.raises(Exception):
        service.create_project("测试项目")

    shell = HumanShellService(conn, settings)
    assert "project created" in shell.run_line('project create "第二项目" --template minimal --enter')
    assert shell.context.path == "/projects/第二项目"
    assert (graph / "pages" / "第二项目.md").exists()
    assert "Undone op" in shell.run_line("undo")
    assert not (graph / "pages" / "第二项目.md").exists()


def test_project_capture_unplaced_clarify_pack_health_and_dashboard(tmp_path):
    graph, conn, repo, settings = lifecycle_env(tmp_path)
    shell = HumanShellService(conn, settings)
    shell.run_line('project create "测试项目" --enter')
    shell.run_line('todo "先记录一个任务"')
    shell.run_line('idea "一个还不成熟的想法"')
    shell.run_line('resource "一个参考资料"')
    shell.run_line('result "形成第一版成果"')

    listing = shell.run_line("ls unplaced")
    assert "先记录一个任务" in listing
    assert "一个还不成熟的想法" in listing
    assert "ls inbox" and "先记录一个任务" in shell.run_line("ls inbox")
    assert shell.run_line("cd inbox") == "/projects/测试项目/inbox"
    assert "先记录一个任务" in shell.run_line("ls inbox")
    shell.run_line("cd ..")

    service = ProjectLifecycleService(conn, settings)
    unplaced = service.unplaced("测试项目")
    assert len(unplaced) >= 2
    assert any(item["object_type"] == "task" for item in unplaced)
    assert "先记录一个任务" in shell.run_line("ls tasks")
    assert "一个还不成熟的想法" in shell.run_line("ls ideas")
    assert "一个参考资料" in shell.run_line("ls resources")

    clarify = service.clarify_project("测试项目", target="unplaced", provider_name="mock")
    conn.commit()
    assert clarify["proposal_ids"]
    assert any(item["proposal_type"] == "link_object_to_node" for item in clarify["proposals"])
    assert "link_object_to_node" in shell.run_line("proposals")

    pack = service.project_pack("测试项目")
    assert pack["unplaced_objects"]
    assert pack["project_health"]["unplaced_count"] >= 2
    assert "forbidden_operations" in pack["constraints"]
    assert "raw_text" not in json.dumps(pack["semantic_tree"], ensure_ascii=False)

    restructure_pack = service.restructure_pack("测试项目")
    assert restructure_pack["semantic_tree"]
    assert restructure_pack["expected_output_schema"]["summary"] == "string"
    assert "raw_evidence_command" in json.dumps(restructure_pack, ensure_ascii=False)

    health = service.project_health("测试项目")
    assert health["results_count"] == 1
    assert health["pending_proposals_count"] >= 1
    assert "Project Health" in shell.run_line("quality project")
    shell.run_line("cd /dashboard")
    assert "Projects Needing Attention" in shell.run_line("ls quality")
    assert "Unplaced Items" in shell.run_line("ls unplaced")


def test_agent_output_to_safe_apply_and_rollback(tmp_path):
    graph, conn, repo, settings = lifecycle_env(tmp_path)
    shell = HumanShellService(conn, settings)
    shell.run_line('project create "测试项目" --enter')
    shell.run_line('todo "先记录一个任务"')
    task = next(item for item in repo.list_objects("task", limit=20) if item["title"] == "先记录一个任务")
    output = {
        "summary": "建议建立执行节点并归位任务。",
        "questions_for_user": [],
        "proposed_nodes": [{"title": "执行", "node_type": "specific_work", "section": "具体事务"}],
        "object_mappings": [{"object_id": task["id"], "target_project_node_id": None, "confidence": 0.8}],
        "proposal_candidates": [
            {
                "proposal_type": "append_block_ref_to_node",
                "title": "Append task ref to project inbox",
                "risk": "medium",
                "target": {"object_id": task["id"]},
                "payload": {
                    "target_project_id": repo.resolve_object_id("测试项目"),
                    "target_project_node_id": None,
                    "file_path": str(graph / "pages" / "测试项目.md"),
                    "line_start": 6,
                    "source_object_id": task["id"],
                    "source_block_uuid": task["block_uuid"],
                },
            }
        ],
        "risks": [],
        "unplaced_remaining": [],
    }
    output_path = tmp_path / "agent-output.json"
    output_path.write_text(json.dumps(output, ensure_ascii=False), encoding="utf-8")

    service = ProjectLifecycleService(conn, settings)
    generated = service.proposals_from_agent_output("测试项目", output_path)
    conn.commit()
    types = {item["proposal_type"] for item in generated["proposals"]}
    assert {"create_project_node", "link_object_to_node", "append_block_ref_to_node"} <= types

    proposal_service = ProposalService(conn, settings)
    create_id = next(item["id"] for item in generated["proposals"] if item["proposal_type"] == "create_project_node")
    before = (graph / "pages" / "测试项目.md").read_text(encoding="utf-8")
    assert "执行" in proposal_service.preview(create_id)["preview_diff"]
    proposal_service.accept(create_id)
    proposal_service.apply(create_id, confirmed=True)
    assert "**[具体事务]** 执行" in (graph / "pages" / "测试项目.md").read_text(encoding="utf-8")
    proposal_service.rollback(create_id)
    assert (graph / "pages" / "测试项目.md").read_text(encoding="utf-8") == before

    link_id = next(item["id"] for item in generated["proposals"] if item["proposal_type"] == "link_object_to_node")
    proposal_service.accept(link_id)
    applied = proposal_service.apply(link_id)
    assert applied["applied_record"]["internal_only"] is True
    proposal_service.rollback(link_id)

    high = proposal_service.create("move_original_block", "Forbidden move", {}, risk="high")
    proposal_service.accept(high)
    with pytest.raises(TaskManagerError):
        proposal_service.apply_many([high], confirmed=True)


def test_invalid_agent_output_rejected_without_writeback(tmp_path):
    graph, conn, _repo, settings = lifecycle_env(tmp_path)
    service = ProjectLifecycleService(conn, settings)
    service.create_project("测试项目")
    conn.commit()
    before = (graph / "pages" / "测试项目.md").read_text(encoding="utf-8")
    bad = tmp_path / "bad.json"
    bad.write_text('{"summary": "missing arrays"}', encoding="utf-8")
    with pytest.raises(ValueError):
        service.proposals_from_agent_output("测试项目", bad)
    assert (graph / "pages" / "测试项目.md").read_text(encoding="utf-8") == before
