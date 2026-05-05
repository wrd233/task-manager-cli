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
from task_manager_cli.query.exporter import SnapshotExporter
from task_manager_cli.query.service import QueryService
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
    p.add_argument("object")
    p.add_argument("content")
    p.add_argument("--author", default="agent")
    p.add_argument("--type", default="comment")
    p.set_defaults(handler=cmd_annotation_add)
    p = ann_sub.add_parser("list", help="List annotations.")
    p.add_argument("--object")
    p.add_argument("--status")
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--format", choices=["json", "table"], default="table")
    p.set_defaults(handler=cmd_annotation_list)
    p = ann_sub.add_parser("status", help="Update annotation status.")
    p.add_argument("annotation_id", type=int)
    p.add_argument("status", choices=["open", "accepted", "rejected", "archived"])
    p.set_defaults(handler=cmd_annotation_status)

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
    ann_id = AnnotationService(conn).add(args.object, args.content, author=args.author, annotation_type=args.type)
    conn.commit()
    return to_json({"annotation_id": ann_id})


def cmd_annotation_list(args) -> str:
    data = AnnotationService(_conn()).list(target_object_ref=args.object, status=args.status, limit=args.limit)
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


if __name__ == "__main__":
    raise SystemExit(main())
