import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

from task_manager_cli.adapters.logseq.adapter import LogseqAdapter
from task_manager_cli.adapters.logseq.parser import parse_logseq_file
from task_manager_cli.adapters.logseq.resolver import LogseqResolver
from task_manager_cli.annotations.service import AnnotationService
from task_manager_cli.config.settings import Settings, default_config_path, init_settings
from task_manager_cli.core.errors import ConfigError, NotFoundError, TaskManagerError
from task_manager_cli.ingest.sync import SyncService
from task_manager_cli.output.formatters import format_output, objects_table, to_json
from task_manager_cli.privacy.redactor import Redactor
from task_manager_cli.proposals.service import ProposalService
from task_manager_cli.query.agent_views import AgentViewService
from task_manager_cli.query.exporter import SnapshotExporter
from task_manager_cli.query.human_views import HumanViewService
from task_manager_cli.query.service import QueryService
from task_manager_cli.reviews.service import ReviewSessionService
from task_manager_cli.storage.database import connect, init_db
from task_manager_cli.storage.repositories import Repository
from task_manager_cli.writes.service import WriteService


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "handler"):
        parser.print_help()
        return 0
    try:
        result = args.handler(args)
        if result is not None:
            print(result)
        return 0
    except (TaskManagerError, ConfigError, NotFoundError, ValueError, KeyError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tm", description="Local action-object indexer and agent context CLI.")
    sub = parser.add_subparsers(dest="command")

    config = sub.add_parser("config", help="Configure the CLI.")
    config_sub = config.add_subparsers(dest="config_command")
    p = config_sub.add_parser("init", help="Initialize config and database.")
    p.add_argument("--graph", help="Logseq graph path.")
    p.add_argument("--db", help="SQLite database path.")
    p.set_defaults(handler=cmd_config_init)
    p = config_sub.add_parser("set-logseq", help="Set Logseq graph path.")
    p.add_argument("graph")
    p.set_defaults(handler=cmd_config_set_logseq)
    p = config_sub.add_parser("show", help="Show current config.")
    p.add_argument("--format", choices=["json", "table"], default="json")
    p.set_defaults(handler=cmd_config_show)
    p = config_sub.add_parser("set-write-mode", help="Set Logseq write mode.")
    p.add_argument("mode", choices=["disabled", "proposal", "guarded", "agent"])
    p.add_argument("--confirm", dest="require_confirm", action="store_true", default=None, help="Require --yes when applying writes.")
    p.add_argument("--no-confirm", dest="require_confirm", action="store_false", help="Do not require --yes when applying writes.")
    p.set_defaults(handler=cmd_config_set_write_mode)

    p = sub.add_parser("doctor", help="Check config, database, and Logseq adapter status.")
    p.set_defaults(handler=cmd_doctor)

    sync = sub.add_parser("sync", help="Sync data sources.")
    sync_sub = sync.add_subparsers(dest="sync_command")
    for name in ("logseq", "all"):
        p = sync_sub.add_parser(name, help=f"Sync {name}.")
        p.add_argument("--dry-run", action="store_true")
        p.add_argument("--recent-journals", type=int, help="Only include the newest N journal files.")
        p.set_defaults(handler=cmd_sync_logseq if name == "logseq" else cmd_sync_all)
    p = sync_sub.add_parser("runs", help="List sync runs.")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--format", choices=["json", "table"], default="table")
    p.set_defaults(handler=cmd_sync_runs)
    p = sync_sub.add_parser("status", help="Show sync status.")
    p.set_defaults(handler=cmd_sync_status)

    list_cmd = sub.add_parser("list", help="List objects.")
    list_sub = list_cmd.add_subparsers(dest="list_command")
    for name, object_type in (("projects", "project"), ("tasks", "task"), ("ideas", "idea")):
        p = list_sub.add_parser(name, help=f"List {name}.")
        p.add_argument("--status")
        p.add_argument("--limit", type=int, default=50)
        p.add_argument("--format", choices=["json", "table"], default="table")
        p.set_defaults(handler=cmd_list_objects, object_type=object_type)

    p = sub.add_parser("show", help="Show one object.")
    p.add_argument("object")
    p.add_argument("--format", choices=["json", "markdown"], default="json")
    p.set_defaults(handler=cmd_show_object)

    p = sub.add_parser("context", help="Show object context.")
    p.add_argument("object")
    p.add_argument("--format", choices=["json", "markdown"], default="markdown")
    p.add_argument("--no-redact", action="store_true")
    p.add_argument("--record-limit", type=int, default=80)
    p.set_defaults(handler=cmd_context_object)

    agent = sub.add_parser("agent", help="Agent-facing context commands.")
    agent_sub = agent.add_subparsers(dest="agent_command")
    p = agent_sub.add_parser("context", help="Export broad agent context.")
    p.add_argument("--type", choices=["project", "task", "idea"])
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--format", choices=["json", "markdown"], default="json")
    p.add_argument("--no-redact", action="store_true")
    p.set_defaults(handler=cmd_agent_context)
    p = agent_sub.add_parser("today-context", help="Export recent evidence for an external agent deciding what to inspect today.")
    p.add_argument("--days", type=int, default=14)
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--format", choices=["json", "markdown"], default="markdown")
    p.add_argument("--include-annotations", dest="include_annotations", action="store_true", default=True)
    p.add_argument("--no-annotations", dest="include_annotations", action="store_false")
    p.add_argument("--redact", dest="redact", action="store_true", default=True)
    p.add_argument("--no-redact", dest="redact", action="store_false")
    p.set_defaults(handler=cmd_agent_today_context)
    p = agent_sub.add_parser("project-context", help="Export one project context for external agent diagnosis.")
    p.add_argument("project")
    p.add_argument("--days", type=int, default=30)
    p.add_argument("--limit", type=int, default=80)
    p.add_argument("--format", choices=["json", "markdown"], default="markdown")
    p.add_argument("--include-annotations", dest="include_annotations", action="store_true", default=True)
    p.add_argument("--no-annotations", dest="include_annotations", action="store_false")
    p.add_argument("--redact", dest="redact", action="store_true", default=True)
    p.add_argument("--no-redact", dest="redact", action="store_false")
    p.set_defaults(handler=cmd_agent_project_context)
    p = agent_sub.add_parser("inbox-context", help="Export idea inbox context for external agent triage.")
    p.add_argument("--days", type=int, default=30)
    p.add_argument("--limit", type=int, default=80)
    p.add_argument("--format", choices=["json", "markdown"], default="markdown")
    p.add_argument("--include-annotations", dest="include_annotations", action="store_true", default=True)
    p.add_argument("--no-annotations", dest="include_annotations", action="store_false")
    p.add_argument("--redact", dest="redact", action="store_true", default=True)
    p.add_argument("--no-redact", dest="redact", action="store_false")
    p.set_defaults(handler=cmd_agent_inbox_context)
    for name, object_type in (("project", "project"), ("task", "task"), ("ideas", "idea")):
        p = agent_sub.add_parser(name, help=f"Export agent context for {name}.")
        p.add_argument("object", nargs="?" if name == "ideas" else None)
        p.add_argument("--limit", type=int, default=20)
        p.add_argument("--format", choices=["json", "markdown"], default="json")
        p.add_argument("--no-redact", action="store_true")
        p.set_defaults(handler=cmd_agent_specific, object_type=object_type)

    ann = sub.add_parser("annotation", help="Store and query annotations.")
    ann_sub = ann.add_subparsers(dest="annotation_command")
    p = ann_sub.add_parser("add", help="Add an annotation to an object.")
    p.add_argument("parts", nargs="+", help="Either <object> <content> or <content> when --record is used.")
    p.add_argument("--record", help="Target record id or source_item_id.")
    p.add_argument("--author", default="agent")
    p.add_argument("--type", default="comment")
    p.set_defaults(handler=cmd_annotation_add)
    p = ann_sub.add_parser("list", help="List annotations.")
    p.add_argument("--object")
    p.add_argument("--record")
    p.add_argument("--status")
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--format", choices=["json", "table"], default="table")
    p.set_defaults(handler=cmd_annotation_list)
    p = ann_sub.add_parser("status", help="Update annotation status.")
    p.add_argument("annotation_id", type=int)
    p.add_argument("status", choices=["open", "accepted", "rejected", "archived"])
    p.set_defaults(handler=cmd_annotation_status)

    report = sub.add_parser("report", help="Human-readable lightweight reports.")
    report_sub = report.add_subparsers(dest="report_command")
    p = report_sub.add_parser("active-projects", help="Show lightweight active project status.")
    p.add_argument("--limit", type=int, default=100)
    p.add_argument("--format", choices=["json", "markdown"], default="markdown")
    p.set_defaults(handler=cmd_report_active_projects)
    p = report_sub.add_parser("recent-unresolved-tasks", help="Show recent unresolved tasks.")
    p.add_argument("--days", type=int, default=14)
    p.add_argument("--limit", type=int, default=100)
    p.add_argument("--format", choices=["json", "markdown"], default="markdown")
    p.set_defaults(handler=cmd_report_recent_unresolved_tasks)
    p = report_sub.add_parser("extraction-quality", help="Show extraction quality diagnostics.")
    p.add_argument("--format", choices=["json", "markdown"], default="markdown")
    p.set_defaults(handler=cmd_report_extraction_quality)

    view = sub.add_parser("view", help="Short human-readable views.")
    view_sub = view.add_subparsers(dest="view_command")
    for name, handler, default_limit in (
        ("today", cmd_view_today, 12),
        ("projects", cmd_view_projects, 20),
        ("tasks", cmd_view_tasks, 20),
        ("ideas", cmd_view_ideas, 20),
        ("inbox", cmd_view_inbox, 20),
    ):
        p = view_sub.add_parser(name, help=f"Show {name} view.")
        p.add_argument("--brief", dest="detail", action="store_false", default=False)
        p.add_argument("--detail", dest="detail", action="store_true")
        p.add_argument("--limit", type=int, default=default_limit)
        p.set_defaults(handler=handler)
    p = view_sub.add_parser("project", help="Show one project view.")
    p.add_argument("project")
    p.add_argument("--brief", dest="detail", action="store_false", default=False)
    p.add_argument("--detail", dest="detail", action="store_true")
    p.add_argument("--limit", type=int, default=12)
    p.set_defaults(handler=cmd_view_project)

    debug = sub.add_parser("debug", help="Debug Logseq parsing and storage.")
    debug_sub = debug.add_subparsers(dest="debug_command")
    p = debug_sub.add_parser("parse-file", help="Parse one Logseq markdown file.")
    p.add_argument("path")
    p.add_argument("--format", choices=["json", "table"], default="json")
    p.set_defaults(handler=cmd_debug_parse_file)
    p = debug_sub.add_parser("block", help="Find a Logseq block by uuid.")
    p.add_argument("uuid")
    p.set_defaults(handler=cmd_debug_block)
    p = debug_sub.add_parser("refs", help="Find refs to a Logseq block uuid.")
    p.add_argument("uuid")
    p.set_defaults(handler=cmd_debug_refs)
    p = debug_sub.add_parser("stats", help="Show database stats.")
    p.set_defaults(handler=cmd_debug_stats)

    export = sub.add_parser("export", help="Export deep local reports from the indexed database.")
    export_sub = export.add_subparsers(dest="export_command")
    p = export_sub.add_parser("snapshot", help="Generate full Markdown and JSONL snapshot reports.")
    p.add_argument("--output-dir", help="Output directory. Defaults to reports/current-system-<timestamp>.")
    p.add_argument("--no-redact", action="store_true", help="Include raw text without redaction.")
    p.add_argument("--chunk-size", type=int, default=500, help="Objects per Markdown chunk.")
    p.set_defaults(handler=cmd_export_snapshot)

    write = sub.add_parser("write", help="Create, preview, and apply guarded write proposals.")
    write_sub = write.add_subparsers(dest="write_command")
    p = write_sub.add_parser("append-child", help="Propose appending a child block to a Logseq block object.")
    p.add_argument("content")
    p.add_argument("--object", help="Target object id/source id/title.")
    p.add_argument("--file", help="Target Logseq markdown file.")
    p.add_argument("--uuid", help="Target block uuid.")
    p.add_argument("--line", type=int, help="Target block line.")
    p.add_argument("--author", default="agent")
    p.set_defaults(handler=cmd_write_append_child)
    p = write_sub.add_parser("append-section", help="Propose appending a block under a page section marker.")
    p.add_argument("content")
    p.add_argument("--section", required=True, help="Section marker, for example [反思].")
    p.add_argument("--object", help="Project/page object id/source id/title.")
    p.add_argument("--file", help="Target Logseq markdown file.")
    p.add_argument("--author", default="agent")
    p.set_defaults(handler=cmd_write_append_section)
    p = write_sub.add_parser("create-page", help="Propose creating a new Logseq page.")
    p.add_argument("page_name")
    p.add_argument("content")
    p.add_argument("--author", default="agent")
    p.set_defaults(handler=cmd_write_create_page)
    p = write_sub.add_parser("list", help="List write proposals.")
    p.add_argument("--status")
    p.add_argument("--limit", type=int, default=50)
    p.set_defaults(handler=cmd_write_list)
    p = write_sub.add_parser("preview", help="Show a write proposal diff.")
    p.add_argument("proposal_id", type=int)
    p.add_argument("--format", choices=["json", "diff"], default="diff")
    p.add_argument("--no-redact", action="store_true", help="Show raw diff without redaction.")
    p.set_defaults(handler=cmd_write_preview)
    p = write_sub.add_parser("apply", help="Apply an open write proposal.")
    p.add_argument("proposal_id", type=int)
    p.add_argument("--yes", action="store_true", help="Confirm the guarded write.")
    p.set_defaults(handler=cmd_write_apply)
    p = write_sub.add_parser("reject", help="Reject an open write proposal.")
    p.add_argument("proposal_id", type=int)
    p.set_defaults(handler=cmd_write_reject)

    proposal = sub.add_parser("proposal", help="Review and apply structured change proposals.")
    proposal_sub = proposal.add_subparsers(dest="proposal_command")
    p = proposal_sub.add_parser("create-annotation", help="Create a low-risk internal annotation proposal.")
    p.add_argument("content")
    p.add_argument("--object")
    p.add_argument("--record")
    p.add_argument("--author", default="agent")
    p.set_defaults(handler=cmd_proposal_create_annotation)
    p = proposal_sub.add_parser("create-marker", help="Create a Logseq marker writeback proposal.")
    p.add_argument("marker", choices=["注", "AI注", "待澄清", "成果", "无成果"])
    p.add_argument("content")
    p.add_argument("--object")
    p.add_argument("--file")
    p.add_argument("--uuid")
    p.add_argument("--line", type=int)
    p.add_argument("--author", default="agent")
    p.set_defaults(handler=cmd_proposal_create_marker)
    p = proposal_sub.add_parser("create-task-marker", help="Create a Logseq task marker change proposal.")
    p.add_argument("marker", choices=["TODO", "DOING", "DONE", "WAITING"])
    p.add_argument("--object")
    p.add_argument("--file")
    p.add_argument("--uuid")
    p.add_argument("--line", type=int)
    p.add_argument("--author", default="agent")
    p.set_defaults(handler=cmd_proposal_create_task_marker)
    p = proposal_sub.add_parser("list", help="List proposals.")
    p.add_argument("--status")
    p.add_argument("--review", type=int)
    p.add_argument("--limit", type=int, default=50)
    p.set_defaults(handler=cmd_proposal_list)
    p = proposal_sub.add_parser("show", help="Show a proposal.")
    p.add_argument("proposal_id", type=int)
    p.add_argument("--preview", action="store_true")
    p.set_defaults(handler=cmd_proposal_show)
    p = proposal_sub.add_parser("accept", help="Accept a suggested proposal.")
    p.add_argument("proposal_id", type=int)
    p.set_defaults(handler=cmd_proposal_accept)
    p = proposal_sub.add_parser("reject", help="Reject a suggested proposal.")
    p.add_argument("proposal_id", type=int)
    p.set_defaults(handler=cmd_proposal_reject)
    p = proposal_sub.add_parser("apply", help="Apply an accepted proposal.")
    p.add_argument("proposal_id", type=int)
    p.add_argument("--yes", action="store_true", help="Confirm guarded Logseq writeback.")
    p.set_defaults(handler=cmd_proposal_apply)
    p = proposal_sub.add_parser("rollback", help="Roll back an applied proposal when possible.")
    p.add_argument("proposal_id", type=int)
    p.set_defaults(handler=cmd_proposal_rollback)

    review = sub.add_parser("review", help="Create and inspect review sessions.")
    review_sub = review.add_subparsers(dest="review_command")
    p = review_sub.add_parser("start", help="Start a review session.")
    p.add_argument("--type", required=True, choices=["inbox", "today", "selected"])
    p.add_argument("--ids", nargs="*", default=[])
    p.add_argument("--title")
    p.set_defaults(handler=cmd_review_start)
    p = review_sub.add_parser("list", help="List review sessions.")
    p.add_argument("--status")
    p.add_argument("--limit", type=int, default=50)
    p.set_defaults(handler=cmd_review_list)
    p = review_sub.add_parser("show", help="Show a review session.")
    p.add_argument("review_id", type=int)
    p.set_defaults(handler=cmd_review_show)
    p = review_sub.add_parser("proposals", help="List proposals generated in a review session.")
    p.add_argument("review_id", type=int)
    p.set_defaults(handler=cmd_review_proposals)
    p = review_sub.add_parser("status", help="Set review status.")
    p.add_argument("review_id", type=int)
    p.add_argument("status", choices=["open", "in_progress", "paused", "completed", "cancelled"])
    p.set_defaults(handler=cmd_review_status)
    p = review_sub.add_parser("close", help="Close a review session.")
    p.add_argument("review_id", type=int)
    p.add_argument("--cancel", action="store_true")
    p.set_defaults(handler=cmd_review_close)
    return parser


def _settings() -> Settings:
    return Settings.load()


def _conn(settings: Settings = None):
    settings = settings or _settings()
    conn = connect(settings.database_path)
    init_db(conn)
    return conn


def _service() -> QueryService:
    settings = _settings()
    return QueryService(_conn(settings), sensitive_patterns=settings.sensitive_patterns)


def cmd_config_init(args) -> str:
    settings = init_settings(args.graph, args.db)
    conn = connect(settings.database_path)
    init_db(conn)
    conn.commit()
    return to_json({"config_path": str(default_config_path()), "database_path": str(settings.database_path), "logseq_graph_path": str(settings.logseq_graph_path)})


def cmd_config_set_logseq(args) -> str:
    settings = init_settings(graph_path=args.graph)
    return to_json({"logseq_graph_path": str(settings.logseq_graph_path)})


def cmd_config_set_write_mode(args) -> str:
    settings = _settings()
    settings.write_mode = args.mode
    if args.require_confirm is not None:
        settings.write_require_confirm = args.require_confirm
    settings.save()
    return to_json({"write_mode": settings.write_mode, "write_require_confirm": settings.write_require_confirm})


def cmd_config_show(args) -> str:
    settings = _settings()
    data = {
        "config_path": str(default_config_path()),
        "app_dir": str(settings.app_dir),
        "database_path": str(settings.database_path),
        "logseq_graph_path": str(settings.logseq_graph_path) if settings.logseq_graph_path else None,
        "sensitive_patterns": settings.sensitive_patterns,
        "ignored_embed_uuids": settings.ignored_embed_uuids,
        "default_redact": settings.default_redact,
        "write_mode": settings.write_mode,
        "write_backup_dir": str(settings.write_backup_dir) if settings.write_backup_dir else None,
        "write_require_confirm": settings.write_require_confirm,
        "allowed_write_operations": settings.allowed_write_operations,
    }
    return to_json(data)


def cmd_doctor(args) -> str:
    settings = _settings()
    conn = _conn(settings)
    repo = Repository(conn)
    graph = settings.logseq_graph_path
    data = {
        "config_path": str(default_config_path()),
        "database_path": str(settings.database_path),
        "database_ok": True,
        "logseq_graph_path": str(graph) if graph else None,
        "logseq_graph_exists": bool(graph and Path(graph).exists()),
        "logseq_pages_exists": bool(graph and (Path(graph) / "pages").exists()),
        "logseq_journals_exists": bool(graph and (Path(graph) / "journals").exists()),
        "stats": repo.stats(),
        "write_mode": settings.write_mode,
        "write_require_confirm": settings.write_require_confirm,
        "write_backup_dir": str(settings.write_backup_dir) if settings.write_backup_dir else None,
    }
    return to_json(data)


def cmd_sync_logseq(args) -> str:
    settings = _settings()
    conn = _conn(settings)
    result = SyncService(conn, settings).sync_logseq(dry_run=args.dry_run, recent_journals=args.recent_journals)
    return to_json(result)


def cmd_sync_all(args) -> str:
    settings = _settings()
    conn = _conn(settings)
    result = SyncService(conn, settings).sync_all(dry_run=args.dry_run, recent_journals=args.recent_journals)
    return to_json(result)


def cmd_sync_runs(args) -> str:
    repo = Repository(_conn())
    data = repo.list_sync_runs(limit=args.limit)
    return format_output(data, args.format, table_kind="sync_runs")


def cmd_sync_status(args) -> str:
    repo = Repository(_conn())
    return to_json({"stats": repo.stats(), "recent_runs": repo.list_sync_runs(limit=5)})


def cmd_list_objects(args) -> str:
    service = _service()
    data = service.list_objects(object_type=args.object_type, status=args.status, limit=args.limit)
    return format_output(data, args.format)


def cmd_show_object(args) -> str:
    data = _service().show_object(args.object)
    return format_output(data, args.format)


def cmd_context_object(args) -> str:
    data = _service().object_context(args.object, redact=not args.no_redact, record_limit=args.record_limit)
    return format_output(data, args.format)


def cmd_agent_context(args) -> str:
    data = _service().agent_context(object_type=args.type, limit=args.limit, redact=not args.no_redact)
    return format_output(data, args.format)


def _agent_view_service():
    settings = _settings()
    return AgentViewService(_conn(settings), sensitive_patterns=settings.sensitive_patterns)


def _human_view_service():
    settings = _settings()
    return HumanViewService(_conn(settings), sensitive_patterns=settings.sensitive_patterns)


def _format_agent_view(data, fmt: str) -> str:
    if fmt == "json":
        return to_json(data)
    return _agent_view_service().markdown(data)


def cmd_agent_today_context(args) -> str:
    service = _agent_view_service()
    data = service.today_context(days=args.days, limit=args.limit, redact=args.redact, include_annotations=args.include_annotations)
    return to_json(data) if args.format == "json" else service.markdown(data)


def cmd_agent_project_context(args) -> str:
    service = _agent_view_service()
    data = service.project_context(args.project, days=args.days, limit=args.limit, redact=args.redact, include_annotations=args.include_annotations)
    return to_json(data) if args.format == "json" else service.markdown(data)


def cmd_agent_inbox_context(args) -> str:
    service = _agent_view_service()
    data = service.inbox_context(days=args.days, limit=args.limit, redact=args.redact, include_annotations=args.include_annotations)
    return to_json(data) if args.format == "json" else service.markdown(data)


def cmd_agent_specific(args) -> str:
    service = _service()
    if getattr(args, "object", None):
        data = service.object_context(args.object, redact=not args.no_redact)
    else:
        data = service.agent_context(object_type=args.object_type, limit=args.limit, redact=not args.no_redact)
    return format_output(data, args.format)


def cmd_annotation_add(args) -> str:
    settings = _settings()
    conn = _conn(settings)
    if args.record:
        target_object = None
        content = " ".join(args.parts)
    else:
        if len(args.parts) < 2:
            raise ValueError("annotation add requires <object> <content>, or <content> with --record.")
        target_object = args.parts[0]
        content = " ".join(args.parts[1:])
    ann_id = AnnotationService(conn).add(target_object, content, author=args.author, annotation_type=args.type, target_record_ref=args.record)
    conn.commit()
    return to_json({"annotation_id": ann_id})


def cmd_annotation_list(args) -> str:
    data = AnnotationService(_conn()).list(target_object_ref=args.object, target_record_ref=args.record, status=args.status, limit=args.limit)
    return format_output(data, args.format, table_kind="annotations")


def cmd_annotation_status(args) -> str:
    conn = _conn()
    AnnotationService(conn).update_status(args.annotation_id, args.status)
    conn.commit()
    return to_json({"annotation_id": args.annotation_id, "status": args.status})


def cmd_debug_parse_file(args) -> str:
    adapter = LogseqAdapter(Path(args.path).parent.parent if Path(args.path).parent.name in {"pages", "journals"} else Path(args.path).parent)
    result = adapter.parse_file(Path(args.path))
    data = {
        "files_scanned": result.files_scanned,
        "objects": [obj.__dict__ for obj in result.objects],
        "records": [{"source_item_id": rec.source_item_id, "raw_text": rec.raw_text, "metadata": rec.metadata} for rec in result.records],
        "relations": [rel.__dict__ for rel in result.relations],
        "warnings": [warning.__dict__ for warning in result.warnings],
    }
    return to_json(data)


def _resolver() -> LogseqResolver:
    settings = _settings()
    if not settings.logseq_graph_path:
        raise ConfigError("Logseq graph path is not configured.")
    return LogseqResolver(settings.logseq_graph_path).build()


def cmd_debug_block(args) -> str:
    block = _resolver().get(args.uuid)
    if not block:
        raise NotFoundError(f"Block not found: {args.uuid}")
    return to_json({"uuid": args.uuid, "text": block.text, "file_path": str(block.file_path), "line": block.line_number, "block_path": block.block_path()})


def cmd_debug_refs(args) -> str:
    refs = _resolver().references_to(args.uuid)
    return to_json([{"text": block.text, "file_path": str(block.file_path), "line": block.line_number} for block in refs])


def cmd_debug_stats(args) -> str:
    return to_json(Repository(_conn()).stats())


def cmd_report_active_projects(args) -> str:
    service = _agent_view_service()
    data = service.active_projects_report(limit=args.limit)
    return to_json(data) if args.format == "json" else service.markdown(data)


def cmd_report_recent_unresolved_tasks(args) -> str:
    service = _agent_view_service()
    data = service.recent_unresolved_tasks_report(days=args.days, limit=args.limit)
    return to_json(data) if args.format == "json" else service.markdown(data)


def cmd_report_extraction_quality(args) -> str:
    service = _agent_view_service()
    data = service.extraction_quality_report()
    return to_json(data) if args.format == "json" else service.markdown(data)


def cmd_view_today(args) -> str:
    return _human_view_service().today(limit=args.limit, detail=args.detail)


def cmd_view_projects(args) -> str:
    return _human_view_service().projects(limit=args.limit, detail=args.detail)


def cmd_view_project(args) -> str:
    return _human_view_service().project(args.project, limit=args.limit, detail=args.detail)


def cmd_view_tasks(args) -> str:
    return _human_view_service().tasks(limit=args.limit, detail=args.detail)


def cmd_view_ideas(args) -> str:
    return _human_view_service().ideas(limit=args.limit, detail=args.detail)


def cmd_view_inbox(args) -> str:
    return _human_view_service().inbox(limit=args.limit, detail=args.detail)


def cmd_export_snapshot(args) -> str:
    settings = _settings()
    conn = _conn(settings)
    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        from datetime import datetime

        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        output_dir = Path.cwd() / "reports" / f"current-system-{stamp}"
    result = SnapshotExporter(conn, sensitive_patterns=settings.sensitive_patterns).export(
        output_dir,
        redact=not args.no_redact,
        chunk_size=args.chunk_size,
    )
    return to_json(result)


def _write_service():
    settings = _settings()
    return WriteService(_conn(settings), settings)


def cmd_write_append_child(args) -> str:
    settings = _settings()
    conn = _conn(settings)
    proposal_id = WriteService(conn, settings).create_append_child_proposal(
        args.content,
        target_object_ref=args.object,
        file_path=args.file,
        block_uuid=args.uuid,
        line_start=args.line,
        author=args.author,
    )
    conn.commit()
    return to_json({"proposal_id": proposal_id, "status": "open"})


def cmd_write_append_section(args) -> str:
    settings = _settings()
    conn = _conn(settings)
    proposal_id = WriteService(conn, settings).create_append_page_section_proposal(
        args.content,
        section_marker=args.section,
        target_object_ref=args.object,
        file_path=args.file,
        author=args.author,
    )
    conn.commit()
    return to_json({"proposal_id": proposal_id, "status": "open"})


def cmd_write_create_page(args) -> str:
    settings = _settings()
    conn = _conn(settings)
    proposal_id = WriteService(conn, settings).create_page_proposal(args.page_name, args.content, author=args.author)
    conn.commit()
    return to_json({"proposal_id": proposal_id, "status": "open"})


def cmd_write_list(args) -> str:
    return to_json(_write_service().list_proposals(status=args.status, limit=args.limit))


def cmd_write_preview(args) -> str:
    settings = _settings()
    proposal = WriteService(_conn(settings), settings).preview(args.proposal_id)
    if not args.no_redact:
        redactor = Redactor(settings.sensitive_patterns)
        proposal = dict(proposal)
        proposal["preview_diff"] = redactor.redact(proposal["preview_diff"]).text
    if args.format == "diff":
        return proposal["preview_diff"]
    return to_json(proposal)


def cmd_write_apply(args) -> str:
    settings = _settings()
    conn = _conn(settings)
    result = WriteService(conn, settings).apply(args.proposal_id, confirmed=args.yes)
    conn.commit()
    return to_json(result)


def cmd_write_reject(args) -> str:
    settings = _settings()
    conn = _conn(settings)
    WriteService(conn, settings).reject(args.proposal_id)
    conn.commit()
    return to_json({"proposal_id": args.proposal_id, "status": "rejected"})


def _proposal_service(conn=None):
    settings = _settings()
    return ProposalService(conn or _conn(settings), settings)


def cmd_proposal_create_annotation(args) -> str:
    conn = _conn()
    proposal_id = ProposalService(conn, _settings()).create_annotation(args.content, target_object_ref=args.object, target_record_ref=args.record, author=args.author)
    conn.commit()
    return to_json({"proposal_id": proposal_id, "status": "suggested"})


def cmd_proposal_create_marker(args) -> str:
    settings = _settings()
    conn = _conn(settings)
    proposal_id = ProposalService(conn, settings).create_logseq_marker(
        args.marker,
        args.content,
        target_object_ref=args.object,
        file_path=args.file,
        block_uuid=args.uuid,
        line_start=args.line,
        source=args.author,
    )
    conn.commit()
    return to_json({"proposal_id": proposal_id, "status": "suggested"})


def cmd_proposal_create_task_marker(args) -> str:
    settings = _settings()
    conn = _conn(settings)
    proposal_id = ProposalService(conn, settings).create_task_marker(
        args.marker,
        target_object_ref=args.object,
        file_path=args.file,
        block_uuid=args.uuid,
        line_start=args.line,
        source=args.author,
    )
    conn.commit()
    return to_json({"proposal_id": proposal_id, "status": "suggested"})


def cmd_proposal_list(args) -> str:
    return to_json(_proposal_service().list(status=args.status, review_session_id=args.review, limit=args.limit))


def cmd_proposal_show(args) -> str:
    settings = _settings()
    conn = _conn(settings)
    service = ProposalService(conn, settings)
    data = service.preview(args.proposal_id) if args.preview else service.get(args.proposal_id)
    if args.preview:
        conn.commit()
    return to_json(data)


def cmd_proposal_accept(args) -> str:
    conn = _conn()
    ProposalService(conn, _settings()).accept(args.proposal_id)
    conn.commit()
    return to_json({"proposal_id": args.proposal_id, "status": "accepted"})


def cmd_proposal_reject(args) -> str:
    conn = _conn()
    ProposalService(conn, _settings()).reject(args.proposal_id)
    conn.commit()
    return to_json({"proposal_id": args.proposal_id, "status": "rejected"})


def cmd_proposal_apply(args) -> str:
    settings = _settings()
    conn = _conn(settings)
    result = ProposalService(conn, settings).apply(args.proposal_id, confirmed=args.yes)
    conn.commit()
    return to_json(result)


def cmd_proposal_rollback(args) -> str:
    settings = _settings()
    conn = _conn(settings)
    result = ProposalService(conn, settings).rollback(args.proposal_id)
    conn.commit()
    return to_json(result)


def cmd_review_start(args) -> str:
    conn = _conn()
    review_id = ReviewSessionService(conn).start(args.type, item_refs=args.ids, title=args.title)
    conn.commit()
    return to_json({"review_id": review_id, "status": "open"})


def cmd_review_list(args) -> str:
    return to_json(ReviewSessionService(_conn()).list(status=args.status, limit=args.limit))


def cmd_review_show(args) -> str:
    return to_json(ReviewSessionService(_conn()).show(args.review_id))


def cmd_review_proposals(args) -> str:
    return to_json(ReviewSessionService(_conn()).proposals(args.review_id))


def cmd_review_status(args) -> str:
    conn = _conn()
    ReviewSessionService(conn).set_status(args.review_id, args.status)
    conn.commit()
    return to_json({"review_id": args.review_id, "status": args.status})


def cmd_review_close(args) -> str:
    conn = _conn()
    ReviewSessionService(conn).close(args.review_id, cancelled=args.cancel)
    conn.commit()
    return to_json({"review_id": args.review_id, "status": "cancelled" if args.cancel else "completed"})


if __name__ == "__main__":
    raise SystemExit(main())
