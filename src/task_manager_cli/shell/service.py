import json
import shlex
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from task_manager_cli.adapters.logseq.adapter import LogseqAdapter
from task_manager_cli.adapters.logseq.extractors import semantic_marker
from task_manager_cli.adapters.logseq.parser import parse_logseq_file
from task_manager_cli.clarify.service import BASIC_QUESTIONS, ClarifyService, proposal_table
from task_manager_cli.config.settings import Settings
from task_manager_cli.core.enums import ProposalType
from task_manager_cli.core.errors import ConfigError, NotFoundError, TaskManagerError
from task_manager_cli.ingest.sync import SyncService
from task_manager_cli.ingest.merger import Merger
from task_manager_cli.output.colors import color_status, color_task_markers, use_color
from task_manager_cli.projects.tree import LABEL_BY_NODE_TYPE, ProjectTreeService
from task_manager_cli.proposals.service import ProposalService
from task_manager_cli.providers.base import DryRunProvider, provider_from_settings
from task_manager_cli.reviews.service import ReviewSessionService
from task_manager_cli.projects.quality import ProjectQualityService
from task_manager_cli.shell.completion import ShellCompleter
from task_manager_cli.shell.inventory import DEFAULT_LIMIT, build_inventory
from task_manager_cli.storage.repositories import Repository
from task_manager_cli.writes.logseq_writer import LogseqWriter, WritePreview


ROOTS = {"today", "dashboard", "inbox", "waiting", "someday", "ideas", "projects", "mini", "reviews", "proposals"}

QUICK_QUESTIONS = [
    {"id": "handling", "text": "你希望如何处理这个条目？行动 / 等待 / 想法 / 资源 / 丢弃 / 稍后"},
]
STANDARD_QUESTIONS = [
    {"id": "value", "text": "这个条目现在还有价值吗？"},
    {"id": "classification", "text": "它更像行动 / 想法 / 资源 / 等待 / 未来可能 / 已完成 / 丢弃？"},
    {"id": "next_step", "text": "如果是行动，下一步是什么？"},
]


@dataclass
class ShellContext:
    path: str = "/today"
    previous_path: Optional[str] = None
    project_ref: Optional[str] = None
    project_node_id: Optional[str] = None
    project_node_title: Optional[str] = None
    mini_ref: Optional[str] = None
    journal_date: str = field(default_factory=lambda: date.today().isoformat())
    provider: str = "mock"
    detail: bool = False
    preview: bool = False
    current_review_id: Optional[int] = None
    current_object_id: Optional[int] = None
    current_object_type: Optional[str] = None
    current_object_title: Optional[str] = None
    current_object_location: Optional[str] = None


@dataclass
class ShellOperation:
    id: int
    command: str
    kind: str
    target: str
    file_path: Optional[str] = None
    backup_path: Optional[str] = None
    proposal_id: Optional[int] = None
    created_file: bool = False
    undone: bool = False
    content: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).replace(microsecond=0).isoformat())


