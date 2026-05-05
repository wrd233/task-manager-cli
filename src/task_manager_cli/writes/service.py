import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from task_manager_cli.config.settings import Settings
from task_manager_cli.core.errors import ConfigError, NotFoundError
from task_manager_cli.storage.repositories import Repository
from task_manager_cli.writes.logseq_writer import LogseqWriter, WriteError, WritePreview


WRITE_MODES = {"disabled", "proposal", "guarded", "agent"}
APPLY_MODES = {"guarded", "agent"}


class WriteService:
    def __init__(self, conn, settings: Settings):
        self.conn = conn
        self.settings = settings
        self.repo = Repository(conn)
        if not settings.logseq_graph_path:
            raise ConfigError("Logseq graph path is not configured.")
        self.writer = LogseqWriter(settings.logseq_graph_path)

    def create_append_child_proposal(
        self,
        content: str,
        target_object_ref: Optional[str] = None,
        file_path: Optional[str] = None,
        block_uuid: Optional[str] = None,
        line_start: Optional[int] = None,
        author: str = "agent",
    ) -> int:
        self._ensure_can_propose("append_child_block")
        target_object_id = None
        if target_object_ref:
            target_object_id = self.repo.resolve_object_id(target_object_ref)
            if target_object_id is None:
                raise NotFoundError(f"Target object not found: {target_object_ref}")
            obj = self.repo.get_object(target_object_id)
            file_path = file_path or obj.get("file_path")
            block_uuid = block_uuid or obj.get("block_uuid")
            line_start = line_start or obj.get("line_start")
        if not file_path:
            raise ConfigError("append-child requires --object or --file.")
        preview = self.writer.preview_append_child(Path(file_path), content, block_uuid=block_uuid, line_start=line_start)
        return self._insert_proposal(
            operation_type="append_child_block",
            preview=preview,
            content=content,
            author=author,
            target_object_id=target_object_id,
            block_uuid=block_uuid or preview.block_uuid,
            line_start=line_start or preview.line_start,
            metadata={"target_object_ref": target_object_ref},
        )

    def create_append_page_section_proposal(
        self,
        content: str,
        section_marker: str,
        target_object_ref: Optional[str] = None,
        file_path: Optional[str] = None,
        author: str = "agent",
    ) -> int:
        self._ensure_can_propose("append_page_section")
        target_object_id = None
        if target_object_ref:
            target_object_id = self.repo.resolve_object_id(target_object_ref)
            if target_object_id is None:
                raise NotFoundError(f"Target object not found: {target_object_ref}")
            obj = self.repo.get_object(target_object_id)
            file_path = file_path or obj.get("file_path")
        if not file_path:
            raise ConfigError("append-section requires --object or --file.")
        preview = self.writer.preview_append_page_section(Path(file_path), section_marker, content)
        return self._insert_proposal(
            operation_type="append_page_section",
            preview=preview,
            content=content,
            author=author,
            target_object_id=target_object_id,
            section_marker=section_marker,
            metadata={"target_object_ref": target_object_ref},
        )

    def create_page_proposal(self, page_name: str, content: str, author: str = "agent") -> int:
        self._ensure_can_propose("create_page")
        preview = self.writer.preview_create_page(page_name, content)
        return self._insert_proposal(
            operation_type="create_page",
            preview=preview,
            content=content,
            author=author,
            page_name=page_name,
            metadata={"page_name": page_name},
        )

    def list_proposals(self, status: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM write_proposals"
        params: List[Any] = []
        if status:
            sql += " WHERE status=?"
            params.append(status)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        return [self._proposal_row(row) for row in self.conn.execute(sql, params).fetchall()]

    def get_proposal(self, proposal_id: int) -> Dict[str, Any]:
        row = self.conn.execute("SELECT * FROM write_proposals WHERE id=?", (proposal_id,)).fetchone()
        if not row:
            raise NotFoundError(f"Write proposal not found: {proposal_id}")
        return self._proposal_row(row)

    def preview(self, proposal_id: int) -> Dict[str, Any]:
        return self.get_proposal(proposal_id)

    def reject(self, proposal_id: int) -> None:
        cur = self.conn.execute(
            "UPDATE write_proposals SET status='rejected', updated_at=CURRENT_TIMESTAMP WHERE id=? AND status='open'",
            (proposal_id,),
        )
        if cur.rowcount == 0:
            raise NotFoundError(f"Open write proposal not found: {proposal_id}")

    def apply(self, proposal_id: int, confirmed: bool = False) -> Dict[str, Any]:
        self._ensure_can_apply()
        if self.settings.write_require_confirm and self.settings.write_mode != "agent" and not confirmed:
            raise ConfigError("Applying writes requires --yes in the current write configuration.")
        proposal = self.get_proposal(proposal_id)
        if proposal["status"] != "open":
            raise WriteError(f"Proposal is not open: {proposal['status']}")
        preview = self._rebuild_preview(proposal)
        backup_path = self.writer.apply(preview, proposal.get("file_sha256"), self.settings.write_backup_dir or self.settings.app_dir / "backups")
        self.conn.execute(
            """
            UPDATE write_proposals
            SET status='applied', backup_path=?, updated_at=CURRENT_TIMESTAMP, applied_at=CURRENT_TIMESTAMP, error=NULL
            WHERE id=?
            """,
            (str(backup_path) if str(backup_path) else None, proposal_id),
        )
        return {"proposal_id": proposal_id, "status": "applied", "file_path": str(preview.file_path), "backup_path": str(backup_path) if str(backup_path) else None}

    def _rebuild_preview(self, proposal: Dict[str, Any]) -> WritePreview:
        op = proposal["operation_type"]
        if op == "append_child_block":
            return self.writer.preview_append_child(
                Path(proposal["file_path"]),
                proposal["content"],
                block_uuid=proposal.get("block_uuid"),
                line_start=proposal.get("line_start"),
            )
        if op == "append_page_section":
            return self.writer.preview_append_page_section(Path(proposal["file_path"]), proposal["section_marker"], proposal["content"])
        if op == "create_page":
            return self.writer.preview_create_page(proposal["page_name"], proposal["content"])
        raise WriteError(f"Unsupported proposal operation: {op}")

    def _insert_proposal(
        self,
        operation_type: str,
        preview: WritePreview,
        content: str,
        author: str,
        target_object_id: Optional[int] = None,
        block_uuid: Optional[str] = None,
        line_start: Optional[int] = None,
        section_marker: Optional[str] = None,
        page_name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        cur = self.conn.execute(
            """
            INSERT INTO write_proposals(
                operation_type, target_object_id, graph_path, file_path, page_name,
                block_uuid, line_start, section_marker, content, preview_diff,
                file_sha256, author, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                operation_type,
                target_object_id,
                str(self.settings.logseq_graph_path),
                str(preview.file_path),
                page_name,
                block_uuid,
                line_start,
                section_marker,
                content,
                preview.diff,
                preview.original_sha256,
                author,
                json.dumps(metadata or {}, ensure_ascii=False),
            ),
        )
        return int(cur.lastrowid)

    def _ensure_can_propose(self, operation: str) -> None:
        if self.settings.write_mode not in WRITE_MODES:
            raise ConfigError(f"Unsupported write_mode: {self.settings.write_mode}")
        if self.settings.write_mode == "disabled":
            raise ConfigError("Write mode is disabled. Use `tm config set-write-mode proposal` or `guarded` first.")
        if operation not in self.settings.allowed_write_operations:
            raise ConfigError(f"Write operation is not allowed by config: {operation}")

    def _ensure_can_apply(self) -> None:
        if self.settings.write_mode not in APPLY_MODES:
            raise ConfigError("Applying writes requires write_mode `guarded` or `agent`.")

    def _proposal_row(self, row) -> Dict[str, Any]:
        data = dict(row)
        data["metadata"] = json.loads(data.pop("metadata_json") or "{}")
        return data
