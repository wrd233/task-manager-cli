import os
import shutil
import textwrap
from dataclasses import dataclass, field
from typing import Callable, Optional

from task_manager_cli.shell.sync_status import SyncStatus


VALID_VIEWS = {
    "show",
    "tree",
    "tasks",
    "today",
    "dashboard",
    "proposals",
    "health",
    "search",
    "preview",
    "edit",
}

VALID_DENSITIES = {"compact", "standard", "full"}


@dataclass
class LayoutState:
    enabled: bool = False
    current_view: str = "today"
    density: str = "standard"
    current_focus: Optional[str] = None
    current_focus_label: Optional[str] = None
    last_message: str = ""
    last_search: str = ""
    last_preview: str = ""
    sync_status: SyncStatus = field(default_factory=SyncStatus)

    def set_view(self, view_name: str) -> None:
        if view_name in VALID_VIEWS:
            self.current_view = view_name
            self.sync_status.view_status = "fresh"

    def set_focus(self, focus_ref: Optional[str], label: Optional[str] = None) -> None:
        self.current_focus = str(focus_ref) if focus_ref is not None else None
        self.current_focus_label = label


class LayoutRenderer:
    def __init__(self, width: Optional[int] = None, clear_screen: bool = False):
        detected = shutil.get_terminal_size((100, 30)).columns
        self.width = max(48, min(width or detected, 120))
        self.clear_screen = clear_screen and bool(os.environ.get("TERM"))

    def render(
        self,
        *,
        state: LayoutState,
        path: str,
        project: str = "-",
        node: str = "-",
        focus: str = "-",
        main_title: str,
        main_body: str,
        actions_title: str,
        actions_body: str,
        prompt: str,
    ) -> str:
        lines = []
        if self.clear_screen:
            lines.append("\033[2J\033[H")
        lines.extend(self._pane("Context", self._context_body(state, path, project, node, focus)))
        lines.extend(self._pane(f"Main View: {main_title}", main_body))
        if state.density != "compact":
            actions = actions_body
            if state.density == "standard":
                actions = self._limit_lines(actions_body, 16)
            lines.extend(self._pane(f"Actionable List: {actions_title}", actions))
        lines.extend(self._pane("Last Message", state.last_message or "(none)"))
        lines.append(self._bar("="))
        lines.append(prompt)
        return "\n".join(lines)

    def _context_body(self, state: LayoutState, path: str, project: str, node: str, focus: str) -> str:
        return "\n".join(
            [
                f"Path: {path}",
                f"Project: {project}",
                f"Node: {node}",
                f"Focus: {focus}",
                f"View: {state.current_view} | Mode: {state.sync_status.mode} | Density: {state.density}",
                state.sync_status.format_line(),
            ]
        )

    def _pane(self, title: str, body: str) -> list[str]:
        return [self._bar("="), title, self._bar("-"), *self._wrap_body(body)]

    def _bar(self, char: str) -> str:
        return char * self.width

    def _wrap_body(self, body: str) -> list[str]:
        if not body:
            return ["(empty)"]
        result: list[str] = []
        for line in body.splitlines() or [""]:
            if len(line) <= self.width:
                result.append(line)
                continue
            result.extend(textwrap.wrap(line, width=self.width, replace_whitespace=False, drop_whitespace=False) or [""])
        return result

    def _limit_lines(self, body: str, limit: int) -> str:
        lines = body.splitlines()
        if len(lines) <= limit:
            return body
        return "\n".join(lines[:limit] + [f"... Showing {limit} of {len(lines)} lines. Use layout full for more."])


def default_view_for_path(path: str, *, has_project: bool = False, has_node: bool = False, has_object: bool = False) -> str:
    if path == "/today":
        return "today"
    if path == "/dashboard":
        return "dashboard"
    if has_node or has_object:
        return "show"
    if has_project:
        return "tree"
    if path == "/proposals":
        return "proposals"
    return "show"


def view_for_command(command: str, args: list[str]) -> Optional[str]:
    if command == "tree":
        return "tree"
    if command == "show":
        return "show"
    if command == "find":
        return "search"
    if command == "proposals":
        return "proposals"
    if command in {"preview", "apply"} and not (command == "preview" and args and args[0] in {"on", "off"}):
        return "preview"
    if command in {"quality", "q"} and (not args or args[0] in {"project", "health"}):
        return "health"
    if command == "ls" and args:
        if args[0] in {"tasks", "todo", "doing", "waiting", "done"}:
            return "tasks"
    return None
