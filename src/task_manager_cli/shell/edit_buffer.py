from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass
class EditBuffer:
    target_id: str
    target_type: str
    scope: str
    source_file: Path
    source_range: tuple[int, int]
    original_lines: List[str]
    buffer_lines: List[str]
    file_hash_at_start: str
    cursor_row: int = 0
    cursor_col: int = 0
    scroll_offset: int = 0
    base_indent: str = ""

    @property
    def dirty(self) -> bool:
        return self.buffer_lines != self.original_lines

    def current_line(self) -> str:
        self._ensure_line()
        return self.buffer_lines[self.cursor_row]

    def insert_text(self, text: str) -> None:
        if "\n" in text:
            self.paste(text)
            return
        self._ensure_line()
        line = self.buffer_lines[self.cursor_row]
        self.buffer_lines[self.cursor_row] = line[: self.cursor_col] + text + line[self.cursor_col :]
        self.cursor_col += len(text)

    def paste(self, text: str) -> None:
        self._ensure_line()
        parts = text.splitlines()
        if not parts:
            return
        line = self.buffer_lines[self.cursor_row]
        before, after = line[: self.cursor_col], line[self.cursor_col :]
        if len(parts) == 1:
            self.insert_text(parts[0])
            return
        replacement = [before + parts[0], *parts[1:-1], parts[-1] + after]
        self.buffer_lines[self.cursor_row : self.cursor_row + 1] = replacement
        self.cursor_row += len(replacement) - 1
        self.cursor_col = len(parts[-1])

    def enter(self) -> None:
        self._ensure_line()
        line = self.buffer_lines[self.cursor_row]
        self.buffer_lines[self.cursor_row] = line[: self.cursor_col]
        self.buffer_lines.insert(self.cursor_row + 1, line[self.cursor_col :])
        self.cursor_row += 1
        self.cursor_col = 0

    def backspace(self) -> None:
        self._ensure_line()
        if self.cursor_col > 0:
            line = self.buffer_lines[self.cursor_row]
            self.buffer_lines[self.cursor_row] = line[: self.cursor_col - 1] + line[self.cursor_col :]
            self.cursor_col -= 1
            return
        if self.cursor_row > 0:
            previous = self.buffer_lines[self.cursor_row - 1]
            current = self.buffer_lines.pop(self.cursor_row)
            self.cursor_row -= 1
            self.cursor_col = len(previous)
            self.buffer_lines[self.cursor_row] = previous + current

    def delete(self) -> None:
        self._ensure_line()
        line = self.buffer_lines[self.cursor_row]
        if self.cursor_col < len(line):
            self.buffer_lines[self.cursor_row] = line[: self.cursor_col] + line[self.cursor_col + 1 :]
            return
        if self.cursor_row + 1 < len(self.buffer_lines):
            self.buffer_lines[self.cursor_row] = line + self.buffer_lines.pop(self.cursor_row + 1)

    def move_left(self) -> None:
        if self.cursor_col > 0:
            self.cursor_col -= 1
        elif self.cursor_row > 0:
            self.cursor_row -= 1
            self.cursor_col = len(self.buffer_lines[self.cursor_row])

    def move_right(self) -> None:
        self._ensure_line()
        if self.cursor_col < len(self.buffer_lines[self.cursor_row]):
            self.cursor_col += 1
        elif self.cursor_row + 1 < len(self.buffer_lines):
            self.cursor_row += 1
            self.cursor_col = 0

    def move_up(self) -> None:
        if self.cursor_row > 0:
            self.cursor_row -= 1
            self.cursor_col = min(self.cursor_col, len(self.buffer_lines[self.cursor_row]))

    def move_down(self) -> None:
        if self.cursor_row + 1 < len(self.buffer_lines):
            self.cursor_row += 1
            self.cursor_col = min(self.cursor_col, len(self.buffer_lines[self.cursor_row]))

    def home(self) -> None:
        self.cursor_col = 0

    def end(self) -> None:
        self._ensure_line()
        self.cursor_col = len(self.buffer_lines[self.cursor_row])

    def set_text(self, text: str) -> None:
        self.buffer_lines = text.splitlines() or [""]
        self.cursor_row = max(0, len(self.buffer_lines) - 1)
        self.cursor_col = len(self.buffer_lines[self.cursor_row])

    def render(self, max_lines: int = 40) -> str:
        start = self.scroll_offset
        end = min(len(self.buffer_lines), start + max_lines)
        lines: list[str] = []
        for idx in range(start, end):
            prefix = ">" if idx == self.cursor_row else " "
            lines.append(f"{prefix}{idx + 1:4d} {self.buffer_lines[idx]}")
            if idx == self.cursor_row:
                lines.append("      " + " " * min(self.cursor_col, 200) + "^")
        if end < len(self.buffer_lines):
            lines.append(f"... {len(self.buffer_lines) - end} more lines")
        return "\n".join(lines)

    def _ensure_line(self) -> None:
        if not self.buffer_lines:
            self.buffer_lines.append("")
        self.cursor_row = max(0, min(self.cursor_row, len(self.buffer_lines) - 1))
        self.cursor_col = max(0, min(self.cursor_col, len(self.buffer_lines[self.cursor_row])))
