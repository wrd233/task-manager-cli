from dataclasses import dataclass
from typing import List


COMMANDS = [
    "pwd",
    "ls",
    "cd",
    "tree",
    "show",
    "open",
    "find",
    "todo",
    "idea",
    "mini",
    "resource",
    "note",
    "ainote",
    "doing",
    "done",
    "wait",
    "someday",
    "result",
    "noresult",
    "clarify",
    "provider",
    "proposals",
    "accept",
    "reject",
    "edit",
    "supersede",
    "preview",
    "apply",
    "history",
    "ops",
    "commands",
    "clear-history",
    "undo",
    "where",
    "quality",
    "q",
    "detail",
    "complete",
    "help",
    "exit",
    "quit",
]

ROOT_PATHS = ["/today", "/inbox", "/waiting", "/someday", "/ideas", "/projects", "/mini", "/reviews", "/proposals"]
PROVIDERS = ["off", "dry-run", "mock", "deepseek", "openai-compatible", "remote"]
QUALITY = ["project-tree", "mini", "membership", "clarify", "all"]
ON_OFF = ["on", "off"]


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
            return COMMANDS
        if command == "cd":
            return self._path_candidates(token)
        if command in {"show", "open", "done", "doing", "wait", "someday", "note", "ainote", "result", "noresult"}:
            return self.shell.completion_object_candidates(command)
        if command == "detail" or (command == "preview" and any(item.startswith(token) for item in ON_OFF)):
            return ON_OFF
        if command in {"accept", "reject", "preview", "apply", "edit", "supersede"}:
            return self.shell.completion_proposal_candidates()
        if command == "provider":
            return PROVIDERS
        if command in {"quality", "q"}:
            return QUALITY
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
        if self.shell.context.project_ref:
            return self.shell.completion_project_node_names()
        return ROOT_PATHS
