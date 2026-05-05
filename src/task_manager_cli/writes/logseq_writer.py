import difflib
import hashlib
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from task_manager_cli.adapters.logseq.parser import LogseqBlock, parse_logseq_file
from task_manager_cli.core.errors import TaskManagerError


class WriteError(TaskManagerError):
    pass


@dataclass
class WritePreview:
    file_path: Path
    original_sha256: str
    new_text: str
    diff: str
    line_start: Optional[int] = None
    block_uuid: Optional[str] = None


class LogseqWriter:
    def __init__(self, graph_path: Path):
        self.graph_path = Path(graph_path).expanduser()

    def sha256(self, path: Path) -> str:
        data = Path(path).read_bytes()
        return hashlib.sha256(data).hexdigest()

    def preview_append_child(self, file_path: Path, content: str, block_uuid: Optional[str] = None, line_start: Optional[int] = None) -> WritePreview:
        path = Path(file_path).expanduser()
        lines = path.read_text(encoding="utf-8").splitlines()
        block = self._resolve_block(path, block_uuid=block_uuid, line_start=line_start)
        insert_at = self._subtree_end_line(block, lines)
        child_indent = " " * ((block.indent + 1) * 4)
        new_block_lines = self._format_block_lines(content, child_indent)
        new_lines = lines[:insert_at] + new_block_lines + lines[insert_at:]
        return self._preview(path, lines, new_lines, line_start=block.line_number, block_uuid=block.uuid)

    def preview_append_page_section(self, file_path: Path, section_marker: str, content: str) -> WritePreview:
        path = Path(file_path).expanduser()
        lines = path.read_text(encoding="utf-8").splitlines()
        parsed = parse_logseq_file(path)
        section = next((block for block in parsed.blocks if section_marker in block.text), None)
        if section is None:
            raise WriteError(f"Section marker not found: {section_marker}")
        insert_at = self._subtree_end_line(section, lines)
        child_indent = " " * ((section.indent + 1) * 4)
        new_block_lines = self._format_block_lines(content, child_indent)
        new_lines = lines[:insert_at] + new_block_lines + lines[insert_at:]
        return self._preview(path, lines, new_lines, line_start=section.line_number, block_uuid=section.uuid)

    def preview_create_page(self, page_name: str, content: str) -> WritePreview:
        pages_dir = self.graph_path / "pages"
        path = pages_dir / f"{page_name.replace('/', '%2F')}.md"
        if path.exists():
            raise WriteError(f"Page already exists: {path}")
        lines = []
        new_lines = self._format_block_lines(content, "")
        diff = "\n".join(difflib.unified_diff([], [line + "\n" for line in new_lines], fromfile="/dev/null", tofile=str(path)))
        return WritePreview(file_path=path, original_sha256="", new_text="\n".join(new_lines) + "\n", diff=diff)

    def apply(self, preview: WritePreview, expected_sha256: Optional[str], backup_dir: Path) -> Path:
        path = preview.file_path
        if path.exists():
            current = self.sha256(path)
            if expected_sha256 and current != expected_sha256:
                raise WriteError("Target file changed since proposal was created; refusing to apply.")
            backup_path = self.backup(path, backup_dir)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            backup_path = Path("")
        path.write_text(preview.new_text, encoding="utf-8")
        return backup_path

    def backup(self, path: Path, backup_dir: Path) -> Path:
        backup_dir = Path(backup_dir).expanduser()
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        safe_name = str(path).strip("/").replace("/", "__")
        backup_path = backup_dir / f"{stamp}__{safe_name}"
        shutil.copy2(path, backup_path)
        return backup_path

    def _resolve_block(self, path: Path, block_uuid: Optional[str], line_start: Optional[int]) -> LogseqBlock:
        parsed = parse_logseq_file(path)
        if block_uuid:
            for block in parsed.blocks:
                if block.uuid == block_uuid:
                    return block
            raise WriteError(f"Block uuid not found in file: {block_uuid}")
        if line_start:
            for block in parsed.blocks:
                if block.line_number == line_start:
                    return block
            raise WriteError(f"Block line not found in file: {line_start}")
        raise WriteError("append_child_block requires block_uuid or line_start.")

    def _subtree_end_line(self, block: LogseqBlock, lines: List[str]) -> int:
        end = block.line_number
        for candidate in block.descendants():
            end = max(end, candidate.line_number)
        while end < len(lines) and self._is_property_or_continuation(lines[end], block.indent):
            end += 1
        return end

    def _is_property_or_continuation(self, line: str, parent_indent: int) -> bool:
        if not line.strip():
            return True
        leading = len(line) - len(line.lstrip(" "))
        return leading > parent_indent * 4 and not line.lstrip().startswith("-")

    def _format_block_lines(self, content: str, indent: str) -> List[str]:
        raw_lines = content.splitlines() or [content]
        formatted = []
        for index, raw in enumerate(raw_lines):
            text = raw.rstrip()
            if not text:
                continue
            if text.lstrip().startswith("-"):
                formatted.append(f"{indent}{text.lstrip()}")
            elif index == 0:
                formatted.append(f"{indent}- {text}")
            else:
                formatted.append(f"{indent}  {text}")
        return formatted or [f"{indent}- "]

    def _preview(self, path: Path, old_lines: List[str], new_lines: List[str], line_start: Optional[int] = None, block_uuid: Optional[str] = None) -> WritePreview:
        old_text_lines = [line + "\n" for line in old_lines]
        new_text_lines = [line + "\n" for line in new_lines]
        diff = "\n".join(difflib.unified_diff(old_text_lines, new_text_lines, fromfile=str(path), tofile=str(path)))
        return WritePreview(
            file_path=path,
            original_sha256=self.sha256(path),
            new_text="".join(new_text_lines),
            diff=diff,
            line_start=line_start,
            block_uuid=block_uuid,
        )
