from dataclasses import dataclass
from typing import Optional


@dataclass
class SyncStatus:
    file_status: str = "synced"
    index_status: str = "fresh"
    buffer_status: str = "none"
    view_status: str = "fresh"
    rollback_op_id: Optional[int] = None
    mode: str = "NORMAL"
    last_write_file: Optional[str] = None
    last_write_line: Optional[int] = None
    message: str = ""

    def mark_write_success(self, file_path: str, line: Optional[int], op_id: Optional[int]) -> None:
        self.file_status = "synced"
        self.index_status = "fresh"
        self.buffer_status = "none"
        self.view_status = "fresh"
        self.mode = "NORMAL"
        self.rollback_op_id = op_id
        self.last_write_file = file_path
        self.last_write_line = line
        self.message = ""

    def mark_write_failed(self, message: str) -> None:
        self.file_status = "failed"
        self.index_status = "unchanged"
        self.view_status = "stale"
        self.message = message

    def mark_conflict(self, message: str = "file changed externally") -> None:
        self.file_status = "conflict"
        self.buffer_status = "dirty"
        self.view_status = "stale"
        self.mode = "CONFLICT"
        self.message = message

    def mark_buffer(self, dirty: bool) -> None:
        self.buffer_status = "dirty" if dirty else "clean"
        self.mode = "INSERT"

    def clear_buffer(self) -> None:
        self.buffer_status = "none"
        self.mode = "NORMAL"

    def rollback_label(self) -> str:
        return f"op #{self.rollback_op_id}" if self.rollback_op_id else "none"

    def format_line(self) -> str:
        file_label = {
            "synced": "synced ✓",
            "dirty": "dirty *",
            "failed": "write failed ✗",
            "conflict": "conflict !",
        }.get(self.file_status, self.file_status)
        index_label = {
            "fresh": "fresh ✓",
            "stale": "stale !",
            "unknown": "unknown ?",
            "unchanged": "unchanged",
        }.get(self.index_status, self.index_status)
        buffer_label = {
            "none": "none",
            "clean": "clean",
            "dirty": "dirty *",
        }.get(self.buffer_status, self.buffer_status)
        view_label = {
            "fresh": "fresh ✓",
            "stale": "stale !",
        }.get(self.view_status, self.view_status)
        return (
            f"File: {file_label} | Index: {index_label} | Buffer: {buffer_label} | "
            f"View: {view_label} | Rollback: {self.rollback_label()} | Mode: {self.mode}"
        )
