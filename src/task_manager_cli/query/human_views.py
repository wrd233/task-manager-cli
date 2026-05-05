from typing import Any, Dict, List, Optional

from task_manager_cli.query.agent_views import AgentViewService
from task_manager_cli.storage.repositories import Repository


class HumanViewService:
    def __init__(self, conn, sensitive_patterns=None):
        self.conn = conn
        self.repo = Repository(conn)
        self.agent_views = AgentViewService(conn, sensitive_patterns=sensitive_patterns or [])

    def today(self, limit: int = 12, detail: bool = False) -> str:
        package = self.agent_views.today_context(days=14, limit=max(limit, 1), redact=True, include_annotations=True)
        lines = ["Today", "=====", ""]
        lines.extend(self._section("Recent unfinished", package.get("recent_unfinished_tasks", [])[:limit], detail))
        lines.extend(self._section("Recent ideas", package.get("recent_ideas", [])[: max(3, min(limit, 6))], detail))
        lines.extend(self._section("Active projects", package.get("active_projects", [])[: max(3, min(limit, 6))], detail))
        lines.append("Tip: use `tm view project <id>` or `tm show <id>` for details.")
        return "\n".join(lines).rstrip() + "\n"

    def projects(self, limit: int = 20, detail: bool = False) -> str:
        projects = self.repo.list_objects("project", limit=limit)
        decorated = [self._decorate_object(obj) for obj in projects]
        lines = ["Projects", "========", ""]
        lines.extend(self._section("Active / recent", decorated, detail))
        lines.append("Tip: use `tm view project <id>` for a project snapshot.")
        return "\n".join(lines).rstrip() + "\n"

    def project(self, ref: str, limit: int = 12, detail: bool = False) -> str:
        package = self.agent_views.project_context(ref, days=30, limit=max(limit, 1), redact=True, include_annotations=True)
        project = package["project"]
        obj = project["object"]
        stats = package.get("task_stats", {})
        lines = [f"Project #{obj['id']}: {obj.get('title')}", "=" * min(72, len(f"Project #{obj['id']}: {obj.get('title')}")), ""]
        lines.append(f"Status: {obj.get('status') or '-'} | Tasks todo/doing/done: {stats.get('todo', 0)}/{stats.get('doing', 0)}/{stats.get('done', 0)} | Ideas: {len(package.get('recent_ideas', []))}")
        lines.append(f"Location: {obj.get('page_name')}:{obj.get('line_start') or ''}")
        if detail:
            lines.append(f"Activity: {obj.get('last_activity_at') or '-'} | annotations: {obj.get('annotation_count', 0)}")
        lines.append("")
        lines.extend(self._section("Open tasks", package.get("unfinished_tasks", [])[:limit], detail))
        lines.extend(self._section("Recent done", package.get("recent_done_tasks", [])[: max(3, min(limit, 6))], detail))
        lines.extend(self._section("Ideas", package.get("recent_ideas", [])[: max(3, min(limit, 6))], detail))
        signals = package.get("signals", {})
        visible_signals = [key for key, value in signals.items() if value]
        if visible_signals:
            lines.extend(["Signals", "-------"])
            for signal in visible_signals:
                lines.append(f"- {signal}")
            lines.append("")
        lines.append(f"Tip: use `tm context {obj['id']}` for full context.")
        return "\n".join(lines).rstrip() + "\n"

    def tasks(self, limit: int = 20, detail: bool = False) -> str:
        todo = self.repo.list_objects("task", status="todo", limit=limit)
        doing = self.repo.list_objects("task", status="doing", limit=max(5, min(limit, 10)))
        lines = ["Tasks", "=====", ""]
        lines.extend(self._section("Doing", [self._decorate_object(obj) for obj in doing], detail))
        lines.extend(self._section("Todo", [self._decorate_object(obj) for obj in todo], detail))
        lines.append("Tip: use `tm show <id>` for details.")
        return "\n".join(lines).rstrip() + "\n"

    def ideas(self, limit: int = 20, detail: bool = False) -> str:
        ideas = self.repo.list_objects("idea", limit=limit)
        lines = ["Ideas", "=====", ""]
        lines.extend(self._section("Recent captured", [self._decorate_object(obj) for obj in ideas], detail))
        lines.append("Tip: use `tm view inbox` for unlinked ideas.")
        return "\n".join(lines).rstrip() + "\n"

    def inbox(self, limit: int = 20, detail: bool = False) -> str:
        package = self.agent_views.inbox_context(days=30, limit=limit, redact=True, include_annotations=True)
        lines = ["Inbox", "=====", ""]
        lines.extend(self._section("Unlinked ideas", package.get("unlinked_ideas", [])[:limit], detail))
        suspicious = package.get("suspicious_ideas", [])
        if suspicious:
            lines.extend(self._section("Suspicious extractions", suspicious[: max(3, min(limit, 8))], detail))
        candidates = package.get("possible_project_links", [])[: max(3, min(limit, 8))]
        if candidates and detail:
            lines.extend(["Possible links", "--------------"])
            for item in candidates:
                refs = ", ".join(item.get("page_refs", []))
                lines.append(f"- idea #{item.get('idea_id')}: {item.get('idea_title')} -> {refs}")
            lines.append("")
        lines.append("Tip: use `tm agent inbox-context --format json` for triage context.")
        return "\n".join(lines).rstrip() + "\n"

    def _section(self, title: str, items: List[Dict[str, Any]], detail: bool) -> List[str]:
        lines = [title, "-" * len(title)]
        if not items:
            lines.extend(["- none", ""])
            return lines
        for item in items:
            obj = item.get("object", item)
            lines.append(self._one_line(obj, detail))
            if detail:
                records = item.get("records", [])
                if records:
                    snippet = records[0].get("raw_text", "").strip().replace("\n", " ")
                    if snippet:
                        lines.append(f"  {snippet[:160]}")
        lines.append("")
        return lines

    def _one_line(self, obj: Dict[str, Any], detail: bool) -> str:
        status = obj.get("status") or "-"
        title = self._truncate(str(obj.get("title") or ""), 72 if detail else 56)
        where = obj.get("page_name") or "-"
        line = obj.get("line_start") or ""
        activity = obj.get("last_activity_at") or obj.get("last_seen_at") or ""
        base = f"- #{obj.get('id')} [{status}] {title} ({where}:{line})"
        if detail:
            signals = []
            if obj.get("journal_exposure_count"):
                signals.append(f"exposed {obj.get('journal_exposure_count')}x")
            if obj.get("child_record_count"):
                signals.append(f"{obj.get('child_record_count')} notes")
            if obj.get("annotation_count"):
                signals.append(f"{obj.get('annotation_count')} annotations")
            if activity:
                signals.append(f"activity {activity}")
            if signals:
                base += " | " + ", ".join(signals)
        return base

    def _decorate_object(self, obj: Dict[str, Any]) -> Dict[str, Any]:
        return {"object": {**obj, **self.repo.object_activity(int(obj["id"]))}, "records": []}

    def _truncate(self, text: str, width: int) -> str:
        return text if len(text) <= width else text[: width - 1] + "…"
