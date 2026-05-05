import json
from pathlib import Path

from task_manager_cli.adapters.logseq.adapter import LogseqAdapter
from task_manager_cli.ingest.merger import Merger
from task_manager_cli.output.formatters import to_json
from task_manager_cli.query.service import QueryService
from task_manager_cli.storage.database import connect, init_db
from task_manager_cli.storage.repositories import Repository


FIXTURE = Path(__file__).parent / "fixtures" / "logseq_graph"


def test_agent_context_is_json_parseable(tmp_path):
    conn = connect(tmp_path / "tm.sqlite3")
    init_db(conn)
    Merger(Repository(conn)).ingest(LogseqAdapter(FIXTURE).scan())
    conn.commit()
    payload = QueryService(conn).agent_context(object_type="task", limit=3)
    assert json.loads(to_json(payload))["packages"]
