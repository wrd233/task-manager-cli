"""Small ANSI color helpers for human-readable terminal output."""

from __future__ import annotations

import os
import re
import sys
from typing import Optional


RESET = "\033[0m"
SEMANTIC_MARKER_COLOR = "1;33"
STATUS_COLORS = {
    "todo": "38;5;25",
    "doing": "38;5;90",
    "waiting": "38;5;136",
    "done": "38;5;28",
    "canceled": "38;5;244",
    "cancelled": "38;5;244",
}
TASK_MARKER_RE = re.compile(r"\b(TODO|DOING|WAITING|DONE|CANCELED|CANCELLED)\b")
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def use_color(color: Optional[bool] = None) -> bool:
    if color is not None:
        return color
    if os.environ.get("NO_COLOR"):
        return False
    return sys.stdout.isatty()


def colorize(text: str, code: str, enabled: bool) -> str:
    if not enabled or not text:
        return text
    return f"\033[{code}m{text}{RESET}"


def color_status(status: str, enabled: bool) -> str:
    key = (status or "").lower()
    return colorize(status, STATUS_COLORS.get(key, ""), enabled) if key in STATUS_COLORS else status


def color_task_markers(text: str, enabled: bool) -> str:
    if not enabled or not text:
        return text

    def repl(match: re.Match) -> str:
        return color_status(match.group(1), enabled)

    return TASK_MARKER_RE.sub(repl, text)


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)
