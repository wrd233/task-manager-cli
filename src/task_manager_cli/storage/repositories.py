import json
import sqlite3
from typing import Any, Dict, Iterable, List, Optional

from task_manager_cli.core.models import ActionObject, Location, Relation, SourceRecord


def _json(data: Optional[Dict[str, Any]]) -> str:
    return json.dumps(data or {}, ensure_ascii=False, sort_keys=True)


def _json_list(data: Optional[List[str]]) -> str:
    return json.dumps(data or [], ensure_ascii=False)


def _load(row: sqlite3.Row) -> Dict[str, Any]:
    data = dict(row)
    for key in list(data):
        if key.endswith("_json"):
            data[key[:-5]] = json.loads(data.pop(key) or "{}")
    if "block_path_json" in data:
        data["block_path"] = json.loads(data.pop("block_path_json") or "[]")
    return data


class Repository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def upsert_location(self, loc: Location) -> int:
        self.conn.execute(
            """
            INSERT INTO locations(
                source_type, source_item_id, graph_path, file_path, page_name, journal_date,
                block_uuid, line_start, line_end, block_path_json, external_url, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_type, source_item_id) DO UPDATE SET
                graph_path=excluded.graph_path,
                file_path=excluded.file_path,
                page_name=excluded.page_name,
                journal_date=excluded.journal_date,
                block_uuid=excluded.block_uuid,
                line_start=excluded.line_start,
                line_end=excluded.line_end,
                block_path_json=excluded.block_path_json,
                external_url=excluded.external_url,
                metadata_json=excluded.metadata_json,
                updated_at=CURRENT_TIMESTAMP
            """,
            (
                loc.source_type,
                loc.source_item_id,
                loc.graph_path,
                loc.file_path,
                loc.page_name,
                loc.journal_date,
                loc.block_uuid,
                loc.line_start,
                loc.line_end,
                _json_list(loc.block_path),
                loc.external_url,
                _json(loc.metadata),
            ),
        )
        return int(self.conn.execute("SELECT id FROM locations WHERE source_type=? AND source_item_id=?", (loc.source_type, loc.source_item_id)).fetchone()["id"])

    def upsert_record(self, rec: SourceRecord) -> int:
        location_id = self.upsert_location(rec.location)
        parent_id = None
        if rec.parent_source_item_id:
            row = self.conn.execute(
                "SELECT id FROM source_records WHERE source_type=? AND source_item_id=?",
                (rec.source_type, rec.parent_source_item_id),
            ).fetchone()
            parent_id = int(row["id"]) if row else None
        self.conn.execute(
            """
            INSERT INTO source_records(
                source_type, source_item_id, raw_text, normalized_text, record_type,
                parent_source_item_id, parent_record_id, location_id, source_created_at,
                source_updated_at, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_type, source_item_id) DO UPDATE SET
                raw_text=excluded.raw_text,
                normalized_text=excluded.normalized_text,
                record_type=excluded.record_type,
                parent_source_item_id=excluded.parent_source_item_id,
                parent_record_id=excluded.parent_record_id,
                location_id=excluded.location_id,
                observed_at=CURRENT_TIMESTAMP,
                source_created_at=excluded.source_created_at,
                source_updated_at=excluded.source_updated_at,
                metadata_json=excluded.metadata_json,
                updated_at=CURRENT_TIMESTAMP
            """,
            (
                rec.source_type,
                rec.source_item_id,
                rec.raw_text,
                rec.normalized_text,
                rec.record_type,
                rec.parent_source_item_id,
                parent_id,
                location_id,
                rec.source_created_at,
                rec.source_updated_at,
                _json(rec.metadata),
            ),
        )
        return int(self.conn.execute("SELECT id FROM source_records WHERE source_type=? AND source_item_id=?", (rec.source_type, rec.source_item_id)).fetchone()["id"])

    def upsert_object(self, obj: ActionObject, location: Location) -> int:
        location_id = self.upsert_location(location)
        existing = self._find_existing_object_for_location(obj, location)
        if existing and existing["source_item_id"] != obj.source_item_id:
            target = self.conn.execute(
                "SELECT id FROM objects WHERE canonical_source=? AND source_item_id=?",
                (obj.source_type, obj.source_item_id),
            ).fetchone()
            if target and int(target["id"]) != int(existing["id"]):
                self.conn.execute(
                    """
                    UPDATE objects SET
                        object_type=?,
                        title=?,
                        status=?,
                        canonical_location_id=?,
                        confidence=?,
                        created_at=COALESCE(created_at, ?),
                        last_seen_at=CURRENT_TIMESTAMP,
                        metadata_json=?
                    WHERE id=?
                    """,
                    (
                        obj.object_type,
                        obj.title,
                        obj.status,
                        location_id,
                        obj.confidence,
                        obj.created_at,
                        _json(obj.metadata),
                        int(target["id"]),
                    ),
                )
                return int(target["id"])
            self.conn.execute(
                """
                UPDATE objects SET
                    object_type=?,
                    title=?,
                    status=?,
                    source_item_id=?,
                    canonical_location_id=?,
                    confidence=?,
                    created_at=COALESCE(created_at, ?),
                    last_seen_at=CURRENT_TIMESTAMP,
                    metadata_json=?
                WHERE id=?
                """,
                (
                    obj.object_type,
                    obj.title,
                    obj.status,
                    obj.source_item_id,
                    location_id,
                    obj.confidence,
                    obj.created_at,
                    _json(obj.metadata),
                    int(existing["id"]),
                ),
            )
            return int(existing["id"])
        self.conn.execute(
            """
            INSERT INTO objects(
                object_type, title, status, canonical_source, source_item_id,
                canonical_location_id, confidence, created_at, created_at_source, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(canonical_source, source_item_id) DO UPDATE SET
                object_type=excluded.object_type,
                title=excluded.title,
                status=excluded.status,
                canonical_location_id=excluded.canonical_location_id,
                confidence=excluded.confidence,
                created_at=COALESCE(objects.created_at, excluded.created_at),
                created_at_source=CASE
                    WHEN objects.created_at IS NULL THEN excluded.created_at_source
                    ELSE objects.created_at_source
                END,
                last_seen_at=CURRENT_TIMESTAMP,
                metadata_json=excluded.metadata_json
            """,
            (
                obj.object_type,
                obj.title,
                obj.status,
                obj.source_type,
                obj.source_item_id,
                location_id,
                obj.confidence,
                obj.created_at,
                obj.created_at_source,
                _json(obj.metadata),
            ),
        )
        return int(self.conn.execute("SELECT id FROM objects WHERE canonical_source=? AND source_item_id=?", (obj.source_type, obj.source_item_id)).fetchone()["id"])

    def _find_existing_object_for_location(self, obj: ActionObject, location: Location) -> Optional[sqlite3.Row]:
        if location.block_uuid:
            row = self.conn.execute(
                """
                SELECT o.*
                FROM objects o
                JOIN locations l ON l.id=o.canonical_location_id
                WHERE o.canonical_source=? AND o.object_type=? AND l.block_uuid=?
                ORDER BY o.last_seen_at DESC, o.id DESC
                LIMIT 1
                """,
                (obj.source_type, obj.object_type, location.block_uuid),
            ).fetchone()
            if row:
                return row
        if location.file_path and location.line_start:
            normalized = obj.title.strip()
            return self.conn.execute(
                """
                SELECT o.*
                FROM objects o
                JOIN locations l ON l.id=o.canonical_location_id
                WHERE o.canonical_source=? AND o.object_type=?
                  AND l.file_path=? AND l.line_start=?
                  AND (o.title=? OR o.source_item_id=?)
                ORDER BY o.last_seen_at DESC, o.id DESC
                LIMIT 1
                """,
                (obj.source_type, obj.object_type, location.file_path, location.line_start, normalized, obj.source_item_id),
            ).fetchone()
        return None

    def update_object_after_writeback(
        self,
        object_id: int,
        *,
        status: Optional[str] = None,
        title: Optional[str] = None,
        dirty_reason: str = "shell_writeback",
    ) -> None:
        row = self.conn.execute("SELECT metadata_json FROM objects WHERE id=?", (object_id,)).fetchone()
        if not row:
            return
        metadata = json.loads(row["metadata_json"] or "{}")
        metadata["index_status"] = "updated_by_shell_writeback"
        metadata["index_dirty_reason"] = dirty_reason
        sets = ["metadata_json=?", "last_seen_at=CURRENT_TIMESTAMP"]
        params: List[Any] = [_json(metadata)]
        if status is not None:
            sets.append("status=?")
            params.append(status)
        if title is not None:
            sets.append("title=?")
            params.append(title)
        params.append(object_id)
        self.conn.execute(f"UPDATE objects SET {', '.join(sets)} WHERE id=?", params)

    def duplicate_objects_for_source_location(self, object_id: int) -> List[Dict[str, Any]]:
        obj = self.get_object(object_id)
        if not obj or not obj.get("file_path") or not obj.get("line_start"):
            return []
        rows = self.conn.execute(
            """
            SELECT o.*, l.file_path, l.page_name, l.journal_date, l.line_start
            FROM objects o
            JOIN locations l ON l.id=o.canonical_location_id
            WHERE o.id != ? AND o.object_type=? AND l.file_path=? AND l.line_start=?
            ORDER BY o.last_seen_at DESC, o.id DESC
            LIMIT 20
            """,
            (object_id, obj.get("object_type"), obj.get("file_path"), obj.get("line_start")),
        ).fetchall()
        return [_load(row) for row in rows]

    def link_object_record(self, object_id: int, record_id: int, role: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        self.conn.execute(
            """
            INSERT INTO object_record_links(object_id, record_id, role, metadata_json)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(object_id, record_id, role) DO UPDATE SET metadata_json=excluded.metadata_json
            """,
            (object_id, record_id, role, _json(metadata)),
        )

    def upsert_relation_by_source(self, rel: Relation) -> None:
        from_row = self.conn.execute(
            "SELECT id FROM objects WHERE canonical_source='logseq' AND source_item_id=?",
            (rel.from_source_item_id,),
        ).fetchone()
        to_row = self.conn.execute(
            "SELECT id FROM objects WHERE canonical_source='logseq' AND source_item_id=?",
            (rel.to_source_item_id,),
        ).fetchone()
        if not from_row or not to_row:
            return
        self.conn.execute(
            """
            INSERT INTO relations(from_object_id, to_object_id, relation_type, confidence, metadata_json)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(from_object_id, to_object_id, relation_type) DO UPDATE SET
                confidence=excluded.confidence,
                metadata_json=excluded.metadata_json
            """,
            (int(from_row["id"]), int(to_row["id"]), rel.relation_type, rel.confidence, _json(rel.metadata)),
        )

    def create_sync_run(self, adapter: str, graph_path: Optional[str], dry_run: bool) -> int:
        cur = self.conn.execute(
            "INSERT INTO sync_runs(adapter, graph_path, dry_run) VALUES (?, ?, ?)",
            (adapter, graph_path, 1 if dry_run else 0),
        )
        return int(cur.lastrowid)

    def finish_sync_run(self, run_id: int, status: str, stats: Dict[str, Any]) -> None:
        self.conn.execute(
            """
            UPDATE sync_runs SET finished_at=CURRENT_TIMESTAMP, status=?, files_scanned=?,
                records_seen=?, objects_seen=?, warnings_seen=?, errors_seen=?, metadata_json=?
            WHERE id=?
            """,
            (
                status,
                int(stats.get("files_scanned", 0)),
                int(stats.get("records_seen", 0)),
                int(stats.get("objects_seen", 0)),
                int(stats.get("warnings_seen", 0)),
                int(stats.get("errors_seen", 0)),
                _json(stats.get("metadata", {})),
                run_id,
            ),
        )

    def list_objects(self, object_type: Optional[str] = None, status: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        where = []
        params: List[Any] = []
        if object_type:
            where.append("o.object_type=?")
            params.append(object_type)
        if status:
            where.append("o.status=?")
            params.append(status)
        sql = """
            SELECT o.*, l.file_path, l.page_name, l.journal_date, l.block_uuid, l.line_start
            FROM objects o
            LEFT JOIN locations l ON l.id=o.canonical_location_id
        """
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY COALESCE(o.created_at, o.first_seen_at) DESC, o.id DESC LIMIT ?"
        params.append(limit)
        return [_load(row) for row in self.conn.execute(sql, params).fetchall()]

    def get_object(self, object_id: int) -> Optional[Dict[str, Any]]:
        row = self.conn.execute(
            """
            SELECT o.*, l.source_type AS location_source_type, l.source_item_id AS location_source_item_id,
                   l.graph_path, l.file_path, l.page_name, l.journal_date, l.block_uuid,
                   l.line_start, l.line_end, l.block_path_json, l.external_url,
                   l.metadata_json AS location_metadata_json
            FROM objects o
            LEFT JOIN locations l ON l.id=o.canonical_location_id
            WHERE o.id=?
            """,
            (object_id,),
        ).fetchone()
        return _load(row) if row else None

    def resolve_object_id(self, ref: str) -> Optional[int]:
        if ref.isdigit():
            row = self.conn.execute("SELECT id FROM objects WHERE id=?", (int(ref),)).fetchone()
            return int(row["id"]) if row else None
        row = self.conn.execute(
            "SELECT id FROM objects WHERE source_item_id=? OR title=? ORDER BY id LIMIT 1",
            (ref, ref),
        ).fetchone()
        return int(row["id"]) if row else None

    def resolve_record_id(self, ref: str) -> Optional[int]:
        if ref.isdigit():
            row = self.conn.execute("SELECT id FROM source_records WHERE id=?", (int(ref),)).fetchone()
            if row:
                return int(row["id"])
        row = self.conn.execute(
            "SELECT id FROM source_records WHERE source_item_id=? ORDER BY id LIMIT 1",
            (ref,),
        ).fetchone()
        return int(row["id"]) if row else None

    def definition_record_for_object(self, object_id: int) -> Optional[Dict[str, Any]]:
        row = self.conn.execute(
            """
            SELECT r.*, l.file_path, l.page_name, l.journal_date, l.block_uuid,
                   l.line_start, l.line_end, l.block_path_json
            FROM object_record_links orl
            JOIN source_records r ON r.id=orl.record_id
            LEFT JOIN locations l ON l.id=r.location_id
            WHERE orl.object_id=? AND orl.role='definition'
            ORDER BY r.id LIMIT 1
            """,
            (object_id,),
        ).fetchone()
        return _load(row) if row else None

    def records_for_object(self, object_id: int, limit: int = 50) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT r.*, orl.role, l.file_path, l.page_name, l.journal_date, l.block_uuid,
                   l.line_start, l.line_end, l.block_path_json
            FROM object_record_links orl
            JOIN source_records r ON r.id=orl.record_id
            LEFT JOIN locations l ON l.id=r.location_id
            WHERE orl.object_id=?
            ORDER BY l.file_path, l.line_start, r.id
            LIMIT ?
            """,
            (object_id, limit),
        ).fetchall()
        return [_load(row) for row in rows]

    def relations_for_object(self, object_id: int) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT r.id, r.relation_type, r.confidence, r.metadata_json,
                   fo.id AS from_id, fo.title AS from_title, fo.object_type AS from_type,
                   too.id AS to_id, too.title AS to_title, too.object_type AS to_type
            FROM relations r
            JOIN objects fo ON fo.id=r.from_object_id
            JOIN objects too ON too.id=r.to_object_id
            WHERE r.from_object_id=? OR r.to_object_id=?
            ORDER BY r.id
            """,
            (object_id, object_id),
        ).fetchall()
        return [_load(row) for row in rows]

    def add_annotation(self, target_object_id: Optional[int], target_record_id: Optional[int], author: str, annotation_type: str, content: str, metadata: Optional[Dict[str, Any]] = None) -> int:
        cur = self.conn.execute(
            """
            INSERT INTO annotations(target_object_id, target_record_id, author, annotation_type, content, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (target_object_id, target_record_id, author, annotation_type, content, _json(metadata)),
        )
        return int(cur.lastrowid)

    def list_annotations(self, target_object_id: Optional[int] = None, target_record_id: Optional[int] = None, status: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        where = []
        params: List[Any] = []
        if target_object_id is not None:
            where.append("a.target_object_id=?")
            params.append(target_object_id)
        if target_record_id is not None:
            where.append("a.target_record_id=?")
            params.append(target_record_id)
        if status:
            where.append("a.status=?")
            params.append(status)
        sql = "SELECT a.*, o.title AS object_title FROM annotations a LEFT JOIN objects o ON o.id=a.target_object_id"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY a.created_at DESC, a.id DESC LIMIT ?"
        params.append(limit)
        return [_load(row) for row in self.conn.execute(sql, params).fetchall()]

    def object_activity(self, object_id: int) -> Dict[str, Any]:
        row = self.conn.execute(
            """
            SELECT
              COUNT(DISTINCT CASE WHEN orl.role != 'definition' THEN orl.record_id END) AS child_record_count,
              COUNT(DISTINCT CASE WHEN orl.role = 'journal_exposure' THEN orl.record_id END) AS journal_exposure_count,
              MAX(COALESCE(r.source_updated_at, r.observed_at)) AS record_activity_at
            FROM object_record_links orl
            JOIN source_records r ON r.id=orl.record_id
            WHERE orl.object_id=?
            """,
            (object_id,),
        ).fetchone()
        annotation_row = self.conn.execute(
            "SELECT COUNT(*) AS annotation_count, MAX(updated_at) AS annotation_activity_at FROM annotations WHERE target_object_id=?",
            (object_id,),
        ).fetchone()
        recent_exposures = self.conn.execute(
            """
            SELECT r.id, r.raw_text, l.file_path, l.page_name, l.journal_date, l.line_start
            FROM object_record_links orl
            JOIN source_records r ON r.id=orl.record_id
            LEFT JOIN locations l ON l.id=r.location_id
            WHERE orl.object_id=? AND orl.role='journal_exposure'
            ORDER BY l.journal_date DESC, l.line_start DESC
            LIMIT 5
            """,
            (object_id,),
        ).fetchall()
        activity_sources = []
        if row and row["record_activity_at"]:
            activity_sources.append("records")
        if row and row["journal_exposure_count"]:
            activity_sources.append("journal_exposure")
        if annotation_row and annotation_row["annotation_count"]:
            activity_sources.append("annotation")
        candidates = [
            row["record_activity_at"] if row else None,
            annotation_row["annotation_activity_at"] if annotation_row else None,
        ]
        return {
            "last_activity_at": max([item for item in candidates if item], default=None),
            "activity_sources": activity_sources,
            "recent_exposures": [_load(item) for item in recent_exposures],
            "journal_exposure_count": int(row["journal_exposure_count"] or 0) if row else 0,
            "child_record_count": int(row["child_record_count"] or 0) if row else 0,
            "annotation_count": int(annotation_row["annotation_count"] or 0) if annotation_row else 0,
        }

    def quality_metrics(self) -> Dict[str, int]:
        stats = self.stats()
        relation_count = int(self.conn.execute("SELECT COUNT(*) AS c FROM relations").fetchone()["c"])
        unlinked = int(
            self.conn.execute(
                """
                SELECT COUNT(*) AS c FROM objects o
                WHERE o.object_type IN ('task', 'idea')
                  AND NOT EXISTS (
                    SELECT 1 FROM relations r
                    WHERE r.from_object_id=o.id AND r.relation_type='belongs_to'
                  )
                """
            ).fetchone()["c"]
        )
        suspicious = int(
            self.conn.execute(
                """
                SELECT COUNT(*) AS c FROM objects o
                WHERE o.object_type='idea'
                  AND (
                    o.title LIKE ']%' OR LENGTH(TRIM(o.title)) < 2 OR
                    o.metadata_json LIKE '%suspicious_idea_reason%'
                  )
                """
            ).fetchone()["c"]
        )
        mismatches = int(
            self.conn.execute(
                """
                SELECT COUNT(*) AS c
                FROM objects o
                JOIN locations cl ON cl.id=o.canonical_location_id
                JOIN object_record_links orl ON orl.object_id=o.id AND orl.role='definition'
                JOIN source_records r ON r.id=orl.record_id
                JOIN locations rl ON rl.id=r.location_id
                WHERE COALESCE(cl.file_path, '') != COALESCE(rl.file_path, '')
                   OR COALESCE(cl.line_start, -1) != COALESCE(rl.line_start, -1)
                   OR COALESCE(cl.source_item_id, '') != COALESCE(rl.source_item_id, '')
                """
            ).fetchone()["c"]
        )
        missing_definition = int(
            self.conn.execute(
                """
                SELECT COUNT(*) AS c FROM objects o
                WHERE NOT EXISTS (
                  SELECT 1 FROM object_record_links orl
                  WHERE orl.object_id=o.id AND orl.role='definition'
                )
                """
            ).fetchone()["c"]
        )
        return {
            **stats,
            "relations": relation_count,
            "unlinked_tasks_ideas": unlinked,
            "suspicious_ideas": suspicious,
            "source_location_mismatches": mismatches,
            "missing_definition_records": missing_definition,
        }

    def update_annotation_status(self, annotation_id: int, status: str) -> bool:
        cur = self.conn.execute(
            "UPDATE annotations SET status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (status, annotation_id),
        )
        return cur.rowcount > 0

    def list_sync_runs(self, limit: int = 20) -> List[Dict[str, Any]]:
        rows = self.conn.execute("SELECT * FROM sync_runs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [_load(row) for row in rows]

    def stats(self) -> Dict[str, int]:
        keys = {
            "objects": "objects",
            "projects": "objects WHERE object_type='project'",
            "tasks": "objects WHERE object_type='task'",
            "ideas": "objects WHERE object_type='idea'",
            "mini_projects": "objects WHERE object_type='mini_project'",
            "records": "source_records",
            "annotations": "annotations",
            "sync_runs": "sync_runs",
        }
        return {key: int(self.conn.execute(f"SELECT COUNT(*) AS c FROM {sql}").fetchone()["c"]) for key, sql in keys.items()}
