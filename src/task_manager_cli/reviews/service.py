import json
from typing import Any, Dict, List, Optional

from task_manager_cli.core.errors import NotFoundError, TaskManagerError
from task_manager_cli.storage.repositories import Repository


class ReviewSessionService:
    def __init__(self, conn):
        self.conn = conn
        self.repo = Repository(conn)

    def start(self, review_type: str, item_refs: Optional[List[str]] = None, title: Optional[str] = None, actor: str = "user") -> int:
        scope = {"type": review_type, "item_refs": item_refs or []}
        cur = self.conn.execute(
            "INSERT INTO review_sessions(review_type, status, title, scope_json) VALUES (?, 'open', ?, ?)",
            (review_type, title or f"{review_type} review", json.dumps(scope, ensure_ascii=False, sort_keys=True)),
        )
        review_id = int(cur.lastrowid)
        self._event(review_id, "started", actor, scope)
        for ref in item_refs or []:
            self.add_item(review_id, ref, actor=actor)
        return review_id

    def add_item(self, review_id: int, item_ref: str, role: str = "candidate", actor: str = "user") -> None:
        self._ensure_exists(review_id)
        object_id = self.repo.resolve_object_id(item_ref)
        record_id = None if object_id else self.repo.resolve_record_id(item_ref)
        self.conn.execute(
            """
            INSERT INTO review_items(review_session_id, object_id, record_id, item_ref, role)
            VALUES (?, ?, ?, ?, ?)
            """,
            (review_id, object_id, record_id, item_ref, role),
        )
        self._event(review_id, "item_added", actor, {"item_ref": item_ref, "object_id": object_id, "record_id": record_id})

    def attach_proposal(self, review_id: int, proposal_id: int, actor: str = "user") -> None:
        self._ensure_exists(review_id)
        cur = self.conn.execute("UPDATE proposals SET review_session_id=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (review_id, proposal_id))
        if cur.rowcount == 0:
            raise NotFoundError(f"Proposal not found: {proposal_id}")
        self._event(review_id, "proposal_attached", actor, {"proposal_id": proposal_id})

    def list(self, status: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        params: List[Any] = []
        sql = "SELECT * FROM review_sessions"
        if status:
            sql += " WHERE status=?"
            params.append(status)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        return [self._row(row) for row in self.conn.execute(sql, params).fetchall()]

    def show(self, review_id: int) -> Dict[str, Any]:
        row = self.conn.execute("SELECT * FROM review_sessions WHERE id=?", (review_id,)).fetchone()
        if not row:
            raise NotFoundError(f"Review session not found: {review_id}")
        data = self._row(row)
        data["items"] = [self._item_row(item) for item in self.conn.execute("SELECT * FROM review_items WHERE review_session_id=? ORDER BY id", (review_id,)).fetchall()]
        data["proposals"] = [self._proposal_row(item) for item in self.conn.execute("SELECT * FROM proposals WHERE review_session_id=? ORDER BY id", (review_id,)).fetchall()]
        data["events"] = [self._event_row(item) for item in self.conn.execute("SELECT * FROM review_events WHERE review_session_id=? ORDER BY id", (review_id,)).fetchall()]
        return data

    def proposals(self, review_id: int) -> List[Dict[str, Any]]:
        self._ensure_exists(review_id)
        return [self._proposal_row(row) for row in self.conn.execute("SELECT * FROM proposals WHERE review_session_id=? ORDER BY id", (review_id,)).fetchall()]

    def set_status(self, review_id: int, status: str, actor: str = "user") -> None:
        if status not in {"open", "in_progress", "paused", "completed", "cancelled"}:
            raise ValueError(f"Unsupported review status: {status}")
        cur = self.conn.execute(
            "UPDATE review_sessions SET status=?, updated_at=CURRENT_TIMESTAMP, closed_at=CASE WHEN ? IN ('completed','cancelled') THEN CURRENT_TIMESTAMP ELSE closed_at END WHERE id=?",
            (status, status, review_id),
        )
        if cur.rowcount == 0:
            raise NotFoundError(f"Review session not found: {review_id}")
        self._event(review_id, f"status_{status}", actor, {})

    def close(self, review_id: int, cancelled: bool = False, actor: str = "user") -> None:
        self.set_status(review_id, "cancelled" if cancelled else "completed", actor=actor)

    def _ensure_exists(self, review_id: int) -> None:
        if not self.conn.execute("SELECT 1 FROM review_sessions WHERE id=?", (review_id,)).fetchone():
            raise NotFoundError(f"Review session not found: {review_id}")

    def _event(self, review_id: int, event_type: str, actor: str, details: Dict[str, Any]) -> None:
        self.conn.execute(
            "INSERT INTO review_events(review_session_id, event_type, actor, details_json) VALUES (?, ?, ?, ?)",
            (review_id, event_type, actor, json.dumps(details, ensure_ascii=False, sort_keys=True)),
        )

    def _row(self, row) -> Dict[str, Any]:
        data = dict(row)
        data["scope"] = json.loads(data.pop("scope_json") or "{}")
        data["metadata"] = json.loads(data.pop("metadata_json") or "{}")
        return data

    def _item_row(self, row) -> Dict[str, Any]:
        data = dict(row)
        data["metadata"] = json.loads(data.pop("metadata_json") or "{}")
        return data

    def _proposal_row(self, row) -> Dict[str, Any]:
        data = dict(row)
        data["payload"] = json.loads(data.pop("payload_json") or "{}")
        data["metadata"] = json.loads(data.pop("metadata_json") or "{}")
        data.pop("applied_record_json", None)
        data.pop("rollback_record_json", None)
        return data

    def _event_row(self, row) -> Dict[str, Any]:
        data = dict(row)
        data["details"] = json.loads(data.pop("details_json") or "{}")
        return data
