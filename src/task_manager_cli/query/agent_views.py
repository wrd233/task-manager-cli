from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from task_manager_cli.privacy.redactor import Redactor
from task_manager_cli.storage.repositories import Repository


class AgentViewService:
    def __init__(self, conn, sensitive_patterns=None):
        self.conn = conn
        self.repo = Repository(conn)
        self.redactor = Redactor(sensitive_patterns or [])

    def today_context(self, days: int = 14, limit: int = 50, redact: bool = True, include_annotations: bool = True) -> Dict[str, Any]:
        since = self._since(days)
        recent = self._objects_with_recent_journal_records(since, limit, object_types=("task", "idea"))
        active_projects = self._active_projects(since, limit=limit)
        unfinished = [item for item in recent if item["object_type"] == "task" and item.get("status") in {"todo", "doing"}]
        ideas = [item for item in recent if item["object_type"] == "idea"]
        return {
            "view": "today-context",
            "query": {"days": days, "since": since, "limit": limit},
            "recent_objects": self._decorate_objects(recent, redact, include_annotations, record_limit=5),
            "recent_unfinished_tasks": self._decorate_objects(unfinished[:limit], redact, include_annotations, record_limit=5),
            "recent_ideas": self._decorate_objects(ideas[:limit], redact, include_annotations, record_limit=5),
            "active_projects": self._decorate_objects(active_projects, redact, include_annotations, record_limit=5),
            "signals": {
                "doing_count": sum(1 for item in recent if item.get("status") == "doing"),
                "recent_unfinished_count": len(unfinished),
                "recent_idea_count": len(ideas),
            },
            "redaction": {"enabled": redact},
            "notes": "CLI provides evidence only; external agents make priority decisions.",
        }

    def project_context(self, ref: str, days: int = 30, limit: int = 80, redact: bool = True, include_annotations: bool = True) -> Dict[str, Any]:
        project_id = self.repo.resolve_object_id(ref)
        if project_id is None:
            raise KeyError(f"Project not found: {ref}")
        project = self.repo.get_object(project_id)
        children = self._project_children(project_id, limit=100000)
        tasks = [item for item in children if item["object_type"] == "task"]
        ideas = [item for item in children if item["object_type"] == "idea"]
        unfinished = [item for item in tasks if item.get("status") in {"todo", "doing"}]
        done = [item for item in tasks if item.get("status") == "done"]
        since = self._since(days)
        exposures = self._project_exposures(project_id, since, limit=limit)
        signals = self._project_signals(project, tasks, ideas, exposures)
        return {
            "view": "project-context",
            "query": {"project": ref, "days": days, "since": since, "limit": limit},
            "project": self._decorate_object(project, redact, include_annotations, record_limit=20),
            "task_stats": {
                "todo": sum(1 for item in tasks if item.get("status") == "todo"),
                "doing": sum(1 for item in tasks if item.get("status") == "doing"),
                "done": sum(1 for item in tasks if item.get("status") == "done"),
                "total": len(tasks),
            },
            "unfinished_tasks": self._decorate_objects(unfinished[:limit], redact, include_annotations, record_limit=5),
            "recent_done_tasks": self._decorate_objects(done[-limit:], redact, include_annotations, record_limit=5),
            "recent_ideas": self._decorate_objects(ideas[-limit:], redact, include_annotations, record_limit=5),
            "relations": self.repo.relations_for_object(project_id),
            "recent_journal_exposures": self._redact_records(exposures, redact),
            "signals": signals,
            "redaction": {"enabled": redact},
        }

    def inbox_context(self, days: int = 30, limit: int = 80, redact: bool = True, include_annotations: bool = True) -> Dict[str, Any]:
        since = self._since(days)
        ideas = self._unlinked_ideas(since, limit=limit)
        suspicious = self._suspicious_ideas(limit=limit)
        candidates = self._idea_project_candidates(ideas)
        return {
            "view": "inbox-context",
            "query": {"days": days, "since": since, "limit": limit},
            "unlinked_ideas": self._decorate_objects(ideas, redact, include_annotations, record_limit=5),
            "possible_project_links": candidates,
            "suspicious_ideas": self._decorate_objects(suspicious, redact, include_annotations, record_limit=3),
            "redaction": {"enabled": redact},
        }

    def active_projects_report(self, limit: int = 100) -> Dict[str, Any]:
        projects = self._active_projects(self._since(3650), limit=limit)
        return {"view": "active-projects", "projects": self._decorate_objects(projects, redact=True, include_annotations=True, record_limit=2)}

    def recent_unresolved_tasks_report(self, days: int = 14, limit: int = 100) -> Dict[str, Any]:
        since = self._since(days)
        tasks = [item for item in self._objects_with_recent_journal_records(since, limit=limit * 2, object_types=("task",)) if item.get("status") in {"todo", "doing"}]
        return {"view": "recent-unresolved-tasks", "query": {"days": days, "since": since}, "tasks": self._decorate_objects(tasks[:limit], True, True, record_limit=3)}

    def extraction_quality_report(self) -> Dict[str, Any]:
        metrics = self.repo.quality_metrics()
        sync_runs = self.repo.list_sync_runs(limit=5)
        return {
            "view": "extraction-quality",
            "metrics": metrics,
            "redaction": {"default_enabled": True},
            "recent_sync_runs": sync_runs,
            "interpretation": {
                "suspicious_ideas": "Ideas with malformed titles or suspicious extraction markers.",
                "unlinked_tasks_ideas": "Task/Idea objects without a belongs_to object relation.",
                "source_location_mismatches": "Objects whose canonical location differs from their definition record location.",
            },
        }

    def markdown(self, package: Dict[str, Any]) -> str:
        lines = [f"# {package.get('view', 'agent-view')}", ""]
        if "query" in package:
            lines.append(f"Query: `{package['query']}`")
            lines.append("")
        if package.get("view") == "extraction-quality":
            lines.extend(["## Metrics", ""])
            for key, value in package["metrics"].items():
                lines.append(f"- `{key}`: `{value}`")
            lines.extend(["", "## Recent Sync Runs", ""])
            for run in package["recent_sync_runs"]:
                lines.append(f"- #{run['id']} {run['adapter']} {run['status']} files={run['files_scanned']} objects={run['objects_seen']}")
            return "\n".join(lines) + "\n"
        for key, value in package.items():
            if key in {"view", "query", "redaction", "notes"}:
                continue
            lines.extend([f"## {key.replace('_', ' ').title()}", ""])
            if isinstance(value, list):
                for item in value:
                    if "object" in item:
                        lines.extend(self._object_item_markdown(item))
                    elif isinstance(item, dict) and "raw_text" in item:
                        lines.append(f"- `{item.get('file_path')}:{item.get('line_start') or ''}` {self.redactor.redact(item.get('raw_text', '')).text.strip()[:220]}")
                    else:
                        lines.append(f"- {self.redactor.redact(str(item)).text}")
            elif isinstance(value, dict) and "object" in value:
                lines.extend(self._object_item_markdown(value))
            elif isinstance(value, dict):
                for subkey, subvalue in value.items():
                    lines.append(f"- `{subkey}`: `{self.redactor.redact(str(subvalue)).text}`")
            else:
                lines.append(f"`{value}`")
            lines.append("")
        if package.get("notes"):
            lines.append(package["notes"])
        return "\n".join(lines).rstrip() + "\n"

    def _object_item_markdown(self, item: Dict[str, Any]) -> List[str]:
        obj = item["object"]
        lines = [f"- #{obj['id']} `{obj['object_type']}` `{obj.get('status')}` {obj.get('title')} ({obj.get('page_name')}:{obj.get('line_start') or ''})"]
        lines.append(f"  - activity: `{obj.get('last_activity_at')}` sources={obj.get('activity_sources')}")
        for record in item.get("records", [])[:3]:
            lines.append(f"  - `{record.get('role')}` {record.get('raw_text', '').strip()[:180]}")
        if item.get("annotations"):
            lines.append(f"  - annotations: `{len(item['annotations'])}`")
        return lines

    def _decorate_objects(self, objects: List[Dict[str, Any]], redact: bool, include_annotations: bool, record_limit: int) -> List[Dict[str, Any]]:
        return [self._decorate_object(item, redact, include_annotations, record_limit) for item in objects]

    def _decorate_object(self, obj: Dict[str, Any], redact: bool, include_annotations: bool, record_limit: int) -> Dict[str, Any]:
        object_id = int(obj["id"])
        merged = {**obj, **self.repo.object_activity(object_id)}
        records = self._redact_records(self.repo.records_for_object(object_id, limit=record_limit), redact)
        return {
            "object": merged,
            "definition_record": self._redact_record(self.repo.definition_record_for_object(object_id), redact),
            "records": records,
            "relations": self.repo.relations_for_object(object_id),
            "annotations": self.repo.list_annotations(target_object_id=object_id, limit=20) if include_annotations else [],
        }

    def _redact_records(self, records: List[Dict[str, Any]], redact: bool) -> List[Dict[str, Any]]:
        return [self._redact_record(record, redact) for record in records if record]

    def _redact_record(self, record: Optional[Dict[str, Any]], redact: bool) -> Optional[Dict[str, Any]]:
        if not record:
            return None
        metadata = record.get("metadata", {})
        private = bool(metadata.get("private"))
        if redact:
            record = dict(record)
            record["raw_text"] = self.redactor.redact(record.get("raw_text", ""), private=private).text
            record["normalized_text"] = self.redactor.redact(record.get("normalized_text", ""), private=private).text
        return record

    def _since(self, days: int) -> str:
        return (date.today() - timedelta(days=days)).isoformat()

    def _objects_with_recent_journal_records(self, since: str, limit: int, object_types: tuple) -> List[Dict[str, Any]]:
        placeholders = ",".join("?" for _ in object_types)
        rows = self.conn.execute(
            f"""
            SELECT DISTINCT o.*, l.file_path, l.page_name, l.journal_date, l.block_uuid, l.line_start
            FROM objects o
            LEFT JOIN locations l ON l.id=o.canonical_location_id
            JOIN object_record_links orl ON orl.object_id=o.id
            JOIN source_records r ON r.id=orl.record_id
            JOIN locations rl ON rl.id=r.location_id
            WHERE o.object_type IN ({placeholders})
              AND rl.journal_date >= ?
            ORDER BY rl.journal_date DESC, rl.line_start DESC, o.id DESC
            LIMIT ?
            """,
            (*object_types, since, limit),
        ).fetchall()
        return [self._load_object_row(row) for row in rows]

    def _active_projects(self, since: str, limit: int) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT DISTINCT p.*, l.file_path, l.page_name, l.journal_date, l.block_uuid, l.line_start
            FROM objects p
            LEFT JOIN locations l ON l.id=p.canonical_location_id
            LEFT JOIN relations rel ON rel.to_object_id=p.id AND rel.relation_type='belongs_to'
            LEFT JOIN object_record_links orl ON orl.object_id=rel.from_object_id
            LEFT JOIN source_records r ON r.id=orl.record_id
            LEFT JOIN locations rl ON rl.id=r.location_id
            WHERE p.object_type='project'
              AND (p.status IS NULL OR p.status NOT IN ('已完成', 'done', 'archived'))
              AND (rl.journal_date IS NULL OR rl.journal_date >= ?)
            ORDER BY COALESCE(rl.journal_date, p.last_seen_at) DESC, p.id DESC
            LIMIT ?
            """,
            (since, limit),
        ).fetchall()
        return [self._load_object_row(row) for row in rows]

    def _project_children(self, project_id: int, limit: int) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT o.*, l.file_path, l.page_name, l.journal_date, l.block_uuid, l.line_start
            FROM relations r
            JOIN objects o ON o.id=r.from_object_id
            LEFT JOIN locations l ON l.id=o.canonical_location_id
            WHERE r.to_object_id=? AND r.relation_type='belongs_to'
            ORDER BY o.object_type, COALESCE(o.created_at, o.first_seen_at), o.id
            LIMIT ?
            """,
            (project_id, limit),
        ).fetchall()
        return [self._load_object_row(row) for row in rows]

    def _project_exposures(self, project_id: int, since: str, limit: int) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT DISTINCT rec.*, loc.file_path, loc.page_name, loc.journal_date, loc.block_uuid, loc.line_start, loc.line_end, loc.block_path_json
            FROM relations rel
            JOIN object_record_links orl ON orl.object_id=rel.from_object_id
            JOIN source_records rec ON rec.id=orl.record_id
            JOIN locations loc ON loc.id=rec.location_id
            WHERE rel.to_object_id=? AND loc.journal_date >= ?
            ORDER BY loc.journal_date DESC, loc.line_start DESC
            LIMIT ?
            """,
            (project_id, since, limit),
        ).fetchall()
        return [self._load_record_row(row) for row in rows]

    def _unlinked_ideas(self, since: str, limit: int) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT o.*, l.file_path, l.page_name, l.journal_date, l.block_uuid, l.line_start
            FROM objects o
            LEFT JOIN locations l ON l.id=o.canonical_location_id
            WHERE o.object_type='idea'
              AND NOT EXISTS (SELECT 1 FROM relations r WHERE r.from_object_id=o.id AND r.relation_type='belongs_to')
              AND (COALESCE(o.created_at, l.journal_date, o.first_seen_at) >= ?)
            ORDER BY COALESCE(o.created_at, l.journal_date, o.first_seen_at) DESC, o.id DESC
            LIMIT ?
            """,
            (since, limit),
        ).fetchall()
        return [self._load_object_row(row) for row in rows]

    def _suspicious_ideas(self, limit: int) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT o.*, l.file_path, l.page_name, l.journal_date, l.block_uuid, l.line_start
            FROM objects o
            LEFT JOIN locations l ON l.id=o.canonical_location_id
            WHERE o.object_type='idea'
              AND (o.title LIKE ']%' OR LENGTH(TRIM(o.title)) < 2 OR o.metadata_json LIKE '%suspicious_idea_reason%')
            ORDER BY o.id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [self._load_object_row(row) for row in rows]

    def _idea_project_candidates(self, ideas: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        candidates = []
        for idea in ideas:
            refs = (idea.get("metadata") or {}).get("page_refs", [])
            if refs:
                candidates.append({"idea_id": idea["id"], "idea_title": idea["title"], "page_refs": refs})
        return candidates

    def _project_signals(self, project: Dict[str, Any], tasks: List[Dict[str, Any]], ideas: List[Dict[str, Any]], exposures: List[Dict[str, Any]]) -> Dict[str, Any]:
        unfinished = [item for item in tasks if item.get("status") in {"todo", "doing"}]
        text = "\n".join(record.get("raw_text", "") for record in exposures)
        return {
            "has_goal_but_no_unfinished_tasks": bool(project and not unfinished),
            "idea_heavy": len(ideas) > max(5, len(tasks) * 2),
            "doing_without_recent_done": any(item.get("status") == "doing" for item in tasks) and not any(item.get("status") == "done" for item in tasks),
            "problem_markers_seen": any(marker in text for marker in ["[问题]", "[待澄清]", "blocked", "阻塞", "卡住"]),
            "recent_exposure_count": len(exposures),
        }

    def _load_object_row(self, row) -> Dict[str, Any]:
        import json

        data = dict(row)
        data["metadata"] = json.loads(data.pop("metadata_json") or "{}")
        return data

    def _load_record_row(self, row) -> Dict[str, Any]:
        import json

        data = dict(row)
        data["metadata"] = json.loads(data.pop("metadata_json") or "{}")
        data["block_path"] = json.loads(data.pop("block_path_json") or "[]")
        return data
