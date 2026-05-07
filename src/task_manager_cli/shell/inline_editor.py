import difflib
from pathlib import Path
from typing import Optional

from task_manager_cli.adapters.logseq.parser import indent_level, parse_logseq_file
from task_manager_cli.core.errors import TaskManagerError
from task_manager_cli.projects.tree import ProjectTreeService
from task_manager_cli.shell.edit_buffer import EditBuffer
from task_manager_cli.writes.logseq_writer import WriteError, WritePreview


class InlineEditor:
    def __init__(self, shell):
        self.shell = shell

    def start(self, args: list[str]) -> str:
        try:
            buffer = self.create_buffer(args)
        except TaskManagerError as exc:
            return str(exc)
        self.shell.layout_state.sync_status.mark_buffer(False)
        self.shell.layout_state.set_view("edit")
        self.shell.layout_state.last_preview = self.render_buffer(buffer)
        result = self._line_mode_loop(buffer)
        self.shell.layout_state.sync_status.clear_buffer()
        self.shell.layout_state.set_view("show")
        return result

    def create_buffer(self, args: list[str]) -> EditBuffer:
        target_ref, scope = self._parse_args(args)
        target = self._resolve_edit_target(target_ref)
        if not target:
            raise TaskManagerError("No editable focus. Use focus <id>, cd <id>, or show <id> first.")
        if target["kind"] in {"project_root", "today", "dashboard", "proposals"}:
            raise TaskManagerError("No editable focus. Use focus <id>, cd <id>, or show <id> first.")
        scope = scope or self._default_scope(target)
        if scope not in {"line", "subtree"}:
            raise TaskManagerError("insert scope must be line or subtree.")
        file_path = Path(target["file_path"])
        block_uuid = target.get("block_uuid")
        line_start = int(target["line_start"])
        lines = file_path.read_text(encoding="utf-8").splitlines()
        parsed = parse_logseq_file(file_path)
        block = next((b for b in parsed.blocks if (block_uuid and b.uuid == block_uuid) or b.line_number == line_start), None)
        if not block:
            raise TaskManagerError("Editable block not found. Refresh the context and try insert again.")
        end = line_start if scope == "line" else self._subtree_end_line(block, lines)
        original = lines[line_start - 1 : end]
        leading = original[0][: len(original[0]) - len(original[0].lstrip(" \t"))] if original else ""
        return EditBuffer(
            target_id=str(target["id"]),
            target_type=target["kind"],
            scope=scope,
            source_file=file_path,
            source_range=(line_start, end),
            original_lines=original or [""],
            buffer_lines=list(original or [""]),
            cursor_row=0,
            cursor_col=len(original[0]) if original else 0,
            file_hash_at_start=self.shell.writer.sha256(file_path),
            base_indent=leading,
        )

    def render_buffer(self, buffer: EditBuffer) -> str:
        return "\n".join(
            [
                f"Target: {buffer.target_type}:{buffer.target_id}",
                f"Scope: {buffer.scope}",
                f"File: {buffer.source_file}:{buffer.source_range[0]}-{buffer.source_range[1]}",
                "",
                "Edit Buffer",
                buffer.render(),
                "",
                "Keys: Ctrl-S save | Ctrl-C/Ctrl-G cancel | :save | :cancel | Paste supported",
            ]
        )

    def preview(self, buffer: EditBuffer) -> WritePreview:
        if self.shell.writer.sha256(buffer.source_file) != buffer.file_hash_at_start:
            raise WriteError("Conflict detected: file changed since edit started.")
        old_file_lines = buffer.source_file.read_text(encoding="utf-8").splitlines()
        start, end = buffer.source_range
        new_file_lines = old_file_lines[: start - 1] + buffer.buffer_lines + old_file_lines[end:]
        diff = "".join(
            difflib.unified_diff(
                [line + "\n" for line in old_file_lines],
                [line + "\n" for line in new_file_lines],
                fromfile=str(buffer.source_file),
                tofile=str(buffer.source_file),
            )
        )
        return WritePreview(
            file_path=buffer.source_file,
            original_sha256=buffer.file_hash_at_start,
            new_text="".join(line + "\n" for line in new_file_lines),
            diff=diff,
            line_start=start,
            block_uuid=None,
        )

    def preview_text(self, buffer: EditBuffer, preview: WritePreview) -> str:
        old_non_empty = sum(1 for line in buffer.original_lines if line.strip())
        new_non_empty = sum(1 for line in buffer.buffer_lines if line.strip())
        warning = ""
        if new_non_empty + 2 < old_non_empty:
            warning = f"\nWarning: new subtree has {old_non_empty - new_non_empty} fewer non-empty lines."
        return "\n".join(
            [
                "Inline Edit Preview",
                f"Target: {buffer.target_type}:{buffer.target_id}",
                f"Scope: {buffer.scope}",
                f"File: {buffer.source_file}",
                f"Line/range: {buffer.source_range[0]}-{buffer.source_range[1]}",
                f"Line count change: {len(buffer.original_lines)} -> {len(buffer.buffer_lines)}",
                f"Rollback available: yes",
                warning.strip(),
                "",
                preview.diff[:4000],
            ]
        ).strip()

    def save(self, buffer: EditBuffer) -> str:
        if not buffer.dirty:
            return "No changes."
        try:
            preview = self.preview(buffer)
        except WriteError as exc:
            self.shell.layout_state.sync_status.mark_conflict(str(exc))
            return f"Conflict detected: file changed since edit started.\nUse :cancel, then refresh and insert again."
        preview_text = self.preview_text(buffer, preview)
        self.shell.layout_state.last_preview = preview_text
        print(preview_text)
        answer = self.shell.input_func("Apply inline edit? [y/N] ").strip().lower()
        if answer not in {"y", "yes", "是"}:
            return "Edit preview canceled. Buffer kept in memory until you :save or :cancel."
        op = self.shell._apply_direct_preview(preview, f"insert {buffer.target_id} {buffer.scope}", f"{buffer.target_type}:{buffer.target_id}")
        self.shell._resync_light(preview.file_path)
        self.shell.layout_state.sync_status.mark_write_success(str(preview.file_path), preview.line_start, op.id)
        return f"Inline edit saved to {preview.file_path}:{preview.line_start} (op #{op.id})\nundo: undo {op.id}"

    def _line_mode_loop(self, buffer: EditBuffer) -> str:
        print(self.render_buffer(buffer))
        while True:
            try:
                line = self.shell.input_func("-- INSERT -- ").rstrip("\n")
            except (EOFError, KeyboardInterrupt):
                line = ":cancel"
            if line in {":cancel", "\x03", "\x07"}:
                if buffer.dirty:
                    answer = self.shell.input_func("Discard unsaved changes? [y/N] ").strip().lower()
                    if answer not in {"y", "yes", "是"}:
                        continue
                return "Edit canceled. No file changes."
            if line in {":save", "\x13"}:
                return self.save(buffer)
            if line == ":show":
                print(self.render_buffer(buffer))
                continue
            if line == ":left":
                buffer.move_left()
            elif line == ":right":
                buffer.move_right()
            elif line == ":up":
                buffer.move_up()
            elif line == ":down":
                buffer.move_down()
            elif line == ":home":
                buffer.home()
            elif line == ":end":
                buffer.end()
            elif line == ":backspace":
                buffer.backspace()
            elif line == ":delete":
                buffer.delete()
            elif line.startswith(":set "):
                buffer.set_text(line[5:])
            else:
                buffer.paste(line)
                if "\n" not in line:
                    buffer.enter()
            self.shell.layout_state.sync_status.mark_buffer(buffer.dirty)
            self.shell.layout_state.last_preview = self.render_buffer(buffer)

    def _parse_args(self, args: list[str]) -> tuple[Optional[str], Optional[str]]:
        scope = None
        target = None
        for arg in args:
            if arg in {"line", "subtree"}:
                scope = arg
            else:
                target = arg
        return target, scope

    def _resolve_edit_target(self, target_ref: Optional[str]) -> Optional[dict]:
        if target_ref:
            if self.shell.context.project_ref:
                service = ProjectTreeService(self.shell.conn, self.shell.settings)
                tree = service.build(self.shell.context.project_ref, detail=True)
                node = service.find_node(tree.get("tree", []), target_ref)
                if node and node.get("location", {}).get("line_start"):
                    loc = node["location"]
                    return {"kind": "project_node", "id": node["id"], "file_path": loc.get("file_path"), "line_start": loc.get("line_start"), "block_uuid": loc.get("block_uuid")}
            target = self.shell.resolve_target(target_ref, allow_types={"task", "idea", "mini_project", "reference", "resource"})
            if target:
                obj = target["object"]
                return {"kind": obj["object_type"], "id": obj["id"], "file_path": obj.get("file_path"), "line_start": obj.get("line_start"), "block_uuid": obj.get("block_uuid")}
            return None
        focus = self.shell.layout_state.current_focus
        if focus:
            return self._resolve_edit_target(focus)
        if self.shell.context.current_object_id:
            return self._resolve_edit_target(str(self.shell.context.current_object_id))
        if self.shell.context.project_node_id and self.shell.context.project_ref:
            return self._resolve_edit_target(self.shell.context.project_node_id)
        if self.shell.context.mini_ref:
            return self._resolve_edit_target(str(self.shell.context.mini_ref))
        if self.shell.context.path in {"/today", "/dashboard", "/proposals"}:
            return {"kind": self.shell.context.path.strip("/")}
        if self.shell.context.project_ref and not self.shell.context.project_node_id:
            return {"kind": "project_root"}
        return None

    def _default_scope(self, target: dict) -> str:
        if target.get("kind") in {"task", "idea", "reference", "resource", "result"}:
            return "line"
        return "subtree"

    def _subtree_end_line(self, block, lines: list[str]) -> int:
        end = block.line_number
        for candidate in block.descendants():
            end = max(end, candidate.line_number)
        while end < len(lines) and self._is_property_or_continuation(lines[end], block.indent):
            end += 1
        return end

    def _is_property_or_continuation(self, line: str, parent_indent: int) -> bool:
        if not line.strip():
            return True
        return indent_level(line) > parent_indent and not line.lstrip(" \t").startswith("-")
