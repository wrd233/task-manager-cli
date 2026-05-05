import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from task_manager_cli.annotations.service import AnnotationService
from task_manager_cli.config.settings import Settings
from task_manager_cli.core.enums import ProposalRisk, ProposalStatus, ProposalType
from task_manager_cli.core.errors import ConfigError, NotFoundError, TaskManagerError
from task_manager_cli.storage.repositories import Repository
from task_manager_cli.writes.logseq_writer import LogseqWriter, WriteError


LOW_RISK = {
    ProposalType.STATUS_CHANGE.value,
    ProposalType.RELATION_CHANGE.value,
    ProposalType.ANNOTATION.value,
    ProposalType.NEEDS_CLARIFICATION.value,
}
MEDIUM_RISK = {
    ProposalType.LOGSEQ_APPEND_MARKER.value,
    ProposalType.LOGSEQ_TASK_MARKER.value,
    ProposalType.CREATE_MINI_PROJECT.value,
    ProposalType.RESULT_MARKER.value,
    ProposalType.CREATE_PROJECT_NODE.value,
}
HIGH_RISK = {
    ProposalType.DELETE.value,
    ProposalType.MERGE.value,
    ProposalType.BULK_LOGSEQ_WRITEBACK.value,
    ProposalType.REWRITE_TITLE.value,
    ProposalType.PROJECT_TREE_REWRITE.value,
}

LOGSEQ_MARKERS = {"**[注]**", "**[AI注]**", "**[待澄清]**", "**[成果]**", "**[无成果]**"}


