import json
import os
import subprocess
import sys
from pathlib import Path

from tests.test_human_shell_semantic_node_show import semantic_shell


ROOT = Path(__file__).resolve().parents[1]


def test_agent_project_node_raw_markdown_and_json(tmp_path):
    shell, _repo = semantic_shell(tmp_path)
    settings = shell.settings
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    env["TM_APP_DIR"] = str(settings.app_dir)
    env["TM_DATABASE_PATH"] = str(settings.database_path)
    env["TM_LOGSEQ_GRAPH"] = str(settings.logseq_graph_path)

    node_id = "block:bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    markdown = subprocess.run(
        [sys.executable, "-m", "task_manager_cli.cli.main", "agent", "project-node", node_id, "--raw", "--context"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    ).stdout
    assert "readonly: true" in markdown
    assert "Ancestor Context" in markdown
    assert "Raw Subtree" in markdown
    assert "普通备注保留" in markdown
    assert "TODO 节点内 TODO" in markdown

    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "task_manager_cli.cli.main",
            "agent",
            "project-node",
            node_id,
            "--format",
            "json",
        ],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    data = json.loads(proc.stdout)
    assert data["readonly"] is True
    assert data["node"]["id"] == node_id
    assert data["node"]["node_type"] == "workflow"
    assert "普通备注保留" in data["raw_subtree"]
