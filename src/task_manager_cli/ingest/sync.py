from pathlib import Path
from typing import Dict, Optional

from task_manager_cli.adapters.logseq.adapter import LogseqAdapter
from task_manager_cli.config.settings import Settings
from task_manager_cli.core.errors import ConfigError
from task_manager_cli.ingest.merger import Merger
from task_manager_cli.storage.database import init_db
from task_manager_cli.storage.repositories import Repository


class SyncService:
    def __init__(self, conn, settings: Settings):
        self.conn = conn
        self.settings = settings
        init_db(conn)
        self.repo = Repository(conn)

    def sync_logseq(self, dry_run: bool = False, recent_journals: Optional[int] = None) -> Dict[str, object]:
        graph_path = self.settings.logseq_graph_path
        if not graph_path:
            raise ConfigError("Logseq graph path is not configured.")
        graph_path = Path(graph_path).expanduser()
        if not graph_path.exists():
            raise ConfigError(f"Logseq graph path does not exist: {graph_path}")

        run_id = self.repo.create_sync_run("logseq", str(graph_path), dry_run)
        try:
            adapter = LogseqAdapter(graph_path, ignored_embed_uuids=self.settings.ignored_embed_uuids)
            result = adapter.scan(recent_journals=recent_journals)
            stats = result.stats()
            if not dry_run:
                ingest_stats = Merger(self.repo).ingest(result)
                stats.update(ingest_stats.as_dict())
            self.repo.finish_sync_run(run_id, "dry_run" if dry_run else "success", stats)
            self.conn.commit()
            return {"run_id": run_id, "dry_run": dry_run, **stats}
        except Exception as exc:
            self.repo.finish_sync_run(run_id, "error", {"errors_seen": 1, "metadata": {"error": str(exc)}})
            self.conn.commit()
            raise

    def sync_all(self, dry_run: bool = False, recent_journals: Optional[int] = None) -> Dict[str, object]:
        return self.sync_logseq(dry_run=dry_run, recent_journals=recent_journals)