class ProposalService:
    def __init__(self, conn, settings: Optional[Settings] = None):
        self.conn = conn
        self.settings = settings
        self.repo = Repository(conn)

    def create(
        self,
        proposal_type: str,
        title: str,
        payload: Dict[str, Any],
        risk: Optional[str] = None,
        target_object_ref: Optional[str] = None,
        target_record_ref: Optional[str] = None,
        review_session_id: Optional[int] = None,
        source: str = "agent",
        rationale: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        target_object_id = self.repo.resolve_object_id(target_object_ref) if target_object_ref else None
        target_record_id = self.repo.resolve_record_id(target_record_ref) if target_record_ref else None
        if target_object_ref and target_object_id is None:
            raise NotFoundError(f"Target object not found: {target_object_ref}")
        if target_record_ref and target_record_id is None:
            raise NotFoundError(f"Target record not found: {target_record_ref}")
        risk = risk or classify_risk(proposal_type, payload)
        cur = self.conn.execute(
            """
            INSERT INTO proposals(
                proposal_type, title, status, risk, target_object_id, target_record_id,
                review_session_id, source, rationale, payload_json, metadata_json
            ) VALUES (?, ?, 'suggested', ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                proposal_type,
                title,
                risk,
                target_object_id,
                target_record_id,
                review_session_id,
                source,
                rationale,
                json.dumps(payload, ensure_ascii=False, sort_keys=True),
                json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True),
            ),
        )
        proposal_id = int(cur.lastrowid)
        self._event(proposal_id, "created", source, {"risk": risk})
        return proposal_id

    def create_annotation(
        self,
        content: str,
        target_object_ref: Optional[str] = None,
        target_record_ref: Optional[str] = None,
        author: str = "agent",
        review_session_id: Optional[int] = None,
    ) -> int:
        return self.create(
            ProposalType.ANNOTATION.value,
            "Add internal annotation",
            {"content": content, "author": author, "annotation_type": "comment"},
            target_object_ref=target_object_ref,
            target_record_ref=target_record_ref,
            review_session_id=review_session_id,
            source=author,
        )

    def create_logseq_marker(
        self,
        marker: str,
        content: str,
        target_object_ref: Optional[str] = None,
        file_path: Optional[str] = None,
        block_uuid: Optional[str] = None,
        line_start: Optional[int] = None,
        source: str = "agent",
    ) -> int:
        marker = normalize_marker(marker)
        if marker not in LOGSEQ_MARKERS:
            raise ValueError(f"Unsupported writeback marker: {marker}")
        proposal_type = ProposalType.RESULT_MARKER.value if marker in {"**[成果]**", "**[无成果]**"} else ProposalType.LOGSEQ_APPEND_MARKER.value
        payload = {"marker": marker, "content": content, "file_path": file_path, "block_uuid": block_uuid, "line_start": line_start}
        return self.create(proposal_type, f"Append {marker} to Logseq block", payload, target_object_ref=target_object_ref, source=source)

    def create_task_marker(self, new_marker: str, target_object_ref: Optional[str] = None, file_path: Optional[str] = None, block_uuid: Optional[str] = None, line_start: Optional[int] = None, source: str = "agent") -> int:
        return self.create(
            ProposalType.LOGSEQ_TASK_MARKER.value,
            f"Change Logseq task marker to {new_marker.upper()}",
            {"new_marker": new_marker.upper(), "file_path": file_path, "block_uuid": block_uuid, "line_start": line_start},
            target_object_ref=target_object_ref,
            source=source,
        )

    def list(self, status: Optional[str] = None, review_session_id: Optional[int] = None, limit: int = 50) -> List[Dict[str, Any]]:
        where = []
        params: List[Any] = []
        if status:
            where.append("status=?")
            params.append(status)
        if review_session_id:
            where.append("review_session_id=?")
            params.append(review_session_id)
        sql = "SELECT * FROM proposals"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        return [self._row(row) for row in self.conn.execute(sql, params).fetchall()]

    def get(self, proposal_id: int) -> Dict[str, Any]:
        row = self.conn.execute("SELECT * FROM proposals WHERE id=?", (proposal_id,)).fetchone()
        if not row:
            raise NotFoundError(f"Proposal not found: {proposal_id}")
        data = self._row(row)
        data["events"] = [self._event_row(item) for item in self.conn.execute("SELECT * FROM proposal_events WHERE proposal_id=? ORDER BY id", (proposal_id,)).fetchall()]
        return data

    def preview(self, proposal_id: int) -> Dict[str, Any]:
        proposal = self.get(proposal_id)
        if proposal["proposal_type"] in {ProposalType.LOGSEQ_APPEND_MARKER.value, ProposalType.RESULT_MARKER.value, ProposalType.NEEDS_CLARIFICATION.value}:
            preview = self._logseq_marker_preview(proposal)
            proposal["preview_diff"] = preview.diff
            proposal["file_sha256"] = preview.original_sha256
            self._event(proposal_id, "previewed", "user", {"file_path": str(preview.file_path), "line_start": preview.line_start, "block_uuid": preview.block_uuid})
            return proposal
        if proposal["proposal_type"] == ProposalType.LOGSEQ_TASK_MARKER.value:
            preview = self._task_marker_preview(proposal)
            proposal["preview_diff"] = preview.diff
            proposal["file_sha256"] = preview.original_sha256
            self._event(proposal_id, "previewed", "user", {"file_path": str(preview.file_path), "line_start": preview.line_start, "block_uuid": preview.block_uuid})
            return proposal
        return proposal

    def accept(self, proposal_id: int, actor: str = "user") -> None:
        self._transition(proposal_id, ProposalStatus.SUGGESTED.value, ProposalStatus.ACCEPTED.value, "accepted", actor)

    def reject(self, proposal_id: int, actor: str = "user") -> None:
        proposal = self.get(proposal_id)
        if proposal["status"] not in {ProposalStatus.SUGGESTED.value, ProposalStatus.EDITED.value}:
            raise TaskManagerError(f"Proposal {proposal_id} is not suggested or edited.")
        self.conn.execute(
            "UPDATE proposals SET status='rejected', updated_at=CURRENT_TIMESTAMP, rejected_at=CURRENT_TIMESTAMP WHERE id=?",
            (proposal_id,),
        )
        self._event(proposal_id, "rejected", actor, {})

    def edit(
        self,
        proposal_id: int,
        title: Optional[str] = None,
        content: Optional[str] = None,
        marker: Optional[str] = None,
        task_marker: Optional[str] = None,
        risk: Optional[str] = None,
        rationale: Optional[str] = None,
        actor: str = "user",
    ) -> Dict[str, Any]:
        proposal = self.get(proposal_id)
        if proposal["status"] in {ProposalStatus.APPLIED.value, ProposalStatus.ROLLED_BACK.value}:
            raise TaskManagerError("Applied or rolled-back proposals cannot be edited in place.")
        before = {
            "title": proposal["title"],
            "risk": proposal["risk"],
            "rationale": proposal.get("rationale"),
            "payload": proposal["payload"],
        }
        payload = dict(proposal["payload"])
        if content is not None:
            payload["content"] = content
        if marker is not None:
            payload["marker"] = normalize_marker(marker)
        if task_marker is not None:
            payload["new_marker"] = task_marker.upper()
        new_risk = risk or proposal["risk"]
        if new_risk not in {item.value for item in ProposalRisk}:
            raise ValueError(f"Unsupported proposal risk: {new_risk}")
        self.conn.execute(
            """
            UPDATE proposals
            SET title=?, risk=?, rationale=?, payload_json=?, status='edited', updated_at=CURRENT_TIMESTAMP
            WHERE id=?
            """,
            (
                title if title is not None else proposal["title"],
                new_risk,
                rationale if rationale is not None else proposal.get("rationale"),
                json.dumps(payload, ensure_ascii=False, sort_keys=True),
                proposal_id,
            ),
        )
        self._event(proposal_id, "edited", actor, {"before": before, "after": {"title": title, "risk": new_risk, "rationale": rationale, "payload": payload}})
        return self.get(proposal_id)

    def supersede(self, proposal_id: int, new_proposal_id: int, actor: str = "user") -> None:
        old = self.get(proposal_id)
        new = self.get(new_proposal_id)
        if old["status"] == ProposalStatus.APPLIED.value:
            raise TaskManagerError("Applied proposals cannot be superseded.")
        cur = self.conn.execute(
            "UPDATE proposals SET status='superseded', updated_at=CURRENT_TIMESTAMP WHERE id=? AND status!='applied'",
            (proposal_id,),
        )
        if cur.rowcount == 0:
            raise TaskManagerError(f"Proposal {proposal_id} cannot be superseded.")
        self._event(proposal_id, "superseded", actor, {"with": new_proposal_id})
        self._event(new_proposal_id, "supersedes", actor, {"old": proposal_id, "old_title": old["title"], "new_title": new["title"]})

    def apply(self, proposal_id: int, confirmed: bool = False, actor: str = "user") -> Dict[str, Any]:
        proposal = self.get(proposal_id)
        if proposal["status"] != ProposalStatus.ACCEPTED.value:
            raise TaskManagerError("Proposal must be accepted before apply.")
        applied_record: Dict[str, Any]
        if proposal["proposal_type"] == ProposalType.ANNOTATION.value:
            payload = proposal["payload"]
            annotation_id = AnnotationService(self.conn).add(
                str(proposal["target_object_id"]) if proposal["target_object_id"] else None,
                payload["content"],
                author=payload.get("author", "agent"),
                annotation_type=payload.get("annotation_type", "comment"),
                target_record_ref=str(proposal["target_record_id"]) if proposal["target_record_id"] else None,
            )
            applied_record = {"annotation_id": annotation_id}
        elif proposal["proposal_type"] in {ProposalType.LOGSEQ_APPEND_MARKER.value, ProposalType.RESULT_MARKER.value, ProposalType.NEEDS_CLARIFICATION.value}:
            self._ensure_write_apply_allowed(confirmed)
            self._ensure_previewed(proposal_id)
            preview = self._logseq_marker_preview(proposal)
            backup = self._writer().apply(preview, preview.original_sha256, self._backup_dir())
            applied_record = {"file_path": str(preview.file_path), "backup_path": str(backup), "line_start": preview.line_start, "block_uuid": preview.block_uuid}
        elif proposal["proposal_type"] == ProposalType.LOGSEQ_TASK_MARKER.value:
            self._ensure_write_apply_allowed(confirmed)
            self._ensure_previewed(proposal_id)
            preview = self._task_marker_preview(proposal)
            backup = self._writer().apply(preview, preview.original_sha256, self._backup_dir())
            applied_record = {"file_path": str(preview.file_path), "backup_path": str(backup), "line_start": preview.line_start, "block_uuid": preview.block_uuid}
        else:
            raise TaskManagerError(f"Apply is not implemented for proposal type: {proposal['proposal_type']}")
        self.conn.execute(
            """
            UPDATE proposals SET status='applied', applied_record_json=?, updated_at=CURRENT_TIMESTAMP, applied_at=CURRENT_TIMESTAMP
            WHERE id=?
            """,
            (json.dumps(applied_record, ensure_ascii=False, sort_keys=True), proposal_id),
        )
        self._event(proposal_id, "applied", actor, applied_record)
        return {"proposal_id": proposal_id, "status": "applied", "applied_record": applied_record}

    def rollback(self, proposal_id: int, actor: str = "user") -> Dict[str, Any]:
        proposal = self.get(proposal_id)
        if proposal["status"] != ProposalStatus.APPLIED.value:
            raise TaskManagerError("Only applied proposals can be rolled back.")
        record = proposal.get("applied_record") or {}
        rollback_record: Dict[str, Any] = {}
        if "annotation_id" in record:
            self.conn.execute("DELETE FROM annotations WHERE id=?", (int(record["annotation_id"]),))
            rollback_record = {"deleted_annotation_id": int(record["annotation_id"])}
        elif record.get("backup_path") and record.get("file_path"):
            self._writer().restore_backup(Path(record["backup_path"]), Path(record["file_path"]))
            rollback_record = {"restored_backup_path": record["backup_path"], "file_path": record["file_path"]}
        else:
            raise TaskManagerError("Proposal does not contain enough rollback information.")
        self.conn.execute(
            """
            UPDATE proposals SET status='rolled_back', rollback_record_json=?, updated_at=CURRENT_TIMESTAMP, rolled_back_at=CURRENT_TIMESTAMP
            WHERE id=?
            """,
            (json.dumps(rollback_record, ensure_ascii=False, sort_keys=True), proposal_id),
        )
        self._event(proposal_id, "rolled_back", actor, rollback_record)
        return {"proposal_id": proposal_id, "status": "rolled_back", "rollback_record": rollback_record}

    def apply_many(self, proposal_ids: List[int], confirmed: bool = False) -> List[Dict[str, Any]]:
        for proposal_id in proposal_ids:
            proposal = self.get(proposal_id)
            if proposal["risk"] == ProposalRisk.HIGH.value:
                raise TaskManagerError("High risk proposals cannot be batch-applied.")
        return [self.apply(proposal_id, confirmed=confirmed) for proposal_id in proposal_ids]

    def _logseq_marker_preview(self, proposal: Dict[str, Any]):
        payload = proposal["payload"]
        marker = normalize_marker(payload.get("marker") or ("**[待澄清]**" if proposal["proposal_type"] == ProposalType.NEEDS_CLARIFICATION.value else ""))
        file_path, block_uuid, line_start = self._target_location(proposal, payload)
        return self._writer().preview_append_marker_child(file_path, marker, payload.get("content", ""), block_uuid=block_uuid, line_start=line_start)

    def _task_marker_preview(self, proposal: Dict[str, Any]):
        payload = proposal["payload"]
        file_path, block_uuid, line_start = self._target_location(proposal, payload)
        return self._writer().preview_update_task_marker(file_path, payload["new_marker"], block_uuid=block_uuid, line_start=line_start)

    def _target_location(self, proposal: Dict[str, Any], payload: Dict[str, Any]):
        file_path = payload.get("file_path")
        block_uuid = payload.get("block_uuid")
        line_start = payload.get("line_start")
        if proposal.get("target_object_id") and not file_path:
            obj = self.repo.get_object(int(proposal["target_object_id"]))
            file_path = obj.get("file_path")
            block_uuid = block_uuid or obj.get("block_uuid")
            line_start = line_start or obj.get("line_start")
        if not file_path:
            raise ConfigError("Logseq writeback proposals require a target object or file_path.")
        return Path(file_path), block_uuid, line_start

    def _writer(self) -> LogseqWriter:
        if not self.settings or not self.settings.logseq_graph_path:
            raise ConfigError("Logseq graph path is not configured.")
        return LogseqWriter(self.settings.logseq_graph_path)

    def _backup_dir(self) -> Path:
        if not self.settings:
            raise ConfigError("Settings are required for Logseq writeback.")
        return self.settings.write_backup_dir or self.settings.app_dir / "backups"

    def _ensure_write_apply_allowed(self, confirmed: bool) -> None:
        if not self.settings:
            raise ConfigError("Settings are required for Logseq writeback.")
        if self.settings.write_mode not in {"guarded", "agent"}:
            raise ConfigError("Applying Logseq writeback requires write_mode `guarded` or `agent`.")
        if self.settings.write_require_confirm and self.settings.write_mode != "agent" and not confirmed:
            raise ConfigError("Applying writes requires --yes in the current write configuration.")

    def _ensure_previewed(self, proposal_id: int) -> None:
        row = self.conn.execute(
            "SELECT 1 FROM proposal_events WHERE proposal_id=? AND event_type='previewed' ORDER BY id DESC LIMIT 1",
            (proposal_id,),
        ).fetchone()
        if not row:
            raise ConfigError("Logseq writeback requires preview/diff before apply. Run `tm proposal show <id> --preview` first.")

    def _transition(self, proposal_id: int, from_status: str, to_status: str, event: str, actor: str) -> None:
        if event == "accepted":
            cur = self.conn.execute(
                "UPDATE proposals SET status=?, updated_at=CURRENT_TIMESTAMP, accepted_at=CURRENT_TIMESTAMP WHERE id=? AND status IN ('suggested', 'edited')",
                (to_status, proposal_id),
            )
            if cur.rowcount == 0:
                raise TaskManagerError(f"Proposal {proposal_id} is not suggested or edited.")
            self._event(proposal_id, event, actor, {})
            return
        cur = self.conn.execute(
            f"UPDATE proposals SET status=?, updated_at=CURRENT_TIMESTAMP, {event}_at=CURRENT_TIMESTAMP WHERE id=? AND status=?",
            (to_status, proposal_id, from_status),
        )
        if cur.rowcount == 0:
            raise TaskManagerError(f"Proposal {proposal_id} is not {from_status}.")
        self._event(proposal_id, event, actor, {})

    def _event(self, proposal_id: int, event_type: str, actor: str, details: Dict[str, Any]) -> None:
        self.conn.execute(
            "INSERT INTO proposal_events(proposal_id, event_type, actor, details_json) VALUES (?, ?, ?, ?)",
            (proposal_id, event_type, actor, json.dumps(details, ensure_ascii=False, sort_keys=True)),
        )

    def _row(self, row) -> Dict[str, Any]:
        data = dict(row)
        data["payload"] = json.loads(data.pop("payload_json") or "{}")
        data["metadata"] = json.loads(data.pop("metadata_json") or "{}")
        if data.get("applied_record_json"):
            data["applied_record"] = json.loads(data.pop("applied_record_json") or "{}")
        else:
            data.pop("applied_record_json", None)
            data["applied_record"] = None
        if data.get("rollback_record_json"):
            data["rollback_record"] = json.loads(data.pop("rollback_record_json") or "{}")
        else:
            data.pop("rollback_record_json", None)
            data["rollback_record"] = None
        return data

    def _event_row(self, row) -> Dict[str, Any]:
        data = dict(row)
        data["details"] = json.loads(data.pop("details_json") or "{}")
        return data


def normalize_marker(marker: str) -> str:
    marker = marker.strip()
    if marker.startswith("**["):
        return marker
    if marker.startswith("[") and marker.endswith("]"):
        return f"**{marker}**"
    return f"**[{marker}]**"


def classify_risk(proposal_type: str, payload: Optional[Dict[str, Any]] = None) -> str:
    if proposal_type in HIGH_RISK:
        return ProposalRisk.HIGH.value
    if proposal_type in MEDIUM_RISK:
        return ProposalRisk.MEDIUM.value
    if proposal_type in LOW_RISK:
        return ProposalRisk.LOW.value
    return ProposalRisk.MEDIUM.value
