from dataclasses import dataclass, replace

from task_manager_cli.shell.inventory import DEFAULT_LIMIT, build_inventory


@dataclass
class RenderedView:
    title: str
    body: str
    actions_title: str = "current context"
    actions_body: str = ""


class ShellViewRenderer:
    def __init__(self, shell):
        self.shell = shell

    def render(self, view_name: str) -> RenderedView:
        if view_name == "tree":
            body = self.shell.tree([])
        elif view_name == "tasks":
            body = self.shell.ls(["tasks"])
        elif view_name == "today":
            old_path = self.shell.context.path
            body = self.shell.ls(["all"]) if old_path == "/today" else self._render_path("/today")
        elif view_name == "dashboard":
            old_path = self.shell.context.path
            body = self.shell.ls(["all"]) if old_path == "/dashboard" else self._render_path("/dashboard")
        elif view_name == "proposals":
            body = self.shell.proposals()
        elif view_name == "health":
            body = self.shell.quality(["project"]) if self.shell.context.project_ref else "view health requires a project context.\nUse cd /projects/<project> first."
        elif view_name == "search":
            if self.shell.layout_state.last_search:
                body = self.shell.find(self.shell.layout_state.last_search)
            else:
                body = "No active search. Use find <keyword>."
        elif view_name == "preview":
            body = self.shell.layout_state.last_preview or "No active preview."
        elif view_name == "edit":
            body = self.shell.layout_state.last_preview or "No edit buffer."
        else:
            body = self.shell.show([])
        return RenderedView(
            title=view_name,
            body=body,
            actions_title=self._actions_title(),
            actions_body=self._actions_body(view_name),
        )

    def _render_path(self, path: str) -> str:
        resolved = self.shell._resolve_path(path)
        if not resolved:
            return f"Path not found: {path}"
        original = replace(self.shell.context)
        try:
            self.shell._apply_context(resolved)
            return self.shell.ls(["all"])
        finally:
            self.shell.context = original

    def _actions_title(self) -> str:
        inv = build_inventory(self.shell.conn, self.shell.context, self.shell.repo, self.shell.settings)
        sections = [section.get("label") for section in inv.get("sections", []) if section.get("items")]
        return ", ".join(sections[:3]) or "current context"

    def _actions_body(self, view_name: str) -> str:
        inv = build_inventory(self.shell.conn, self.shell.context, self.shell.repo, self.shell.settings)
        lines: list[str] = []
        count = 0
        limit = DEFAULT_LIMIT if self.shell.layout_state.density != "full" else 50
        for section in inv.get("sections", []):
            items = section.get("items", [])
            if not items:
                continue
            lines.append(f"{section.get('label', section.get('type', 'Items'))}:")
            for item in items[: max(0, limit - count)]:
                lines.append(self._item_line(item))
                count += 1
                if count >= limit:
                    break
            if count >= limit:
                total = sum(len(s.get("items", [])) for s in inv.get("sections", []))
                if total > count:
                    lines.append(f"Showing {count} of {total}. Use ls tasks --all or layout full.")
                break
        return "\n".join(lines) if lines else "No actionable items in this context."

    def _item_line(self, item: dict) -> str:
        item_type = item.get("type", "")
        title = item.get("title", "")
        status = item.get("status") or ""
        iid = item.get("object_id") or item.get("id")
        if item_type == "node":
            return f"  [{iid}] {item.get('label') or ''} {title}".rstrip()
        if item_type == "proposal":
            return f"  [{item.get('id')}] proposal:{item.get('proposal_id', iid)} {item.get('risk', '')} {item.get('proposal_type', '')}".rstrip()
        prefix = f"#{iid}" if str(iid).isdigit() else str(iid)
        marker = f" {status.upper()}" if status else ""
        return f"  {prefix}{marker} {item_type} {title}".rstrip()
