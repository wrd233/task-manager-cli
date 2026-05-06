import json
import shlex
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from task_manager_cli.adapters.logseq.extractors import semantic_marker
from task_manager_cli.adapters.logseq.parser import parse_logseq_file
from task_manager_cli.clarify.service import BASIC_QUESTIONS, ClarifyService, proposal_table
from task_manager_cli.config.settings import Settings
from task_manager_cli.core.enums import ProposalType
from task_manager_cli.core.errors import ConfigError, NotFoundError, TaskManagerError
from task_manager_cli.ingest.sync import SyncService
from task_manager_cli.projects.tree import LABEL_BY_NODE_TYPE, ProjectTreeService
from task_manager_cli.proposals.service import ProposalService
from task_manager_cli.providers.base import DryRunProvider, provider_from_settings
from task_manager_cli.reviews.service import ReviewSessionService
from task_manager_cli.storage.repositories import Repository
from task_manager_cli.writes.logseq_writer import LogseqWriter, WritePreview


ROOTS = {"today", "inbox", "waiting", "someday", "ideas", "projects", "mini", "reviews", "proposals"}


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
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).replace(microsecond=0).isoformat())


class HumanShellService:
    def __init__(self, conn, settings: Settings, input_func: Callable[[str], str] = input):
        self.conn = conn
        self.settings = settings
        self.repo = Repository(conn)
        self.context = ShellContext()
        self.history: List[ShellOperation] = []
        self.local_proposal_map: Dict[int, int] = {}
        self.input_func = input_func
        if not settings.logseq_graph_path:
            raise ConfigError("Logseq graph path is not configured.")
        self.writer = LogseqWriter(settings.logseq_graph_path)

    def prompt(self) -> str:
        return f"ta:{self.context.path}> "

    def run_line(self, line: str) -> str:
        line = line.strip()
        if not line:
            return ""
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
                return self.ls()
            if command == "cd":
                return self.cd(args[0] if args else "/")
            if command == "tree":
                return self.tree()
            if command == "show":
                return self.show(args)
            if command == "open":
                return self.open(args)
            if command == "find":
                return self.find(" ".join(args))
            if command in {"todo", "idea", "mini", "resource"}:
                return self.create_item(command, " ".join(args))
            if command in {"note", "ainote", "result", "noresult"}:
                return self.append_marker(command, args)
            if command in {"doing", "done", "wait"}:
                return self.change_task_marker(command, args)
            if command == "someday":
                return self.someday(args)
            if command == "undo":
                return self.undo()
            if command == "proposals":
                return self.proposals()
            if command in {"accept", "reject", "preview", "apply", "edit"}:
                return self.proposal_action(command, args)
            if command == "clarify":
                return self.clarify()
            if command == "provider":
                return self.provider(args)
            if command == "detail":
                return self.detail(args)
            return f"Unknown command: {command}. Type `help`."
        except (TaskManagerError, ConfigError, NotFoundError, ValueError, KeyError) as exc:
            return f"Error: {exc}"

    def help(self) -> str:
        return "\n".join(
            [
                "Human Shell commands:",
                "  pwd, ls, cd, tree, show, open, find",
                "  todo, idea, mini, resource, note, ainote, doing, done, wait, someday, result, noresult",
                "  clarify, provider, proposals, accept, reject, preview, apply, edit, undo",
                "  detail on|off, exit",
            ]
        )

    def cd(self, target: str) -> str:
        old = self.context.path
        if target == "-":
            if not self.context.previous_path:
                return "No previous context."
            target = self.context.previous_path
        elif target == "..":
            target = self._parent_path(self.context.path)
        target = self._expand_alias(target)
        if not target.startswith("/"):
            target = self._join_path(self.context.path, target)
        resolved = self._resolve_path(target)
        if not resolved:
            return f"Path not found: {target}\nCandidates: {', '.join(self._path_candidates(target))}"
        self.context.previous_path = old
        self.context.path = resolved["path"]
        self.context.project_ref = resolved.get("project_ref")
        self.context.project_node_id = resolved.get("project_node_id")
        self.context.project_node_title = resolved.get("project_node_title")
        self.context.mini_ref = resolved.get("mini_ref")
        return self.context.path

    def ls(self) -> str:
        path = self.context.path
        if path == "/":
            return "\n".join(f"- {item}" for item in sorted(ROOTS))
        if path == "/projects":
            return self._objects_list("project")
        if path == "/mini":
            return self._objects_list("mini_project")
        if path == "/ideas":
            return self._objects_list("idea")
        if path == "/proposals":
            return self.proposals()
        if path.startswith("/projects/") and self.context.project_ref:
            tree = ProjectTreeService(self.conn, self.settings).build(self.context.project_ref)
            lines = [f"Project: {tree['project']['title']}", f"Nodes: {tree['summary']['node_count']}"]
            for node in tree.get("tree", [])[:12]:
                lines.append(f"- [{LABEL_BY_NODE_TYPE.get(node['node_type'], node['node_type'])}] {node['title']}")
            return "\n".join(lines)
        if path in {"/today", "/inbox", "/waiting", "/someday"}:
            return self._context_objects(path)
        return f"Context: {path}"

    def tree(self) -> str:
        if not self.context.project_ref:
            return "tree is available inside /projects/<project>."
        service = ProjectTreeService(self.conn, self.settings)
        return service.render_markdown(service.build(self.context.project_ref, detail=self.context.detail), detail=self.context.detail)

    def show(self, args: List[str]) -> str:
        if not args:
            return "Usage: show <object-id>|proposal <id>|review <id>"
        if args[0] == "proposal" and len(args) > 1:
            return json.dumps(ProposalService(self.conn, self.settings).get(self._proposal_id(args[1])), ensure_ascii=False, indent=2)
        if args[0] == "review" and len(args) > 1:
            return json.dumps(ReviewSessionService(self.conn).show(int(args[1])), ensure_ascii=False, indent=2)
        obj = self.repo.get_object(int(args[0])) if args[0].isdigit() else None
        if not obj:
            object_id = self.repo.resolve_object_id(args[0])
            obj = self.repo.get_object(object_id) if object_id else None
        if not obj:
            return f"Object not found: {' '.join(args)}"
        return f"#{obj['id']} {obj['object_type']} {obj.get('status') or ''} {obj['title']}\n{obj.get('file_path')}:{obj.get('line_start') or ''}"

    def open(self, args: List[str]) -> str:
        if not args:
            return "Usage: open <object-id>"
        object_id = self.repo.resolve_object_id(args[0])
        if object_id is None:
            return f"Object not found: {args[0]}"
        obj = self.repo.get_object(object_id)
        return f"{obj.get('file_path')}:{obj.get('line_start') or ''}\nblock_path: {obj.get('block_path') or []}"

    def find(self, query: str) -> str:
        if not query:
            return "Usage: find <keyword>"
        like = f"%{query}%"
        rows = self.conn.execute(
            """
            SELECT o.*, l.file_path, l.page_name, l.journal_date, l.line_start
            FROM objects o LEFT JOIN locations l ON l.id=o.canonical_location_id
            WHERE o.title LIKE ? OR o.metadata_json LIKE ?
            ORDER BY o.id DESC LIMIT 20
            """,
            (like, like),
        ).fetchall()
        if not rows:
            return "No matches."
        return "\n".join(f"- #{row['id']} {row['object_type']} {row['title']} ({row['page_name']}:{row['line_start'] or ''})" for row in rows)

    def create_item(self, kind: str, text: str) -> str:
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
        op = self._apply_direct_preview(preview, f"{kind} {text}", target)
        self._resync()
        return f"{kind} written to {target} (op #{op.id})"

    def append_marker(self, command: str, args: List[str]) -> str:
        if len(args) < 2:
            return f"Usage: {command} <object-id> \"text\""
        marker = {"note": "**[注]**", "ainote": "**[AI注]**", "result": "**[成果]**", "noresult": "**[无成果]**"}[command]
        object_id = self.repo.resolve_object_id(args[0])
        if object_id is None:
            return f"Object not found: {args[0]}"
        obj = self.repo.get_object(object_id)
        preview = self.writer.preview_append_marker_child(Path(obj["file_path"]), marker, " ".join(args[1:]), block_uuid=obj.get("block_uuid"), line_start=obj.get("line_start"))
        op = self._apply_direct_preview(preview, f"{command} {args[0]}", f"object:{object_id}")
        self._resync()
        return f"{command} appended to #{object_id} (op #{op.id})"

    def change_task_marker(self, command: str, args: List[str]) -> str:
        if not args:
            return f"Usage: {command} <object-id> [reason]"
        object_id = self.repo.resolve_object_id(args[0])
        if object_id is None:
            return f"Object not found: {args[0]}"
        obj = self.repo.get_object(object_id)
        marker = {"doing": "DOING", "done": "DONE", "wait": "WAITING"}[command]
        preview = self.writer.preview_update_task_marker(Path(obj["file_path"]), marker, block_uuid=obj.get("block_uuid"), line_start=obj.get("line_start"))
        op = self._apply_direct_preview(preview, f"{command} {args[0]}", f"object:{object_id}")
        extra = ""
        if command == "wait" and len(args) > 1:
            note_preview = self.writer.preview_append_marker_child(Path(obj["file_path"]), "**[注]**", " ".join(args[1:]), block_uuid=obj.get("block_uuid"), line_start=obj.get("line_start"))
            note_op = self._apply_direct_preview(note_preview, f"wait-note {args[0]}", f"object:{object_id}")
            extra = f"; reason note op #{note_op.id}"
        self._resync()
        hint = ""
        if command == "done" and not self._has_result_marker(object_id):
            hint = f"\n该条目已完成，但没有成果标注。可输入 result {object_id} \"...\" 或 noresult {object_id} \"...\""
        return f"#{object_id} -> {marker} (op #{op.id}{extra}){hint}"

    def someday(self, args: List[str]) -> str:
        if not args:
            return "Usage: someday <object-id>"
        object_id = self.repo.resolve_object_id(args[0])
        if object_id is None:
            return f"Object not found: {args[0]}"
        obj = self.repo.get_object(object_id)
        preview = self.writer.preview_append_marker_child(Path(obj["file_path"]), "**[注]**", "#someday", block_uuid=obj.get("block_uuid"), line_start=obj.get("line_start"))
        op = self._apply_direct_preview(preview, f"someday {args[0]}", f"object:{object_id}")
        self._resync()
        return f"#someday appended to #{object_id} (op #{op.id})"

    def undo(self) -> str:
        for op in reversed(self.history):
            if op.undone:
                continue
            if op.proposal_id:
                result = ProposalService(self.conn, self.settings).rollback(op.proposal_id)
                self.conn.commit()
                op.undone = True
                return f"Rolled back proposal {op.proposal_id}: {result['status']}"
            if op.backup_path and op.file_path and Path(op.backup_path).is_file():
                self.writer.restore_backup(Path(op.backup_path), Path(op.file_path))
                op.undone = True
                self._resync()
                return f"Undone op #{op.id}: {op.command}"
            if op.created_file and op.file_path:
                Path(op.file_path).unlink(missing_ok=True)
                op.undone = True
                self._resync()
                return f"Undone op #{op.id}: {op.command}"
            return f"Cannot undo op #{op.id}: missing rollback information."
        return "Nothing to undo."

    def proposals(self) -> str:
        proposals = ProposalService(self.conn, self.settings).list(status="suggested", limit=50)
        proposals += ProposalService(self.conn, self.settings).list(status="accepted", limit=50)
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
            return "Use bottom CLI for detailed proposal edit in v1: tm proposal edit ..."
        return f"Unsupported proposal command: {command}"

    def clarify(self) -> str:
        ids = self._candidate_ids_for_context(limit=10)
        if not ids:
            return "No clarify candidates in this context."
        reviews = ReviewSessionService(self.conn)
        review_id = reviews.start(f"shell:{self.context.path}", item_refs=ids, title=f"Shell clarify {self.context.path}")
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
            for index, question in enumerate(BASIC_QUESTIONS, 1):
                answer = self.input_func(f"问题 {index}：{question['text']}\n> ").strip()
                if answer == "quit":
                    reviews.set_status(review_id, "paused")
                    self.conn.commit()
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
        self.conn.commit()
        proposals = ProposalService(self.conn, self.settings).list(review_session_id=review_id, limit=100)
        lines = [f"Clarify completed: review #{review_id}", proposal_table(proposals, self.repo)]
        if previews:
            lines.append(f"Payload previews: {len(previews)}")
        return "\n".join(lines)

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
        op = ShellOperation(len(self.history) + 1, command, kind, target, file_path=file_path, backup_path=backup_path, proposal_id=proposal_id, created_file=created_file)
        self.history.append(op)
        return op

    def _resync(self) -> None:
        SyncService(self.conn, self.settings).sync_logseq()

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
            node = self._match_project_node(str(project_id), parts[2:])
            if not node:
                return None
            return {"path": f"/projects/{project['title']}/{'/'.join(parts[2:])}", "project_ref": str(project_id), "project_node_id": node["id"], "project_node_title": node["title"]}
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

    def _match_project_node(self, project_ref: str, parts: List[str]) -> Optional[Dict[str, Any]]:
        tree = ProjectTreeService(self.conn, self.settings).build(project_ref, detail=False)
        flat: List[Dict[str, Any]] = []
        ProjectTreeService(self.conn, self.settings)._flatten(tree["tree"], flat)
        wanted = parts[-1]
        for node in flat:
            label = LABEL_BY_NODE_TYPE.get(node["node_type"], node["node_type"])
            if node["title"] == wanted or label == wanted or f"{label}/{node['title']}" == "/".join(parts):
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
        return self.local_proposal_map.get(value, value)

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