class HumanShellService:
    def __init__(self, conn, settings: Settings, input_func: Callable[[str], str] = input):
        self.conn = conn
        self.settings = settings
        self.repo = Repository(conn)
        self.context = ShellContext()
        self.history: List[ShellOperation] = []
        self.command_history: List[str] = []
        self.local_proposal_map: Dict[int, int] = {}
        self.input_func = input_func
        if not settings.logseq_graph_path:
            raise ConfigError("Logseq graph path is not configured.")
        self.writer = LogseqWriter(settings.logseq_graph_path)
        self.completer = ShellCompleter(self)

    def prompt(self) -> str:
        return f"ta:{self.context.path}> "

    def run_line(self, line: str) -> str:
        line = line.strip()
        if not line:
            return ""
        self._record_command(line)
        try:
            parts = shlex.split(line)
        except ValueError as exc:
            return f"Parse error: {exc}"
        if not parts:
            return ""
        command, args = parts[0], parts[1:]
        try:
            if command in {"help", "?"}:
                return self.help()
            if command in {"exit", "quit"}:
                return "__exit__"
            if command == "pwd":
                return self.context.path
            if command == "ls":
                return self.ls(args)
            if command == "cd":
                return self.cd(" ".join(args) if args else "/")
            if command == "tree":
                return self.tree(args)
            if command == "show":
                return self.show(args)
            if command == "open":
                return self.open(args)
            if command == "find":
                return self.find(" ".join(args))
            if command in {"todo", "idea", "mini", "resource"}:
                preview_only, clean_args = self._extract_preview_flag(args)
                return self.create_item(command, " ".join(clean_args), preview_only=preview_only)
            if command in {"note", "ainote", "result", "noresult"}:
                return self.append_marker(command, args)
            if command in {"doing", "done", "wait"}:
                return self.change_task_marker(command, args)
            if command == "someday":
                return self.someday(args)
            if command == "undo":
                return self.undo(args[0] if args else None)
            if command in {"history", "ops"}:
                return self.operation_history(detail="--detail" in args)
            if command == "commands":
                return self.commands()
            if command == "clear-history":
                self.command_history.clear()
                return "Command history cleared."
            if command == "where":
                return self.where(args)
            if command in {"quality", "q"}:
                return self.quality(args)
            if command == "proposals":
                return self.proposals()
            if command == "preview" and args and args[0] in {"on", "off"}:
                self.context.preview = args[0] == "on"
                return f"preview: {args[0]}"
            if command == "edit" and args:
                return self._route_edit(args)
            if command in {"accept", "reject", "preview", "apply", "supersede"}:
                return self.proposal_action(command, args)
            if command == "clarify":
                return self.clarify(args)
            if command == "provider":
                return self.provider(args)
            if command == "detail":
                return self.detail(args)
            if command == "complete":
                result = self.completer.complete_line(" ".join(args))
                return result.display or "\n".join(result.candidates) or "No completions."
            return f"Unknown command: {command}. Type `help`."
        except (TaskManagerError, ConfigError, NotFoundError, ValueError, KeyError) as exc:
            return f"Error: {exc}"

    def help(self) -> str:
        return "\n".join(
            [
                "Human Shell commands:",
                "导航: pwd, ls, cd, tree, show, open, find",
                "创建: todo, idea, mini, resource",
                "状态/成果: note, ainote, doing, done, wait, someday, result, noresult",
                "安全: preview on|off, where, history, undo [op]",
                "Proposal: proposals, accept, reject, edit, supersede, preview, apply",
                "Clarify: clarify, clarify resume|status|retry|eval|cancel",
                "质量报告: quality project-tree|mini|membership|clarify|all",
                "补全: Tab completion; fallback `complete <line>`",
                "其他: provider, commands, clear-history, detail on|off, exit",
            ]
        )

    def cd(self, target: str) -> str:
        old = self.context.path
        if target == "-":
            if not self.context.previous_path:
                return "No previous context."
            target = self.context.previous_path
        elif target == "..":
            if self.context.current_object_id:
                if self.context.project_ref:
                    project = self._object(self.context.project_ref)
                    target = f"/projects/{project['title']}"
                elif self.context.mini_ref:
                    target = "/mini"
                else:
                    target = "/"
            else:
                target = self._parent_path(self.context.path)
        else:
            object_context = self._resolve_object_context(target)
            if object_context:
                self.context.previous_path = old
                self._apply_context(object_context)
                return self.context.path
            node_context = self._resolve_project_node_context(target)
            if node_context:
                self.context.previous_path = old
                self._apply_context(node_context)
                return self.context.path
        target = self._expand_alias(target)
        if not target.startswith("/"):
            target = self._join_path(self.context.path, target)
        resolved = self._resolve_path(target)
        if not resolved:
            candidates = self._path_candidates(target)
            if candidates:
                choice = self._choose("找到多个路径候选", [{"label": item, "value": item} for item in candidates])
                if not choice:
                    return f"Path not found: {target}\nCandidates: {', '.join(candidates)}"
                resolved = self._resolve_path(choice["value"])
            if not resolved:
                return f"Path not found: {target}\nCandidates: {', '.join(candidates)}"
        self.context.previous_path = old
        self._apply_context(resolved)
        return self.context.path

    def ls(self, args: Optional[List[str]] = None) -> str:
        """List visible objects in current context, with optional filters.

        Filters: tasks, todo, doing, waiting, ideas, resources, mini, nodes, proposals, all.
        """
        args = args or []
        filter_name = args[0].lower() if args and not args[0].startswith("--") else None
        show_all = "--all" in args
        color = False if any(arg in {"--no-color", "no-color", "plain"} for arg in args) else None

        inv = build_inventory(self.conn, self.context, self.repo, self.settings)
        sections = inv.get("sections", [])
        if not sections and not inv.get("_project_title"):
            if inv.get("_note"):
                return f"Context: {inv.get('context', self.context.path)}\n{inv['_note']}"
            project_title = inv.get("_project_title")
            if project_title:
                return f"Project: {project_title}\n(empty)"
            return f"Context: {inv.get('context', self.context.path)}\n(empty)"

        lines = []
        project_title = inv.get("_project_title") or inv.get("project_node_title")
        if project_title:
            lines.append(f"Project: {project_title}")

        # Build section filter map
        section_map = {s["type"]: s for s in sections}
        note = inv.get("_attribution_note")
        fallback_section = section_map.pop("_fallback_note", None)
        note_section = section_map.pop("_note", None)

        if filter_name and filter_name != "all":
            return self._filtered_ls(filter_name, section_map, note, fallback_section, lines, show_all, color=color)

        # Default: show all sections with limits and overflow
        overflow = inv.get("overflow", {})
        for section_type, section in section_map.items():
            items = section.get("items", [])
            if not items:
                continue
            label = section.get("label", section_type)
            item_limit = None if show_all else DEFAULT_LIMIT
            shown = items[:item_limit]
            extra = len(items) - len(shown)
            lines.append(f"\n{label}:")
            lines.extend(self._format_section_items(shown, section_type, color=color))
            if extra > 0:
                lines.append(f"  ... 还有 {extra} 条，可用 ls {section_type} --all")

        if fallback_section:
            lines.append("\n当前 node 关联对象不足，以下为项目级候选：")
            f_items = fallback_section.get("items", [])
            shown = f_items[:DEFAULT_LIMIT]
            lines.extend(self._format_section_items(shown, fallback_section.get("type", ""), color=color))
            extra = len(f_items) - len(shown)
            if extra > 0:
                lines.append(f"  ... 还有 {extra} 条")

        return "\n".join(lines) if lines else "No items."

    def _format_section_items(self, items: List[dict], section_type: str, *, color: Optional[bool] = None) -> List[str]:
        """Format inventory items for display."""
        lines = []
        color_enabled = use_color(color)
        for item in items:
            iid = item.get("id", "?")
            title = item.get("title", "")
            status = item.get("status") or ""
            label = item.get("label") or ""
            src = item.get("source_location", "")
            item_type = item.get("type", "")
            attribution = f"  [{item.get('attribution')}]" if item.get("attribution") else ""

            if item_type == "node":
                label_str = f" [{label}]" if label else ""
                lines.append(f"  [{iid}] {label_str} {title}")
            elif item_type == "proposal":
                pt = item.get("proposal_type", "")
                risk = item.get("risk", "")
                pid = item.get("proposal_id", iid)
                lines.append(f"  [{iid}] proposal:{pid} {pt} {risk}")
            elif item_type in ("reference", "resource"):
                lines.append(f"  #{iid} RESOURCE {title}  ({src}){attribution}")
            elif item_type == "idea":
                lines.append(f"  #{iid} IDEA {title}  ({src}){attribution}")
            elif item_type == "result":
                lines.append(f"  #{iid} RESULT {title}  ({src}){attribution}")
            elif item_type == "record":
                lines.append(f"  #{iid} {color_task_markers(title, color_enabled)}  ({src}){attribution}")
            elif item_type in ("task", "mini_project"):
                marker = status.upper() if status else item_type.upper()
                marker = color_status(marker, color_enabled)
                lines.append(f"  #{iid} {marker} {title}  ({src}){attribution}")
            elif item_type == "project":
                lines.append(f"  #{iid} {title}")
            else:
                lines.append(f"  [#{iid}] {item_type} {title}")
        return lines

    def _filtered_ls(
        self,
        filter_name: str,
        section_map: dict,
        note,
        fallback_section,
        header_lines: List[str],
        show_all: bool = False,
        *,
        color: Optional[bool] = None,
    ) -> str:
        """Handle filtered ls output."""
        lines = list(header_lines)

        # Filter mapping
        filter_to_sections = {
            "tasks": ["actions"],
            "todo": ["actions"],
            "doing": ["actions"],
            "waiting": ["actions", "waiting"],
            "ideas": ["ideas"],
            "resources": ["resources"],
            "mini": ["mini_projects"],
            "nodes": ["nodes"],
            "proposals": ["proposals"],
            "projects": ["projects"],
            "active": ["actions"],
            "journal": ["journal"],
            "exposed": ["exposed"],
            "results": ["results"],
            "notes": ["notes"],
            "done": ["actions"],
            "reviews": ["reviews"],
        }

        target_sections = filter_to_sections.get(filter_name, [])
        if not target_sections:
            return f"Unknown filter: {filter_name}. Try: tasks, todo, doing, waiting, done, ideas, resources, mini, nodes, projects, journal, exposed, results, proposals, reviews, all"

        # Status filtering for todo/doing/waiting
        status_filter = None
        if filter_name in ("todo", "doing", "waiting", "done"):
            status_filter = filter_name

        found = 0
        for stype in target_sections:
            section = section_map.get(stype)
            if not section:
                continue
            items = section.get("items", [])
            if status_filter:
                items = [it for it in items if (it.get("status") or "").lower() == status_filter]
            if not items:
                continue
            label = section.get("label", stype)
            lines.append(f"\n{label}:")
            limit = None if show_all else DEFAULT_LIMIT
            shown = items[:limit]
            lines.extend(self._format_section_items(shown, stype, color=color))
            found += 1
            extra = len(items) - len(shown)
            if extra > 0:
                lines.append(f"  ... 还有 {extra} 条，可用 ls {filter_name} --all")

        if not found:
            return "\n".join(lines) + f"\nNo {filter_name} found."

        return "\n".join(lines)

    def tree(self, args: Optional[List[str]] = None) -> str:
        args = args or []
        if not self.context.project_ref:
            if self.context.mini_ref or self.context.current_object_id:
                if any(arg in {"raw", "show"} for arg in args):
                    return self.show([])
                mini_tree = self._tree_for_current_mini(args)
                if mini_tree:
                    return mini_tree
                return "tree is available inside /projects/<project>. 可使用 show 查看当前对象的完整 Logseq 子树。"
            return "tree is available inside /projects/<project>."
        service = ProjectTreeService(self.conn, self.settings)
        detail = self.context.detail or "detail" in args
        color = False if any(arg in {"no-color", "plain"} for arg in args) else None
        if any(arg in {"raw", "show"} for arg in args):
            if self.context.project_node_id:
                rendered = service.raw_subtree_for_node(self.context.project_ref, self.context.project_node_id, detail=detail, color=color)
                return rendered or "Raw subtree not found."
            return "tree raw is available inside a project node context. Use show for the current raw subtree."
        tree = service.build(self.context.project_ref, detail=detail)
        return service.render_markdown(tree, detail=detail, color=color, root_node_id=self.context.project_node_id)

    def show(self, args: List[str]) -> str:
        if not args and self.context.project_node_id and self.context.project_ref:
            return self._show_project_node_context()
        if not args and self.context.mini_ref:
            args = [str(self.context.mini_ref)]
        if not args and self.context.current_object_id:
            args = [str(self.context.current_object_id)]
        if not args:
            return "Usage: show <object-id>|proposal <id>|review <id>"
        if args[0] == "proposal" and len(args) > 1:
            return json.dumps(ProposalService(self.conn, self.settings).get(self._proposal_id(args[1])), ensure_ascii=False, indent=2)
        if args[0] == "review" and len(args) > 1:
            return json.dumps(ReviewSessionService(self.conn).show(int(args[1])), ensure_ascii=False, indent=2)
        if self.context.project_ref:
            node_output = self._show_project_node_ref(" ".join(args))
            if node_output:
                return node_output
        target = self.resolve_target(" ".join(args), allow_types={"project", "task", "idea", "mini_project", "reference", "resource"})
        obj = target.get("object") if target else None
        if not obj:
            return f"Object not found: {' '.join(args)}"
        if obj["object_type"] == "mini_project":
            lines = self._show_mini_header(obj)
        else:
            lines = [f"#{obj['id']} {obj['object_type']} {obj.get('status') or ''} {obj['title']}", f"{obj.get('file_path')}:{obj.get('line_start') or ''}"]
        metadata = obj.get("metadata") if isinstance(obj.get("metadata"), dict) else {}
        if metadata.get("index_status") == "updated_by_shell_writeback":
            lines.append("index: updated by shell writeback")
        duplicates = self.repo.duplicate_objects_for_source_location(int(obj["id"]))
        if duplicates:
            ids = ", ".join(f"#{item['id']}" for item in duplicates[:5])
            lines.append(f"duplicates: hidden same source location {ids}")
        block = ProjectTreeService(self.conn, self.settings).find_block_for_object(obj)
        if block:
            lines.extend(
                [
                    "",
                    "当前内容：",
                    ProjectTreeService(self.conn, self.settings).render_raw_subtree(block, detail=self.context.detail),
                ]
            )
        return "\n".join(lines)

    def _show_mini_header(self, obj: Dict[str, Any]) -> List[str]:
        project = self._project_for_file(obj.get("file_path"))
        lines = [
            f"Mini Project #{obj['id']}",
            f"标题：{obj['title']}",
        ]
        if project:
            lines.append(f"项目：{project['title']}")
        lines.append(f"位置：{obj.get('file_path')}:{obj.get('line_start') or ''}")
        if project:
            lines.extend(["", "上下文：", f"Project: {project['title']}"])
        return lines

    def _show_project_node_context(self) -> str:
        return self._show_project_node_ref(self.context.project_node_id or "") or "Project node not found."

    def _show_project_node_ref(self, node_ref: str) -> Optional[str]:
        if not self.context.project_ref or not node_ref:
            return None
        service = ProjectTreeService(self.conn, self.settings)
        tree = service.build(self.context.project_ref, detail=True)
        node = service.find_node(tree.get("tree", []), node_ref)
        if not node:
            matched = self._match_project_node(self.context.project_ref, [node_ref])
            node = service.find_node(tree.get("tree", []), matched["id"]) if matched else None
        if not node:
            return None
        block = service.find_block(self.context.project_ref, node["id"])
        if not node or not block:
            return None
        project = tree["project"]
        loc = node.get("location", {})
        label = LABEL_BY_NODE_TYPE.get(node.get("node_type"), node.get("node_type"))
        lines = [
            f"Project Node {node['id']}",
            f"类型：{label}",
            f"项目：{project['title']}",
            f"位置：{loc.get('file_path') or project.get('file_path')}:{loc.get('line_start') or ''}",
            "",
            "上级上下文：",
            f"Project: {project['title']}",
        ]
        context = service.render_block_context(block)
        if context and context != "(root)":
            lines.append(context)
        lines.extend(["", "当前内容：", service.render_raw_subtree(block, detail=self.context.detail)])
        return "\n".join(lines)

    def _tree_for_current_mini(self, args: List[str]) -> Optional[str]:
        if not self.context.mini_ref:
            return None
        obj = self._object(self.context.mini_ref)
        project = self._project_for_file(obj.get("file_path"))
        if not project:
            return None
        service = ProjectTreeService(self.conn, self.settings)
        detail = self.context.detail or "detail" in args
        color = False if any(arg in {"no-color", "plain"} for arg in args) else None
        tree = service.build(str(project["id"]), detail=detail)
        return service.render_markdown(tree, detail=detail, color=color, root_node_id=obj.get("source_item_id"))

    def _project_for_file(self, file_path: Optional[str]) -> Optional[Dict[str, Any]]:
        if not file_path:
            return None
        rows = self.repo.list_objects("project", limit=100000)
        for row in rows:
            if row.get("file_path") == file_path:
                return row
        return None

    def open(self, args: List[str]) -> str:
        if not args and self.context.current_object_id:
            args = [str(self.context.current_object_id)]
        if not args:
            return "Usage: open <object-id>"
        target = self.resolve_target(" ".join(args), allow_types={"project", "task", "idea", "mini_project", "reference", "resource"})
        if not target:
            return f"Object not found: {args[0]}"
        obj = target["object"]
        return f"{obj.get('file_path')}:{obj.get('line_start') or ''}\nblock_path: {obj.get('block_path') or []}"

    def find(self, query: str) -> str:
        parts = shlex.split(query) if query else []
        global_only = "--global" in parts
        include_all = "--all" in parts
        terms = [part for part in parts if part not in {"--global", "--all"}]
        query = " ".join(terms)
        if not query:
            return "Usage: find <keyword>"
        if global_only:
            rows = self._search_objects(query, limit=20)
            return self._format_find_rows(rows, prefix="[global]")
        context_ids = self._context_object_ids()
        context_rows = self._search_objects(query, object_ids=context_ids, limit=20) if context_ids else []
        if include_all:
            global_rows = [row for row in self._search_objects(query, limit=20) if int(row["id"]) not in {int(item["id"]) for item in context_rows}]
            lines = ["Context results:"]
            lines.append(self._format_find_rows(context_rows) if context_rows else "No context matches.")
            lines.append("\nGlobal results:")
            lines.append(self._format_find_rows(global_rows, prefix="[global]") if global_rows else "No global matches.")
            return "\n".join(lines)
        if context_rows:
            return self._format_find_rows(context_rows)
        rows = self._search_objects(query, limit=20)
        if not rows:
            return "No matches."
        return "No context matches. Global matches:\n" + self._format_find_rows(rows, prefix="[global]")

    def _search_objects(self, query: str, object_ids: Optional[List[int]] = None, limit: int = 20) -> List[Dict[str, Any]]:
        like = f"%{query}%"
        params: List[Any] = [like, like]
        id_sql = ""
        if object_ids is not None:
            if not object_ids:
                return []
            id_sql = " AND o.id IN (" + ",".join("?" for _ in object_ids) + ")"
            params.extend(object_ids)
        rows = self.conn.execute(
            f"""
            SELECT o.*, l.file_path, l.page_name, l.journal_date, l.line_start
            FROM objects o LEFT JOIN locations l ON l.id=o.canonical_location_id
            WHERE (o.title LIKE ? OR o.metadata_json LIKE ?) {id_sql}
            ORDER BY o.id DESC LIMIT 20
            """,
            (*params,),
        ).fetchall()
        return self._dedupe_rows([self._object_row(row) for row in rows])[:limit]

    def _context_object_ids(self) -> List[int]:
        if self.context.current_object_id:
            ids = [int(self.context.current_object_id)]
            for record in self.repo.records_for_object(int(self.context.current_object_id), limit=100):
                if record.get("role") != "definition" and record.get("id"):
                    pass
            return ids
        inv = build_inventory(self.conn, self.context, self.repo, self.settings)
        ids: List[int] = []
        for section in inv.get("sections", []):
            for item in section.get("items", []):
                if item.get("type") in {"task", "idea", "mini_project", "reference", "resource", "project"}:
                    try:
                        ids.append(int(item.get("object_id") or item["id"]))
                    except Exception:
                        continue
        return sorted(set(ids))

    def _dedupe_rows(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        seen = set()
        result = []
        for row in rows:
            key = (row.get("file_path"), row.get("line_start"), row.get("object_type"), row.get("title"))
            if key in seen:
                continue
            seen.add(key)
            result.append(row)
        return result

    def _format_find_rows(self, rows: List[Dict[str, Any]], prefix: str = "") -> str:
        if not rows:
            return "No matches."
        lines = []
        duplicate_count = 0
        for row in rows:
            duplicates = self.repo.duplicate_objects_for_source_location(int(row["id"]))
            duplicate_count += len(duplicates)
            mark = f"{prefix} " if prefix else ""
            lines.append(f"- {mark}#{row['id']} {row['object_type']} {row['title']} ({row.get('page_name')}:{row.get('line_start') or ''})")
        if duplicate_count:
            lines.append(f"duplicate source-location objects hidden: {duplicate_count}")
        return "\n".join(lines)

    def create_item(self, kind: str, text: str, preview_only: bool = False) -> str:
        if not text:
            return f"Usage: {kind} \"text\""
        content = {
            "todo": f"TODO {text}",
            "idea": f"**[想法]** {text}",
            "mini": f"**[小任务]** {text}",
            "resource": f"**[资源]** {text}",
        }[kind]
        if self.context.path == "/inbox" and kind == "todo":
            content = f"{content} #inbox"
        preview, target = self._preview_for_context(kind, content)
        if preview_only:
            return self._location_preview(kind, preview, target, content)
        if self.context.preview and not self._confirm(self._location_preview(kind, preview, target, content) + "\n确认写入？ [y/N] "):
            return "Cancelled."
        op = self._apply_direct_preview(preview, f"{kind} {text}", target)
        self._resync_light(preview.file_path)
        return f"{kind} written to {target} (op #{op.id})\nundo: undo {op.id}"

    def append_marker(self, command: str, args: List[str]) -> str:
        if self.context.current_object_id and len(args) >= 1:
            target_ref = str(self.context.current_object_id)
            text_args = args
        elif len(args) >= 2:
            target_ref = args[0]
            text_args = args[1:]
        else:
            return f"Usage: {command} <object-id> \"text\""
        marker = {"note": "**[注]**", "ainote": "**[AI注]**", "result": "**[成果]**", "noresult": "**[无成果]**"}[command]
        target = self.resolve_target(target_ref, allow_types={"task", "idea", "mini_project", "project", "reference", "resource"})
        if not target:
            return f"Object not found: {target_ref}"
        obj = target["object"]
        object_id = int(obj["id"])
        content = " ".join(text_args)
        preview = self.writer.preview_append_marker_child(Path(obj["file_path"]), marker, content, block_uuid=obj.get("block_uuid"), line_start=obj.get("line_start"))
        if self.context.preview and not self._confirm(self._location_preview(command, preview, f"object:{object_id}", f"{marker} {content}") + "\n确认写入？ [y/N] "):
            return "Cancelled."
        op = self._apply_direct_preview(preview, f"{command} {target_ref}", f"object:{object_id}")
        self._resync_light(preview.file_path, changed_object_id=object_id)
        return f"{command} appended to #{object_id} (op #{op.id})"

    def change_task_marker(self, command: str, args: List[str]) -> str:
        if not args and self.context.current_object_id:
            args = [str(self.context.current_object_id)]
        if not args:
            return f"Usage: {command} <object-id> [reason]"
        target = self.resolve_target(args[0], allow_types={"task"})
        if not target:
            return f"Object not found: {args[0]}"
        obj = target["object"]
        object_id = int(obj["id"])
        marker = {"doing": "DOING", "done": "DONE", "wait": "WAITING"}[command]
        preview = self.writer.preview_update_task_marker(Path(obj["file_path"]), marker, block_uuid=obj.get("block_uuid"), line_start=obj.get("line_start"))
        if self.context.preview and not self._confirm(self._location_preview(command, preview, f"object:{object_id}", marker) + "\n确认写入？ [y/N] "):
            return "Cancelled."
        op = self._apply_direct_preview(preview, f"{command} {args[0]}", f"object:{object_id}")
        self.repo.update_object_after_writeback(object_id, status=marker.lower(), dirty_reason="task_marker")
        extra = ""
        if command == "wait" and len(args) > 1:
            note_preview = self.writer.preview_append_marker_child(Path(obj["file_path"]), "**[注]**", " ".join(args[1:]), block_uuid=obj.get("block_uuid"), line_start=obj.get("line_start"))
            note_op = self._apply_direct_preview(note_preview, f"wait-note {args[0]}", f"object:{object_id}")
            extra = f"; reason note op #{note_op.id}"
        self._resync_light(preview.file_path, changed_object_id=object_id)
        hint = ""
        if command == "done" and not self._has_result_marker(object_id):
            hint = f"\n该条目已完成，但没有成果标注。可输入 result {object_id} \"...\" 或 noresult {object_id} \"...\""
        return f"#{object_id} -> {color_status(marker, use_color())} (op #{op.id}{extra}){hint}"

    def someday(self, args: List[str]) -> str:
        if not args:
            return "Usage: someday <object-id>"
        target = self.resolve_target(args[0], allow_types={"task", "idea", "mini_project", "project"})
        if not target:
            return f"Object not found: {args[0]}"
        obj = target["object"]
        object_id = int(obj["id"])
        preview = self.writer.preview_append_marker_child(Path(obj["file_path"]), "**[注]**", "#someday", block_uuid=obj.get("block_uuid"), line_start=obj.get("line_start"))
        op = self._apply_direct_preview(preview, f"someday {args[0]}", f"object:{object_id}")
        self._resync_light(preview.file_path, changed_object_id=object_id)
        return f"#someday appended to #{object_id} (op #{op.id})"

    def undo(self, ref: Optional[str] = None) -> str:
        candidates = list(reversed(self.history)) if ref in {None, "last"} else [op for op in self.history if str(op.id) == str(ref)]
        if not candidates:
            return "Nothing to undo." if ref in {None, "last"} else f"Operation not found: {ref}"
        for op in candidates:
            if op.undone:
                if ref:
                    return f"Operation #{op.id} is already undone."
                continue
            if op.proposal_id:
                result = ProposalService(self.conn, self.settings).rollback(op.proposal_id)
                self.conn.commit()
                op.undone = True
                return f"Rolled back proposal {op.proposal_id}: {result['status']}"
            if op.backup_path and op.file_path and Path(op.backup_path).is_file():
                self.writer.restore_backup(Path(op.backup_path), Path(op.file_path))
                op.undone = True
                self._resync_light(Path(op.file_path))
                return f"Undone op #{op.id}: {op.command}"
            if op.created_file and op.file_path:
                Path(op.file_path).unlink(missing_ok=True)
                op.undone = True
                self._resync_light(Path(op.file_path))
                return f"Undone op #{op.id}: {op.command}"
            return f"Cannot undo op #{op.id}: missing rollback information."
        return "Nothing to undo."

    def operation_history(self, detail: bool = False) -> str:
        if not self.history:
            return "No operations yet."
        lines = ["最近操作"]
        for op in self.history:
            status = "undone" if op.undone else "applied"
            lines.append(f"[{op.id}] {op.kind} {op.command} status={status} undo={'no' if op.undone else 'available'}")
            if detail:
                lines.append(f"    target: {op.target}")
                if op.file_path:
                    lines.append(f"    file: {op.file_path}")
                if op.content:
                    lines.append(f"    content: {op.content}")
        return "\n".join(lines)

    def commands(self) -> str:
        return "\n".join(f"{index + 1}. {item}" for index, item in enumerate(self.command_history)) or "No command history."

    def proposals(self) -> str:
        proposals = ProposalService(self.conn, self.settings).list(status="suggested", limit=50)
        proposals += ProposalService(self.conn, self.settings).list(status="accepted", limit=50)
        proposals = sorted(proposals, key=lambda proposal: proposal["id"])
        self.local_proposal_map = {index + 1: proposal["id"] for index, proposal in enumerate(proposals)}
        if not proposals:
            return "No pending proposals."
        lines = []
        for index, proposal in enumerate(proposals, 1):
            lines.append(f"{index}. #{proposal['id']} {proposal['status']} {proposal['risk']} {proposal['proposal_type']} - {proposal['title']}")
        return "\n".join(lines)

    def proposal_action(self, command: str, args: List[str]) -> str:
        if not args:
            return f"Usage: {command} <proposal-id|local-number|accepted|low>"
        service = ProposalService(self.conn, self.settings)
        if command == "accept" and args[0] == "low":
            accepted = []
            for proposal in service.list(status="suggested", limit=200):
                if proposal["risk"] == "low":
                    service.accept(proposal["id"])
                    accepted.append(proposal["id"])
            self.conn.commit()
            return f"Accepted low risk proposals: {accepted}"
        if command == "apply" and args[0] == "accepted":
            applied = []
            for proposal in service.list(status="accepted", limit=200):
                if proposal["risk"] == "high":
                    continue
                result = service.apply(proposal["id"], confirmed=True)
                applied.append(result["proposal_id"])
                self._record_operation(f"apply proposal {proposal['id']}", "proposal_apply", f"proposal:{proposal['id']}", proposal_id=proposal["id"])
            self.conn.commit()
            self._resync()
            return f"Applied accepted proposals: {applied}"
        proposal_id = self._proposal_id(args[0])
        if command == "accept":
            service.accept(proposal_id)
            self.conn.commit()
            return f"Accepted proposal {proposal_id}."
        if command == "reject":
            service.reject(proposal_id)
            self.conn.commit()
            return f"Rejected proposal {proposal_id}."
        if command == "preview":
            data = service.preview(proposal_id)
            self.conn.commit()
            return data.get("preview_diff") or json.dumps(data, ensure_ascii=False, indent=2)
        if command == "apply":
            result = service.apply(proposal_id, confirmed=True)
            self.conn.commit()
            self._record_operation(f"apply proposal {proposal_id}", "proposal_apply", f"proposal:{proposal_id}", proposal_id=proposal_id)
            self._resync()
            return f"Applied proposal {proposal_id}: {result['status']}"
        if command == "edit":
            if len(args) < 3:
                return "Usage: edit <proposal> content|reason|risk|marker <value>"
            field, value = args[1], " ".join(args[2:])
            kwargs: Dict[str, Any] = {}
            if field == "content":
                kwargs["content"] = value
            elif field in {"reason", "rationale"}:
                kwargs["rationale"] = value
            elif field == "risk":
                kwargs["risk"] = value
            elif field == "marker":
                kwargs["marker"] = value
            else:
                return "Editable fields: content, reason, risk, marker"
            edited = service.edit(proposal_id, **kwargs)
            self.conn.commit()
            return f"Edited proposal {proposal_id}: {field}"
        if command == "supersede":
            if len(args) < 2:
                return "Usage: supersede <old> <new>"
            service.supersede(proposal_id, self._proposal_id(args[1]))
            self.conn.commit()
            return f"Superseded proposal {proposal_id} with {self._proposal_id(args[1])}."
        return f"Unsupported proposal command: {command}"

    # ── edit routing ──────────────────────────────────────────────────────

    def _route_edit(self, args: List[str]) -> str:
        """Route edit command: edit task ... or edit proposal ... or edit <N> ..."""
        if not args:
            return "Usage: edit task|proposal <target> <field> <value>"

        if args[0] == "task":
            return self._edit_task(args[1:])
        if args[0] in {"title", "content", "status"} and self.context.current_object_type == "task":
            return self._edit_task([str(self.context.current_object_id), *args])
        if args[0] == "proposal":
            return self.proposal_action("edit", args[1:])

        # Backward compatibility: edit <N> content|reason|risk|marker <value>
        first = args[0]
        if first.isdigit():
            num = int(first)
            pid_exists = num in self.local_proposal_map
            obj_exists = self.repo.resolve_object_id(first) is not None
            field = args[1].lower() if len(args) >= 2 else ""

            if pid_exists and obj_exists:
                proposal_only = {"reason", "risk", "marker"}
                task_only = {"title", "status"}
                if field in proposal_only:
                    return self.proposal_action("edit", args)
                if field in task_only:
                    return self._edit_task(args)
                # content overlaps both; show ambiguity for safety
                if field == "content":
                    return self.proposal_action("edit", args)  # backwards compat
                return (
                    f"歧义：{first} 同时匹配 Proposal 和对象。\n"
                    f"请使用 edit proposal {first} ... 或 edit task {first} ..."
                )
            if pid_exists:
                return self.proposal_action("edit", args)
            if obj_exists:
                return self._edit_task(args)
            return f"Proposal [{first}] 不存在。请先运行 proposals 或 ls proposals 查看当前编号。"

        return f"Unknown edit target: {args[0]}. Use edit task ... or edit proposal ..."

    def _edit_task(self, args: List[str]) -> str:
        if not args:
            return "Usage: edit task <target> title|content|status <value>"
        if len(args) < 3:
            return "Usage: edit task <target> title|content|status <value>"
        target_ref = args[0]
        field = args[1].lower()
        value = " ".join(args[2:])

        if field == "title":
            return self._edit_task_title(target_ref, value)
        if field == "content":
            return self._edit_task_content(target_ref, value)
        if field == "status":
            return self._edit_task_status(target_ref, value)
        return f"Unknown field: {field}. Supported: title, content, status"

    def _edit_task_title(self, target_ref: str, new_title: str) -> str:
        if not new_title:
            return "Usage: edit task <target> title \"new title\""
        target = self.resolve_target(target_ref, allow_types={"task"})
        if not target:
            return f"Task not found: {target_ref}"
        obj = target["object"]
        object_id = int(obj["id"])

        preview = self.writer.preview_modify_block_text(
            Path(obj["file_path"]),
            block_uuid=obj.get("block_uuid"),
            line_start=obj.get("line_start"),
            new_text=new_title,
            preserve_task_marker=True,
        )
        # Always show preview for block text modification
        print(self._location_preview("edit task title", preview, f"object:{object_id}", new_title))
        if not self._confirm("Apply this change? [y/N] "):
            return "Cancelled."
        op = self._apply_direct_preview(preview, f"edit task {target_ref} title", f"object:{object_id}")
        self.repo.update_object_after_writeback(object_id, title=new_title, dirty_reason="task_title")
        self._resync_light(preview.file_path, changed_object_id=object_id)
        return f"Task #{object_id} title updated (op #{op.id})\nundo: undo {op.id}"

    def _edit_task_content(self, target_ref: str, new_content: str) -> str:
        # This round: equivalent to title (preserves task marker)
        return self._edit_task_title(target_ref, new_content)

    def _edit_task_status(self, target_ref: str, new_status: str) -> str:
        marker_map = {"todo": "TODO", "doing": "DOING", "done": "DONE", "waiting": "WAITING"}
        marker = marker_map.get(new_status.lower())
        if not marker:
            return f"Unknown status: {new_status}. Supported: todo, doing, waiting, done"
        target = self.resolve_target(target_ref, allow_types={"task"})
        if not target:
            return f"Task not found: {target_ref}"
        obj = target["object"]
        object_id = int(obj["id"])

        preview = self.writer.preview_update_task_marker(
            Path(obj["file_path"]), marker,
            block_uuid=obj.get("block_uuid"), line_start=obj.get("line_start"),
        )
        if self.context.preview and not self._confirm(
            self._location_preview("edit task status", preview, f"object:{object_id}", marker)
            + "\n确认写入？ [y/N] "
        ):
            return "Cancelled."
        op = self._apply_direct_preview(preview, f"edit task {target_ref} status {new_status}", f"object:{object_id}")
        self.repo.update_object_after_writeback(object_id, status=marker.lower(), dirty_reason="task_marker")
        self._resync_light(preview.file_path, changed_object_id=object_id)
        return f"Task #{object_id} -> {color_status(marker, use_color())} (op #{op.id})\nundo: undo {op.id}"

    # ── clarify ───────────────────────────────────────────────────────────

    def clarify(self, args: List[str] = None) -> str:
        args = args or []
        mode = "standard"
        if args and args[0] in {"quick", "standard", "deep", "ai"}:
            mode = args[0]
            args = args[1:]
        elif len(args) >= 2 and args[0] == "mode" and args[1] in {"quick", "standard", "deep", "ai"}:
            mode = args[1]
            args = args[2:]
        reviews = ReviewSessionService(self.conn)
        if args and args[0] == "status":
            return self._clarify_status()
        if args and args[0] == "eval":
            if not self.context.current_review_id:
                return "No current clarify review."
            data = ClarifyService(self.conn, self.settings).eval_review(self.context.current_review_id)
            return "\n".join([f"Clarify review #{self.context.current_review_id}", f"proposals: {data['generated_proposal_count']}", f"failed: {data['provider_failed_count']}", f"types: {data['proposal_type_distribution']}"])
        if args and args[0] == "cancel":
            if not self.context.current_review_id:
                return "No current clarify review."
            reviews.set_status(self.context.current_review_id, "cancelled")
            self.conn.commit()
            return f"Clarify cancelled: review #{self.context.current_review_id}"
        if args and args[0] == "retry":
            if not self.context.current_review_id:
                return "No current clarify review."
            return self._run_clarify_review(self.context.current_review_id, mode=mode)
        if args and args[0] == "resume":
            if not self.context.current_review_id:
                open_review = self._latest_shell_review()
                if not open_review:
                    return "No shell clarify review to resume."
                self.context.current_review_id = int(open_review["id"])
            return self._run_clarify_review(self.context.current_review_id, mode=mode)
        ids = self._candidate_ids_for_context(limit=10)
        if not ids:
            return "No clarify candidates in this context."
        review_id = reviews.start(f"shell:{self.context.path}", item_refs=ids, title=f"Shell clarify {self.context.path}")
        self.context.current_review_id = review_id
        return self._run_clarify_review(review_id, mode=mode)

    def _run_clarify_review(self, review_id: int, mode: str = "standard") -> str:
        reviews = ReviewSessionService(self.conn)
        generated: List[int] = []
        previews: List[Dict[str, Any]] = []
        provider = provider_from_settings(self.settings, override_name=self.context.provider) if self.context.provider != "off" else None
        clarify_service = ClarifyService(self.conn, self.settings)
        for item in reviews.pending_clarify_items(review_id):
            obj = self.repo.get_object(int(item["object_id"]))
            print(f"\n条目 #{obj['id']}：{obj['title']}")
            print(f"当前状态：{obj.get('status') or ''}")
            print(f"来源：{obj.get('page_name') or ''}:{obj.get('line_start') or ''}")
            answers = []
            questions = self._clarify_questions(mode)
            if mode == "ai" and provider is not None:
                payload = clarify_service.build_payload(review_id, item["id"], obj, "请生成最多 3 个必要问题。", project_ref=self.context.project_ref)
                payload["clarify_mode"] = "ai_questions"
                if isinstance(provider, DryRunProvider):
                    previews.append(provider.preview_payload(payload))
                    questions = QUICK_QUESTIONS
                else:
                    result = provider.generate(payload)
                    questions = [
                        {"id": f"ai_{idx + 1}", "text": q.get("question") or str(q)}
                        for idx, q in enumerate((result.questions_for_user or [])[:3])
                    ] or QUICK_QUESTIONS
                reviews.update_item_clarify(item["id"], {"status": "asked", "provider": self.context.provider, "questions": questions, "ai_questions_only": True})
            for index, question in enumerate(questions, 1):
                answer = self.input_func(f"问题 {index}：{question['text']}\n> ").strip()
                if answer == "quit":
                    reviews.set_status(review_id, "paused")
                    self.conn.commit()
                    self.context.current_review_id = review_id
                    return f"Clarify paused: review #{review_id}"
                if answer == "skip":
                    reviews.skip_item(item["id"], "shell skip")
                    break
                if answer == "show":
                    print(self.show([str(obj["id"])]))
                    answer = self.input_func("> ").strip()
                reviews.record_answer(item["id"], question["id"], question["text"], answer)
                answers.append(answer)
            else:
                if mode == "ai":
                    reviews.update_item_clarify(item["id"], {"status": "answered", "provider": self.context.provider, "ai_questions_only": True})
                    continue
                if provider is None:
                    reviews.update_item_clarify(item["id"], {"status": "answered", "provider": "off"})
                    continue
                payload = clarify_service.build_payload(review_id, item["id"], obj, "\n".join(answers), project_ref=self.context.project_ref)
                if isinstance(provider, DryRunProvider):
                    previews.append(provider.preview_payload(payload))
                    reviews.update_item_clarify(item["id"], {"status": "submitted", "provider": "dry-run", "provider_request_summary": {"size_chars": payload.get("payload_size_chars")}, "provider_response_summary": {"dry_run": True}})
                    continue
                result = provider.generate(payload)
                proposal_ids = clarify_service._result_to_proposals(review_id, int(obj["id"]), result)
                generated.extend(proposal_ids)
                reviews.update_item_clarify(item["id"], {"status": "proposal_generated" if proposal_ids else "submitted", "provider": self.context.provider, "generated_proposal_ids": proposal_ids})
        reviews.set_status(review_id, "completed")
        self.context.current_review_id = review_id
        self.conn.commit()
        proposals = ProposalService(self.conn, self.settings).list(review_session_id=review_id, limit=100)
        lines = [f"Clarify completed: review #{review_id}", proposal_table(proposals, self.repo)]
        if previews:
            lines.append(f"Payload previews: {len(previews)}")
        return "\n".join(lines)

    def _clarify_questions(self, mode: str) -> List[Dict[str, str]]:
        if mode == "quick":
            return QUICK_QUESTIONS
        if mode == "deep":
            return BASIC_QUESTIONS
        if mode == "ai":
            return QUICK_QUESTIONS
        return STANDARD_QUESTIONS

    def provider(self, args: List[str]) -> str:
        if not args:
            return f"provider: {self.context.provider}"
        name = args[0]
        if name not in {"off", "dry-run", "mock", "deepseek", "openai-compatible", "remote", "invalid-json"}:
            return f"Unsupported provider: {name}"
        self.context.provider = name
        return f"provider: {self.context.provider}"

    def detail(self, args: List[str]) -> str:
        if not args or args[0] not in {"on", "off"}:
            return f"detail: {'on' if self.context.detail else 'off'}"
        self.context.detail = args[0] == "on"
        return f"detail: {args[0]}"

    def where(self, args: List[str]) -> str:
        if not args:
            return "Usage: where todo|idea|mini|resource ... OR where result <object> ..."
        command = args[0]
        if command in {"todo", "idea", "mini", "resource"}:
            text = " ".join(args[1:]) or "..."
            content = {
                "todo": f"TODO {text}",
                "idea": f"**[想法]** {text}",
                "mini": f"**[小任务]** {text}",
                "resource": f"**[资源]** {text}",
            }[command]
            preview, target = self._preview_for_context(command, content)
            return self._location_preview(command, preview, target, content)
        if command in {"result", "noresult", "note", "ainote"} and (len(args) >= 2 or self.context.current_object_id):
            marker = {"note": "**[注]**", "ainote": "**[AI注]**", "result": "**[成果]**", "noresult": "**[无成果]**"}[command]
            target_ref = args[1] if len(args) >= 2 and not self.context.current_object_id else str(self.context.current_object_id)
            content_args = args[2:] if target_ref != str(self.context.current_object_id) else args[1:]
            target = self.resolve_target(target_ref, allow_types={"task", "idea", "mini_project", "project", "reference", "resource"})
            if not target:
                return f"Object not found: {target_ref}"
            obj = target["object"]
            preview = self.writer.preview_append_marker_child(Path(obj["file_path"]), marker, " ".join(content_args) or "...", block_uuid=obj.get("block_uuid"), line_start=obj.get("line_start"))
            return self._location_preview(command, preview, f"object:{obj['id']}", marker)
        return "Unsupported where command."

    def quality(self, args: List[str]) -> str:
        name = args[0] if args else "all"
        if name == "--json" and len(args) > 1:
            name = args[1]
        service = ProjectQualityService(self.conn, self.settings)
        if name in {"project-tree", "tree"}:
            return service.markdown(service.project_tree_quality())
        if name == "mini":
            return service.markdown(service.mini_project_quality())
        if name == "membership":
            return service.markdown(service.membership_quality())
        if name == "clarify":
            if not self.context.current_review_id:
                return "No current clarify review."
            return self.clarify(["eval"])
        if name == "all":
            tree = service.project_tree_quality()
            mini = service.mini_project_quality()
            membership = service.membership_quality()
            return "\n".join(
                [
                    "# Shell Quality Summary",
                    f"- project pages: {tree['recognized_project_pages']}",
                    f"- suspicious projects: {len(tree['projects_with_suspicious_tree'])}",
                    f"- mini projects: {mini['mini_project_count']}",
                    f"- membership candidates: {membership['candidate_count']}",
                    f"- duplicate proposals: {membership['duplicate_proposal_count']}",
                ]
            )
        return "Usage: quality project-tree|mini|membership|clarify|all"

    def _preview_for_context(self, kind: str, content: str) -> Tuple[WritePreview, str]:
        path = self.context.path
        if path in {"/today", "/inbox"} or not self._has_write_context():
            target = self._today_journal_path()
            if path == "/inbox" and kind != "todo":
                content = f"{content} #inbox"
            return self._preview_append_file_end(target, content), str(target)
        if self.context.project_node_id and self.context.project_ref:
            file_path, line_start = self._node_location(self.context.project_ref, self.context.project_node_id)
            return self.writer.preview_append_child(file_path, content, line_start=line_start), f"{file_path}:{line_start}"
        if self.context.mini_ref:
            obj = self._object(self.context.mini_ref)
            return self.writer.preview_append_child(Path(obj["file_path"]), content, block_uuid=obj.get("block_uuid"), line_start=obj.get("line_start")), f"mini:{obj['id']}"
        if self.context.project_ref:
            return self._preview_project_append(kind, content)
        target = self._today_journal_path()
        return self._preview_append_file_end(target, f"{content} #inbox"), f"{target} (fallback inbox)"

    def _preview_project_append(self, kind: str, content: str) -> Tuple[WritePreview, str]:
        marker_by_kind = {"todo": "具体事务", "idea": "想法", "mini": "小任务", "resource": "资源"}
        project = self._object(self.context.project_ref)
        file_path = Path(project["file_path"])
        target_marker = marker_by_kind.get(kind, "具体事务")
        parsed = parse_logseq_file(file_path, project.get("title"))
        for block in parsed.blocks:
            if semantic_marker(block.raw) == target_marker:
                return self.writer.preview_append_child(file_path, content, block_uuid=block.uuid, line_start=block.line_number), f"{file_path}:{block.line_number}"
        section = f"**[{target_marker}]**"
        preview = self._preview_append_file_end(file_path, section)
        temp_text = preview.new_text
        lines = temp_text.splitlines()
        line_start = len(lines)
        child = self._format_child(content, indent=1)
        new_text = temp_text + child
        diff = self._diff(file_path, file_path.read_text(encoding="utf-8"), new_text)
        return WritePreview(file_path=file_path, original_sha256=self.writer.sha256(file_path), new_text=new_text, diff=diff, line_start=line_start), f"{file_path}:{line_start}"

    def _preview_append_file_end(self, file_path: Path, content: str) -> WritePreview:
        path = Path(file_path)
        old = path.read_text(encoding="utf-8") if path.exists() else ""
        if old and not old.endswith("\n"):
            old += "\n"
        new = old + self._format_child(content, indent=0)
        return WritePreview(file_path=path, original_sha256=self.writer.sha256(path) if path.exists() else "", new_text=new, diff=self._diff(path, old, new))

    def _apply_direct_preview(self, preview: WritePreview, command: str, target: str) -> ShellOperation:
        created_file = not preview.file_path.exists()
        backup = self.writer.apply(preview, preview.original_sha256, self.settings.write_backup_dir or self.settings.app_dir / "backups")
        self.conn.commit()
        backup_path = str(backup) if backup and str(backup) not in {"", "."} else None
        return self._record_operation(command, "direct_write", target, file_path=str(preview.file_path), backup_path=backup_path, created_file=created_file)

    def _record_operation(self, command: str, kind: str, target: str, file_path: Optional[str] = None, backup_path: Optional[str] = None, proposal_id: Optional[int] = None, created_file: bool = False) -> ShellOperation:
        op = ShellOperation(len(self.history) + 1, command, kind, target, file_path=file_path, backup_path=backup_path, proposal_id=proposal_id, created_file=created_file, content=command)
        self.history.append(op)
        return op

    def resolve_target(self, text: str, allow_types: Optional[set] = None) -> Optional[Dict[str, Any]]:
        if not text:
            return None
        if text.isdigit():
            obj = self.repo.get_object(int(text))
            if obj and (not allow_types or obj["object_type"] in allow_types):
                return {"object": obj}
        rows = self._target_candidates(text, allow_types=allow_types)
        if not rows:
            return None
        if len(rows) == 1:
            return {"object": rows[0]}
        choice = self._choose(
            "找到多个匹配项",
            [
                {
                    "label": f"#{row['id']} {row['object_type']} {row.get('status') or ''} {row['title']} ({row.get('page_name')}:{row.get('line_start') or ''})",
                    "value": row,
                }
                for row in rows[:10]
            ],
        )
        return {"object": choice["value"]} if choice else None

    def _target_candidates(self, text: str, allow_types: Optional[set] = None) -> List[Dict[str, Any]]:
        like = f"%{text}%"
        params: List[Any] = [like]
        type_sql = ""
        if allow_types:
            type_sql = " AND o.object_type IN (" + ",".join("?" for _ in allow_types) + ")"
            params.extend(sorted(allow_types))
        rows = self.conn.execute(
            f"""
            SELECT o.*, l.file_path, l.page_name, l.journal_date, l.line_start
            FROM objects o LEFT JOIN locations l ON l.id=o.canonical_location_id
            WHERE o.title LIKE ? {type_sql}
            ORDER BY CASE WHEN l.page_name=? THEN 0 ELSE 1 END, o.id DESC
            LIMIT 20
            """,
            (*params, self._current_page_name()),
        ).fetchall()
        return [self._object_row(row) for row in rows]

    def _object_row(self, row) -> Dict[str, Any]:
        data = dict(row)
        if "metadata_json" in data:
            data["metadata"] = json.loads(data.pop("metadata_json") or "{}")
        return data

    def _choose(self, title: str, candidates: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not candidates:
            return None
        lines = [title]
        for index, item in enumerate(candidates, 1):
            lines.append(f"[{index}] {item['label']}")
        lines.append("请选择编号，或输入 q 取消：")
        try:
            answer = self.input_func("\n".join(lines) + "\n> ").strip()
        except (EOFError, OSError):
            return None
        if answer.lower() in {"q", "quit", "cancel", ""}:
            return None
        if answer.isdigit() and 1 <= int(answer) <= len(candidates):
            return candidates[int(answer) - 1]
        return None

    def _confirm(self, prompt: str) -> bool:
        return self.input_func(prompt).strip().lower() in {"y", "yes", "是"}

    def _location_preview(self, operation: str, preview: WritePreview, target: str, content: str) -> str:
        try:
            rel = Path(preview.file_path).relative_to(Path(self.settings.logseq_graph_path))
        except Exception:
            rel = preview.file_path
        if self.context.detail:
            return "\n".join(
                [
                    "将写入：",
                    f"graph: {self.settings.logseq_graph_path}",
                    f"file: {rel}",
                    f"target: {target}",
                    f"operation: {operation}",
                    f"line: {preview.line_start or ''}",
                    "content:",
            f"  - {color_task_markers(content, use_color())}",
                    "diff:",
                    preview.diff[:1200],
                ]
            )
        old_line, new_line = self._preview_old_new(preview)
        is_append = old_line == "" and new_line
        heading = "将追加内容" if is_append else "将修改任务" if "task" in operation or operation in {"done", "doing", "wait"} else "将写入"
        scope = "追加为目标 block 的子块" if is_append else "仅修改目标 block 首行，保留子块"
        lines = [
            f"将写入：{heading} {target}",
            "",
            f"file: {rel}:{preview.line_start or ''}",
            f"operation: {operation}",
            f"scope: {scope}",
            "undo: available",
        ]
        if old_line:
            lines.extend(["", "old:", f"  {color_task_markers(old_line.strip(), use_color())}"])
        if new_line:
            lines.extend(["", "new child:" if is_append else "new:", f"  {color_task_markers(new_line.strip(), use_color())}"])
        return "\n".join(lines)

    def _preview_old_new(self, preview: WritePreview) -> Tuple[str, str]:
        old_line = ""
        new_line = ""
        for line in preview.diff.splitlines():
            if line.startswith("---") or line.startswith("+++") or line.startswith("@@"):
                continue
            if line.startswith("-") and not old_line:
                old_line = line[1:]
            elif line.startswith("+"):
                new_line = line[1:]
        if not old_line and preview.line_start and preview.file_path.exists():
            try:
                old_lines = preview.file_path.read_text(encoding="utf-8").splitlines()
                if 1 <= preview.line_start <= len(old_lines):
                    old_line = old_lines[preview.line_start - 1]
            except OSError:
                pass
        return old_line, new_line

    def _extract_preview_flag(self, args: List[str]) -> Tuple[bool, List[str]]:
        return "--preview" in args, [arg for arg in args if arg != "--preview"]

    def _record_command(self, line: str) -> None:
        lowered = line.lower()
        if any(secret in lowered for secret in ("api_key", "token", "password", "secret", "sk-")):
            self.command_history.append("[redacted sensitive command]")
            return
        if line not in {"exit", "quit", "commands", "clear-history"}:
            self.command_history.append(line)

    def _current_page_name(self) -> Optional[str]:
        if self.context.project_ref:
            try:
                return self._object(self.context.project_ref).get("page_name")
            except Exception:
                return None
        return None

    def _clarify_status(self) -> str:
        if not self.context.current_review_id:
            return "No current clarify review."
        review = ReviewSessionService(self.conn).show(self.context.current_review_id)
        statuses = [item.get("metadata", {}).get("clarify", {}).get("status", "pending") for item in review.get("items", [])]
        return "\n".join(
            [
                f"review id: {review['id']}",
                f"status: {review['status']}",
                f"total items: {len(statuses)}",
                f"answered: {statuses.count('answered')}",
                f"skipped: {statuses.count('skipped')}",
                f"failed: {statuses.count('failed')}",
                f"proposals generated: {len(review.get('proposals', []))}",
            ]
        )

    def _latest_shell_review(self) -> Optional[Dict[str, Any]]:
        rows = ReviewSessionService(self.conn).list(limit=20)
        return next((row for row in rows if str(row.get("review_type", "")).startswith("shell:") and row.get("status") in {"open", "in_progress", "paused"}), None)

    def completion_project_names(self) -> List[str]:
        names = []
        for row in self.repo.list_objects("project", limit=100):
            title = row["title"]
            names.append(title)
            if title.startswith("项目-"):
                names.append(title[3:])
        return names

    def completion_mini_names(self) -> List[str]:
        return [row["title"] for row in self.repo.list_objects("mini_project", limit=100)]

    def completion_project_node_names(self) -> List[str]:
        if not self.context.project_ref:
            return []
        tree = ProjectTreeService(self.conn, self.settings).build(self.context.project_ref, detail=False)
        flat: List[Dict[str, Any]] = []
        ProjectTreeService(self.conn, self.settings)._flatten(tree["tree"], flat)
        names = []
        for node in flat:
            label = LABEL_BY_NODE_TYPE.get(node["node_type"], node["node_type"])
            names.append(node["title"])
            names.append(f"{label}/{node['title']}")
        return names

    def completion_object_candidates(self, command: str) -> List[str]:
        allow = {"show", "open"}
        types = None if command in allow else {"task", "idea", "mini_project", "project"}
        rows = self._target_candidates("", allow_types=types) if False else []
        sql_types = "" if types is None else "WHERE object_type IN (" + ",".join("?" for _ in types) + ")"
        params = sorted(types) if types else []
        rows = self.conn.execute(f"SELECT id, title FROM objects {sql_types} ORDER BY id DESC LIMIT 100", params).fetchall()
        return [row["title"] for row in rows] + [str(row["id"]) for row in rows]

    def completion_proposal_candidates(self) -> List[str]:
        if not self.local_proposal_map:
            self.proposals()
        return [str(index) for index in sorted(self.local_proposal_map)]

    def completion_relative_in_context(self, token: str) -> List[str]:
        """Return relative completion candidates based on current context."""
        path = self.context.path
        if path == "/projects" or (path == "/" and not token.startswith("/")):
            return self.completion_project_names()
        if path == "/mini":
            return self.completion_mini_names()
        if path.startswith("/projects/") and self.context.project_ref:
            return self.completion_project_node_names()
        return []

    def _resync(self) -> None:
        SyncService(self.conn, self.settings).sync_logseq()

    def _resync_light(self, changed_file: Optional[Path] = None, changed_object_id: Optional[int] = None) -> None:
        if changed_file and Path(changed_file).exists():
            result = LogseqAdapter(Path(self.settings.logseq_graph_path)).parse_file(Path(changed_file))
            Merger(self.repo).ingest(result)
        if changed_object_id:
            self.repo.update_object_after_writeback(changed_object_id, dirty_reason="shell_writeback")
        self.conn.commit()

    def _has_write_context(self) -> bool:
        return bool(self.context.project_ref or self.context.project_node_id or self.context.mini_ref)

    def _today_journal_path(self) -> Path:
        graph = Path(self.settings.logseq_graph_path)
        journals = graph / "journals"
        journals.mkdir(parents=True, exist_ok=True)
        return journals / f"{date.today().strftime('%Y_%m_%d')}.md"

    def _object(self, ref: Optional[str]) -> Dict[str, Any]:
        if not ref:
            raise NotFoundError("Object ref missing.")
        object_id = self.repo.resolve_object_id(ref)
        if object_id is None:
            raise NotFoundError(f"Object not found: {ref}")
        obj = self.repo.get_object(object_id)
        if not obj:
            raise NotFoundError(f"Object not found: {ref}")
        return obj

    def _node_location(self, project_ref: str, node_id: str) -> Tuple[Path, int]:
        tree = ProjectTreeService(self.conn, self.settings).build(project_ref, detail=True)
        flat: List[Dict[str, Any]] = []
        ProjectTreeService(self.conn, self.settings)._flatten(tree["tree"], flat)
        node = next((item for item in flat if item["id"] == node_id), None)
        if not node:
            raise NotFoundError(f"Project node not found: {node_id}")
        return Path(node["location"]["file_path"]), int(node["location"]["line_start"])

    def _resolve_path(self, path: str) -> Optional[Dict[str, Any]]:
        path = "/" + "/".join(part for part in path.split("/") if part)
        if path == "/":
            return {"path": "/"}
        parts = [part for part in path.split("/") if part]
        if not parts or parts[0] not in ROOTS:
            return None
        if parts[0] == "projects" and len(parts) >= 2:
            project_name = "/".join(parts[1:2])
            project_id = self.repo.resolve_object_id(project_name) or self.repo.resolve_object_id(f"项目-{project_name}")
            if project_id is None:
                return None
            project = self.repo.get_object(project_id)
            if len(parts) == 2:
                return {"path": f"/projects/{project['title']}", "project_ref": str(project_id)}
            if len(parts) == 3 and parts[2] in set(LABEL_BY_NODE_TYPE.values()):
                return {"path": f"/projects/{project['title']}/{parts[2]}", "project_ref": str(project_id)}
            node = self._match_project_node(str(project_id), parts[2:])
            if not node:
                return None
            label = LABEL_BY_NODE_TYPE.get(node["node_type"], node["node_type"])
            return {
                "path": f"/projects/{project['title']}/{label}/{node['title']}",
                "project_ref": str(project_id),
                "project_node_id": node["id"],
                "project_node_title": node["title"],
            }
        if parts[0] == "mini" and len(parts) >= 2:
            name = "/".join(parts[1:])
            mini_id = self.repo.resolve_object_id(name)
            if mini_id is None:
                return None
            mini = self.repo.get_object(mini_id)
            return {"path": f"/mini/{mini['title']}", "mini_ref": str(mini_id)}
        if len(parts) == 1:
            return {"path": f"/{parts[0]}"}
        return None

    def _apply_context(self, resolved: Dict[str, Any]) -> None:
        self.context.path = resolved["path"]
        self.context.project_ref = resolved.get("project_ref")
        self.context.project_node_id = resolved.get("project_node_id")
        self.context.project_node_title = resolved.get("project_node_title")
        self.context.mini_ref = resolved.get("mini_ref")
        self.context.current_object_id = resolved.get("current_object_id")
        self.context.current_object_type = resolved.get("current_object_type")
        self.context.current_object_title = resolved.get("current_object_title")
        self.context.current_object_location = resolved.get("current_object_location")

    def _resolve_object_context(self, target: str) -> Optional[Dict[str, Any]]:
        raw = target.strip()
        if not raw:
            return None
        parts = raw.split()
        type_hint = None
        ref = raw
        if len(parts) == 2 and parts[0] in {"task", "mini", "mini_project", "idea", "resource", "reference", "project"}:
            type_hint = "mini_project" if parts[0] == "mini" else parts[0]
            ref = parts[1]
        if ref.startswith("#"):
            ref = ref[1:]
        if not ref.isdigit() and type_hint is None:
            return None
        allow_types = {type_hint} if type_hint else {"task", "idea", "mini_project", "reference", "resource", "project"}
        target_obj = self.resolve_target(ref, allow_types=allow_types)
        if not target_obj:
            return None
        obj = target_obj["object"]
        obj_type = obj["object_type"]
        parent_project = self.context.project_ref
        base = self.context.path
        if parent_project:
            try:
                project = self._object(parent_project)
                base = f"/projects/{project['title']}"
            except Exception:
                base = "/objects"
        elif obj_type == "mini_project":
            base = "/mini"
        else:
            base = "/objects"
        label = "mini" if obj_type == "mini_project" else obj_type
        return {
            "path": f"{base}/{label}/{obj['id']}",
            "project_ref": parent_project,
            "mini_ref": str(obj["id"]) if obj_type == "mini_project" else self.context.mini_ref,
            "current_object_id": int(obj["id"]),
            "current_object_type": obj_type,
            "current_object_title": obj["title"],
            "current_object_location": f"{obj.get('file_path')}:{obj.get('line_start') or ''}",
        }

    def _resolve_project_node_context(self, target: str) -> Optional[Dict[str, Any]]:
        if not self.context.project_ref:
            return None
        raw = target.strip()
        if not raw:
            return None
        node = self._match_project_node(self.context.project_ref, [raw])
        if not node:
            return None
        project = self._object(self.context.project_ref)
        label = LABEL_BY_NODE_TYPE.get(node["node_type"], node["node_type"])
        return {
            "path": f"/projects/{project['title']}/{label}/{node['title']}",
            "project_ref": str(project["id"]),
            "project_node_id": node["id"],
            "project_node_title": node["title"],
        }

    def _match_project_node(self, project_ref: str, parts: List[str]) -> Optional[Dict[str, Any]]:
        tree = ProjectTreeService(self.conn, self.settings).build(project_ref, detail=False)
        flat: List[Dict[str, Any]] = []
        ProjectTreeService(self.conn, self.settings)._flatten(tree["tree"], flat)
        wanted = parts[-1]
        for node in flat:
            label = LABEL_BY_NODE_TYPE.get(node["node_type"], node["node_type"])
            if node["id"] == wanted or node["title"] == wanted or label == wanted or wanted in node["title"] or f"{label}/{node['title']}" == "/".join(parts):
                return node
        return None

    def _candidate_ids_for_context(self, limit: int) -> List[str]:
        if self.context.path == "/today":
            return ClarifyService(self.conn, self.settings).today_candidates(limit)
        if self.context.path == "/inbox":
            return ClarifyService(self.conn, self.settings).inbox_candidates(limit)
        if self.context.project_ref:
            return ClarifyService(self.conn, self.settings).project_candidates(self.context.project_ref, limit)
        if self.context.path == "/ideas":
            return [str(item["id"]) for item in self.repo.list_objects("idea", limit=limit)]
        return ClarifyService(self.conn, self.settings).inbox_candidates(limit)

    def _has_result_marker(self, object_id: int) -> bool:
        return any(record.get("role") == "result_marker" for record in self.repo.records_for_object(object_id, limit=100))

    def _proposal_id(self, ref: str) -> int:
        value = int(ref)
        if value in self.local_proposal_map:
            return self.local_proposal_map[value]
        if self.local_proposal_map:
            raise TaskManagerError(
                f"Proposal [{value}] 不存在。请先运行 proposals 或 ls proposals 查看当前编号。"
            )
        return value

    def _objects_list(self, object_type: str) -> str:
        rows = self.repo.list_objects(object_type, limit=50)
        return "\n".join(f"- #{row['id']} {row['title']} ({row.get('status') or ''})" for row in rows) or "Empty."

    def _context_objects(self, path: str) -> str:
        if path == "/waiting":
            rows = self.repo.list_objects("task", status="waiting", limit=50)
        elif path == "/someday":
            rows = self._objects_by_tag("someday")
        elif path == "/inbox":
            rows = self._objects_by_tag("inbox")
        else:
            rows = ClarifyService(self.conn, self.settings).today_candidates(20)
            rows = [self.repo.get_object(int(item)) for item in rows]
        return "\n".join(f"- #{row['id']} {row['object_type']} {row.get('status') or ''} {row['title']}" for row in rows if row) or "Empty."

    def _objects_by_tag(self, tag: str) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT DISTINCT o.*, l.file_path, l.page_name, l.journal_date, l.line_start
            FROM objects o
            JOIN object_record_links orl ON orl.object_id=o.id
            JOIN source_records r ON r.id=orl.record_id
            LEFT JOIN locations l ON l.id=o.canonical_location_id
            WHERE r.metadata_json LIKE ?
            ORDER BY o.id DESC LIMIT 50
            """,
            (f"%{tag}%",),
        ).fetchall()
        return [dict(row) for row in rows]

    def _path_candidates(self, target: str) -> List[str]:
        if "/projects" in target or target.startswith("/p"):
            return [f"/projects/{row['title']}" for row in self.repo.list_objects("project", limit=10)]
        if "/mini" in target:
            return [f"/mini/{row['title']}" for row in self.repo.list_objects("mini_project", limit=10)]
        return [f"/{item}" for item in sorted(ROOTS)]

    def _expand_alias(self, target: str) -> str:
        if target == "@today":
            return "/today"
        if target == "@inbox":
            return "/inbox"
        if target.startswith("@p/"):
            return "/projects/" + target[3:]
        if target.startswith("@mini/"):
            return "/mini/" + target[6:]
        return target

    def _parent_path(self, path: str) -> str:
        if path == "/":
            return "/"
        parent = "/".join(path.rstrip("/").split("/")[:-1])
        return parent or "/"

    def _join_path(self, base: str, child: str) -> str:
        return base.rstrip("/") + "/" + child

    def _format_child(self, content: str, indent: int) -> str:
        prefix = " " * (indent * 4)
        return f"{prefix}- {content.strip()}\n"

    def _diff(self, path: Path, old: str, new: str) -> str:
        import difflib

        return "".join(difflib.unified_diff(old.splitlines(True), new.splitlines(True), fromfile=str(path), tofile=str(path)))
