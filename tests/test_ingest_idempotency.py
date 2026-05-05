from pathlib import Path

from task_manager_cli.adapters.logseq.adapter import LogseqAdapter
from task_manager_cli.ingest.merger import Merger
from task_manager_cli.storage.database import connect, init_db
from task_manager_cli.storage.repositories import Repository


FIXTURE = Path(__file__).parent / "fixtures" / "logseq_graph"


def test_ingest_is_idempotent(tmp_path):
    conn = connect(tmp_path / "tm.sqlite3")
    init_db(conn)
    repo = Repository(conn)
    result = LogseqAdapter(FIXTURE).scan()
    Merger(repo).ingest(result)
    conn.commit()
    first = repo.stats()
    Merger(repo).ingest(result)
    conn.commit()
    second = repo.stats()
    assert first["objects"] == second["objects"]
    assert first["records"] == second["records"]
