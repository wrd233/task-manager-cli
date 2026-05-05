import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from task_manager_cli.output.formatters import to_json
from task_manager_cli.privacy.redactor import Redactor
from task_manager_cli.storage.repositories import Repository


class SnapshotExporter:
    def __init__(self, conn, sensitive_patterns=None):
        self.conn = conn
        self.repo = Repository(conn)
        self.redactor = Redactor(sensitive_patterns or [])

    def export(self, output_dir: Path, redact: bool = True, chunk_size: int = 500) -> Dict[str, Any]:
        output_dir = Path(output_dir).expanduser()
        output_dir.mkdir(parents=True, exist_ok=True)

        stats = self.repo.stats()
        projects = self.repo.list_objects("project", limit=100000)
        tasks = self.repo.list_objects("task", limit=100000)
        ideas = self.repo.list_objects("idea", limit=100000)

        paths = []
        paths.append(self._write(output_dir / "00_INDEX.md", self._index_markdown(stats, projects, tasks, ideas, redact)))
        paths.append(self._write(output_dir / "01_projects_full.md", self._objects_markdown("Projects", projects, redact=redact)))
        paths.extend(self._write_chunks(output_dir, "02_tasks_full", "Tasks", tasks, chunk_size, redact))
        paths.extend(self._write_chunks(output_dir, "03_ideas_full", "Ideas", ideas, chunk_size, redact))
        paths.append(self._write(output_dir / "04_relations_full.md", self._relations_markdown()))
        paths.append(self._write(output_dir / "05_annotations_full.md", self._annotations_markdown()))
        paths.append(self._write(output_dir / "06_sync_runs.md", self._sync_runs_markdown()))
        paths.append(self._write(output_dir / "07_project_dossiers_full.md", self._project_dossiers_markdown(projects, redact=redact)))
        paths.append(self._write(output_dir / "08_unlinked_objects.md", self._unlinked_objects_markdown(redact=redact)))
        paths.append(self._write(output_dir / "09_source_inventory.md", self._source_inventory_markdown()))

        paths.append(self._write_jsonl(output_dir / "objects_full.jsonl", self._object_context_rows(projects + tasks + ideas, redact=redact)))
        paths.append(self._write_jsonl(output_dir / "records_full.jsonl", self._all_records(redact=redact)))
        paths.append(self._write_jsonl(output_dir / "relations_full.jsonl", self._all_relations()))
        paths.append(self._write(output_dir / "summary.json", to_json({"stats": stats, "redaction": {"enabled": redact}, "generated_at": self._now()})))

        return {
            "output_dir": str(output_dir),
            "files": [str(path) for path in paths],
            "stats": stats,
            "redaction": {"enabled": redact},
        }

    def _now(self) -> str:
        return datetime.now().replace(microsecond=0).isoformat()

    def _write(self, path: Path, text: str) -> Path:
        path.write_text(text, encoding="utf-8")
        return path

    def _write_chunks(self, output_dir: Path, stem: str, title: str, objects: List[Dict[str, Any]], chunk_size: int, redact: bool) -> List[Path]:
        paths = []
        for index in range(0, len(objects), chunk_size):
            chunk = objects[index : index + chunk_size]
            suffix = index // chunk_size + 1
            paths.append(self._write(output_dir / f"{stem}_part{suffix:02d}.md", self._objects_markdown(f"{title} Part {suffix}", chunk, redact=redact)))
        return paths

    def _write_jsonl(self, path: Path, rows: Iterable[Dict[str, Any]]) -> Path:
        with path.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
        return path

    def _index_markdown(self, stats: Dict[str, int], projects: List[Dict[str, Any]], tasks: List[Dict[str, Any]], ideas: List[Dict[str, Any]], redact: bool) -> str:
        lines = [
            "# Current Action System Snapshot",
            "",
            f"- Generated at: `{self._now()}`",
            f"- Redaction enabled: `{redact}`",
            f"- Objects: `{stats['objects']}`",
            f"- Projects: `{stats['projects']}`",
            f"- Tasks: `{stats['tasks']}`",
            f"- Ideas: `{stats['ideas']}`",
            f"- Source records: `{stats['records']}`",
            f"- Relations: `{self._relation_count()}`",
            f"- Annotations: `{stats['annotations']}`",
            "",
            "## Files",
            "",
            "- `01_projects_full.md`: all project objects, source locations, metadata, linked records, relations, annotations.",
            "- `02_tasks_full_part*.md`: all task objects split into chunks.",
            "- `03_ideas_full_part*.md`: all idea objects split into chunks.",
            "- `04_relations_full.md`: all object relations.",
            "- `05_annotations_full.md`: annotation store.",
            "- `06_sync_runs.md`: sync history.",
            "- `07_project_dossiers_full.md`: project-by-project dossiers with directly related tasks and ideas expanded.",
            "- `08_unlinked_objects.md`: tasks and ideas without object-level project/task relation.",
            "- `09_source_inventory.md`: source record distribution by page and journal.",
            "- `objects_full.jsonl`: one full context JSON object per ActionObject.",
            "- `records_full.jsonl`: all source records with locations.",
            "- `relations_full.jsonl`: all relation rows.",
            "- `summary.json`: machine-readable summary.",
            "",
            "## Status Breakdown",
            "",
            self._status_breakdown_markdown(tasks),
            "",
            "## Recent Projects",
            "",
            self._compact_object_list(projects[:30]),
            "",
            "## Recent Tasks",
            "",
            self._compact_object_list(tasks[:50]),
            "",
            "## Recent Ideas",
            "",
            self._compact_object_list(ideas[:50]),
            "",
            "## Notes",
            "",
            "This export is generated from the CLI SQLite index. Logseq files were read-only during sync.",
            "Sensitive-looking content and records marked private are redacted by default.",
        ]
        return "\n".join(lines) + "\n"

    def _objects_markdown(self, title: str, objects: List[Dict[str, Any]], redact: bool) -> str:
        lines = [f"# {title}", "", f"Count: `{len(objects)}`", ""]
        for obj in objects:
            lines.extend(self._object_markdown(obj, redact=redact))
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"

    def _object_markdown(self, obj: Dict[str, Any], redact: bool) -> List[str]:
        object_id = int(obj["id"])
        lines = [
            f"## #{object_id} {obj.get('object_type')} | {self._clean(obj.get('title', ''), redact)}",
            "",
            f"- Status: `{obj.get('status')}`",
            f"- Confidence: `{obj.get('confidence')}`",
            f"- Created at: `{obj.get('created_at')}` via `{obj.get('created_at_source')}`",
            f"- First seen: `{obj.get('first_seen_at')}`",
            f"- Last seen: `{obj.get('last_seen_at')}`",
            f"- Source: `{obj.get('canonical_source')}` / `{obj.get('source_item_id')}`",
            f"- Location: `{obj.get('file_path')}:{obj.get('line_start') or ''}`",
            f"- Page: `{obj.get('page_name')}`",
            f"- Journal date: `{obj.get('journal_date')}`",
            f"- Block uuid: `{obj.get('block_uuid')}`",
            f"- Metadata: `{json.dumps(obj.get('metadata', {}), ensure_ascii=False)}`",
        ]
        relations = self.repo.relations_for_object(object_id)
        if relations:
            lines.extend(["", "### Relations"])
            for rel in relations:
                lines.append(
                    f"- `{rel.get('relation_type')}`: #{rel.get('from_id')} {self._clean(rel.get('from_title'), redact)} -> "
                    f"#{rel.get('to_id')} {self._clean(rel.get('to_title'), redact)} "
                    f"(confidence `{rel.get('confidence')}`)"
                )
        records = self.repo.records_for_object(object_id, limit=100000)
        if records:
            lines.extend(["", "### Linked Records"])
            for record in records:
                private = bool((record.get("metadata") or {}).get("private"))
                raw = self._clean(record.get("raw_text", ""), redact, private=private)
                raw = raw.strip().replace("\n", "\n  ")
                lines.append(f"- `{record.get('role')}` `{record.get('file_path')}:{record.get('line_start') or ''}`")
                lines.append(f"  {raw}")
        annotations = self.repo.list_annotations(target_object_id=object_id, limit=100000)
        if annotations:
            lines.extend(["", "### Annotations"])
            for ann in annotations:
                lines.append(f"- #{ann.get('id')} [{ann.get('status')}] `{ann.get('annotation_type')}` {self._clean(ann.get('content', ''), redact)}")
        return lines

    def _relations_markdown(self) -> str:
        rows = list(self._all_relations())
        lines = ["# Relations", "", f"Count: `{len(rows)}`", ""]
        for row in rows:
            lines.append(
                f"- #{row.get('id')} `{row.get('relation_type')}` "
                f"#{row.get('from_id')} {row.get('from_title')} -> #{row.get('to_id')} {row.get('to_title')} "
                f"(confidence `{row.get('confidence')}`)"
            )
        return "\n".join(lines) + "\n"

    def _annotations_markdown(self) -> str:
        rows = self.repo.list_annotations(limit=100000)
        lines = ["# Annotations", "", f"Count: `{len(rows)}`", ""]
        for row in rows:
            lines.append(f"- #{row.get('id')} [{row.get('status')}] `{row.get('annotation_type')}` target=#{row.get('target_object_id')} author={row.get('author')}: {row.get('content')}")
        return "\n".join(lines) + "\n"

    def _sync_runs_markdown(self) -> str:
        rows = self.repo.list_sync_runs(limit=100000)
        lines = ["# Sync Runs", "", f"Count: `{len(rows)}`", ""]
        for row in rows:
            lines.append(
                f"- #{row.get('id')} `{row.get('adapter')}` `{row.get('status')}` "
                f"started `{row.get('started_at')}` finished `{row.get('finished_at')}` "
                f"files `{row.get('files_scanned')}` objects `{row.get('objects_seen')}` records `{row.get('records_seen')}`"
            )
        return "\n".join(lines) + "\n"

    def _project_dossiers_markdown(self, projects: List[Dict[str, Any]], redact: bool) -> str:
        lines = ["# Project Dossiers", "", f"Count: `{len(projects)}`", ""]
        for project in projects:
            project_id = int(project["id"])
            lines.extend(self._object_markdown(project, redact=redact))
            children = self._children_for_project(project_id)
            if children:
                lines.extend(["", "### Expanded Related Tasks And Ideas", ""])
                for child in children:
                    lines.extend(self._object_markdown(child, redact=redact))
                    lines.append("")
            else:
                lines.extend(["", "### Expanded Related Tasks And Ideas", "", "_No direct belongs_to children indexed._", ""])
        return "\n".join(lines).rstrip() + "\n"

    def _children_for_project(self, project_id: int) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT o.*, l.file_path, l.page_name, l.journal_date, l.block_uuid, l.line_start
            FROM relations r
            JOIN objects o ON o.id=r.from_object_id
            LEFT JOIN locations l ON l.id=o.canonical_location_id
            WHERE r.to_object_id=? AND r.relation_type='belongs_to'
            ORDER BY o.object_type, COALESCE(o.created_at, o.first_seen_at), o.id
            """,
            (project_id,),
        ).fetchall()
        children = []
        for row in rows:
            data = dict(row)
            data["metadata"] = json.loads(data.pop("metadata_json") or "{}")
            children.append(data)
        return children

    def _unlinked_objects_markdown(self, redact: bool) -> str:
        rows = self.conn.execute(
            """
            SELECT o.*, l.file_path, l.page_name, l.journal_date, l.block_uuid, l.line_start
            FROM objects o
            LEFT JOIN locations l ON l.id=o.canonical_location_id
            WHERE o.object_type IN ('task', 'idea')
              AND NOT EXISTS (
                SELECT 1 FROM relations r
                WHERE r.from_object_id=o.id AND r.relation_type='belongs_to'
              )
            ORDER BY o.object_type, COALESCE(o.created_at, o.first_seen_at), o.id
            """
        ).fetchall()
        objects = []
        for row in rows:
            data = dict(row)
            data["metadata"] = json.loads(data.pop("metadata_json") or "{}")
            objects.append(data)
        lines = ["# Unlinked Tasks And Ideas", "", f"Count: `{len(objects)}`", ""]
        for obj in objects:
            lines.extend(self._object_markdown(obj, redact=redact))
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"

    def _source_inventory_markdown(self) -> str:
        by_page = self.conn.execute(
            """
            SELECT l.page_name, l.journal_date, COUNT(*) AS records
            FROM source_records r
            LEFT JOIN locations l ON l.id=r.location_id
            GROUP BY l.page_name, l.journal_date
            ORDER BY records DESC, l.page_name
            LIMIT 1000
            """
        ).fetchall()
        by_type = self.conn.execute(
            "SELECT record_type, COUNT(*) AS records FROM source_records GROUP BY record_type ORDER BY records DESC"
        ).fetchall()
        lines = ["# Source Inventory", "", "## By Record Type", ""]
        for row in by_type:
            lines.append(f"- `{row['record_type']}`: `{row['records']}`")
        lines.extend(["", "## Top Pages/Journals By Indexed Records", ""])
        for row in by_page:
            label = row["page_name"] or row["journal_date"] or "unknown"
            journal = f" journal `{row['journal_date']}`" if row["journal_date"] else ""
            lines.append(f"- `{label}`{journal}: `{row['records']}` records")
        return "\n".join(lines) + "\n"

    def _object_context_rows(self, objects: List[Dict[str, Any]], redact: bool) -> Iterable[Dict[str, Any]]:
        for obj in objects:
            object_id = int(obj["id"])
            records = []
            for record in self.repo.records_for_object(object_id, limit=100000):
                private = bool((record.get("metadata") or {}).get("private"))
                records.append(
                    {
                        **record,
                        "raw_text": self._clean(record.get("raw_text", ""), redact, private=private),
                        "normalized_text": self._clean(record.get("normalized_text", ""), redact, private=private),
                    }
                )
            yield {
                "object": obj,
                "records": records,
                "relations": self.repo.relations_for_object(object_id),
                "annotations": self.repo.list_annotations(target_object_id=object_id, limit=100000),
            }

    def _all_records(self, redact: bool) -> Iterable[Dict[str, Any]]:
        cur = self.conn.execute(
            """
            SELECT r.*, l.file_path, l.page_name, l.journal_date, l.block_uuid, l.line_start,
                   l.line_end, l.block_path_json
            FROM source_records r
            LEFT JOIN locations l ON l.id=r.location_id
            ORDER BY r.id
            """
        )
        for row in cur:
            data = dict(row)
            metadata = json.loads(data.pop("metadata_json") or "{}")
            private = bool(metadata.get("private"))
            data["metadata"] = metadata
            data["block_path"] = json.loads(data.pop("block_path_json") or "[]")
            data["raw_text"] = self._clean(data.get("raw_text", ""), redact, private=private)
            data["normalized_text"] = self._clean(data.get("normalized_text", ""), redact, private=private)
            yield data

    def _all_relations(self) -> Iterable[Dict[str, Any]]:
        cur = self.conn.execute(
            """
            SELECT r.id, r.relation_type, r.confidence, r.metadata_json,
                   fo.id AS from_id, fo.title AS from_title, fo.object_type AS from_type,
                   too.id AS to_id, too.title AS to_title, too.object_type AS to_type
            FROM relations r
            JOIN objects fo ON fo.id=r.from_object_id
            JOIN objects too ON too.id=r.to_object_id
            ORDER BY r.id
            """
        )
        for row in cur:
            data = dict(row)
            data["metadata"] = json.loads(data.pop("metadata_json") or "{}")
            yield data

    def _relation_count(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) AS c FROM relations").fetchone()["c"])

    def _status_breakdown_markdown(self, tasks: List[Dict[str, Any]]) -> str:
        counts: Dict[str, int] = {}
        for task in tasks:
            status = task.get("status") or "unknown"
            counts[status] = counts.get(status, 0) + 1
        return "\n".join(f"- `{status}`: `{count}`" for status, count in sorted(counts.items()))

    def _compact_object_list(self, objects: List[Dict[str, Any]]) -> str:
        if not objects:
            return "_None_"
        return "\n".join(
            f"- #{obj.get('id')} `{obj.get('status')}` {obj.get('title')} "
            f"({obj.get('page_name')}:{obj.get('line_start') or ''})"
            for obj in objects
        )

    def _clean(self, text: Optional[str], redact: bool, private: bool = False) -> str:
        if text is None:
            return ""
        if not redact:
            return str(text)
        return self.redactor.redact(str(text), private=private).text
