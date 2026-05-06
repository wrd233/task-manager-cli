from dataclasses import dataclass
from typing import List


COMMANDS = [
    "pwd", "ls", "cd", "tree", "show", "open", "find",
    "todo", "idea", "mini", "resource",
    "note", "ainote", "doing", "done", "wait", "someday", "result", "noresult",
    "clarify", "provider", "proposals",
    "accept", "reject", "edit", "supersede", "preview", "apply",
    "history", "ops", "commands", "clear-history", "undo",
    "where", "quality", "q", "detail", "complete",
    "help", "exit", "quit",
]

ROOT_PATHS = ["/today", "/inbox", "/waiting", "/someday", "/ideas", "/projects", "/mini", "/reviews", "/proposals"]
PROVIDERS = ["off", "dry-run", "mock", "deepseek", "openai-compatible", "remote"]
QUALITY = ["project-tree", "mini", "membership", "clarify", "all"]
ON_OFF = ["on", "off"]
LS_FILTERS = ["tasks", "todo", "doing", "waiting", "ideas", "resources", "mini", "nodes", "proposals", "all"]
EDIT_SUBCOMMANDS = ["proposal", "task"]
TASK_FIELDS = ["title", "content", "status"]
TASK_STATUSES = ["todo", "doing", "waiting", "done"]
PROPOSAL_FIELDS = ["content", "reason", "risk", "marker"]


@dataclass
class CompletionResult:
    replacement: str
    candidates: List[str]
    unique: bool = False
    display: str = ""


class ShellCompleter:
    def __init__(self, shell):
        self.shell = shell

    def complete_line(self, line: str, cursor: int = None, limit: int = 20) -> CompletionResult:
        cursor = len(line) if cursor is None else cursor
        before = line[:cursor]
        parts = before.split()
        token = "" if before.endswith(" ") else (parts[-1] if parts else "")
        command = parts[0] if parts else ""
        candidates = self._candidates(command, token, parts)
        candidates = [item for item in candidates if item.startswith(token)]
        candidates = sorted(dict.fromkeys(candidates))[:limit]
        if len(candidates) == 1:
            return CompletionResult(candidates[0], candidates, unique=True)
        display = "\n".join(f"  {item}" for item in candidates)
        return CompletionResult(token, candidates, unique=False, display=display)

    def _candidates(self, command: str, token: str, parts: List[str]) -> List[str]:
        if len(parts) <= 1 and token == command:
            if not token or any(cmd.startswith(token) for cmd in COMMANDS):
                return COMMANDS
            return self._relative_context_candidates(token)

        if command == "cd":
            return self._path_candidates(token)

        if command == "ls":
            return self._ls_candidates(token, parts)

        if command in {"show", "open", "done", "doing", "wait", "someday", "note", "ainote", "result", "noresult"}:
            return self.shell.completion_object_candidates(command)

        if command == "detail" or (command == "preview" and any(item.startswith(token) for item in ON_OFF)):
            return ON_OFF

        if command in {"accept", "reject", "preview", "apply", "supersede"}:
            return self.shell.completion_proposal_candidates()

        if command == "edit":
            return self._edit_candidates(token, parts)

        if command == "provider":
            return PROVIDERS

        if command in {"quality", "q"}:
            return QUALITY

        if command not in COMMANDS and not token.startswith("/"):
            return self._relative_context_candidates(token)

        return []

    def _path_candidates(self, token: str) -> List[str]:
        if token.startswith("/projects/"):
            prefix = token.removeprefix("/projects/")
            return ["/projects/" + item for item in self.shell.completion_project_names() if item.startswith(prefix)]
        if token.startswith("/mini/"):
            prefix = token.removeprefix("/mini/")
            return ["/mini/" + item for item in self.shell.completion_mini_names() if item.startswith(prefix)]
        if token.startswith("/"):
            paths = list(ROOT_PATHS)
            paths.extend("/projects/" + item for item in self.shell.completion_project_names())
            paths.extend("/mini/" + item for item in self.shell.completion_mini_names())
            return paths

        # Relative completion based on current context
        path = self.shell.context.path
        if path == "/projects":
            return self.shell.completion_project_names()
        if path == "/mini":
            return self.shell.completion_mini_names()
        if self.shell.context.project_ref:
            return self.shell.completion_project_node_names()

        return ROOT_PATHS

    def _relative_context_candidates(self, token: str) -> List[str]:
        """Relative completion for bare tokens in specific contexts."""
        return self.shell.completion_relative_in_context(token)

    def _ls_candidates(self, token: str, parts: List[str]) -> List[str]:
        """Completion for ls filters."""
        return LS_FILTERS

    def _edit_candidates(self, token: str, parts: List[str]) -> List[str]:
        """Completion for edit command."""
        # edit <Tab> → proposal, task
        if len(parts) == 2:
            return EDIT_SUBCOMMANDS

        subcommand = parts[1] if len(parts) > 1 else ""

        if subcommand == "proposal":
            if len(parts) == 3 and not parts[-1].isdigit():
                return self.shell.completion_proposal_candidates()
            if len(parts) == 3 and parts[-1].isdigit() and not token:
                return PROPOSAL_FIELDS
            if len(parts) >= 4:
                return PROPOSAL_FIELDS

        if subcommand == "task":
            if len(parts) == 3 and not parts[-1].isdigit():
                # edit task <prefix> → task candidates
                return self.shell.completion_object_candidates("show")
            if len(parts) == 3 and parts[-1].isdigit() and not token:
                # edit task <id> <Tab> → field candidates
                return TASK_FIELDS
            if len(parts) == 3 and parts[-1].isdigit() and token:
                # edit task <id> <prefix> → field candidates
                return TASK_FIELDS
            if len(parts) >= 4:
                if parts[3].lower() == "status" if len(parts) > 3 else False:
                    return TASK_STATUSES
                return TASK_FIELDS

        # edit <N> ... backwards compat
        if len(parts) == 2 and parts[1].isdigit():
            return []

        return EDIT_SUBCOMMANDS
