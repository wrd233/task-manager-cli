import json
from typing import Any, Dict, Iterable, List


def to_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, default=str)


def objects_table(objects: List[Dict[str, Any]]) -> str:
    if not objects:
        return "No objects found."
    headers = ["id", "type", "status", "title", "page", "line"]
    rows = []
    for obj in objects:
        rows.append([
            str(obj.get("id", "")),
            str(obj.get("object_type", "")),
            str(obj.get("status") or ""),
            str(obj.get("title", ""))[:60],
            str(obj.get("page_name") or ""),
            str(obj.get("line_start") or ""),
        ])
    return _plain_table(headers, rows)


def annotations_table(items: List[Dict[str, Any]]) -> str:
    if not items:
        return "No annotations found."
    rows = []
    for item in items:
        rows.append([
            str(item.get("id", "")),
            str(item.get("status", "")),
            str(item.get("annotation_type", "")),
            str(item.get("author", "")),
            str(item.get("object_title") or item.get("target_object_id") or ""),
            str(item.get("content", ""))[:70],
        ])
    return _plain_table(["id", "status", "type", "author", "target", "content"], rows)


def sync_runs_table(items: List[Dict[str, Any]]) -> str:
    if not items:
        return "No sync runs found."
    rows = []
    for item in items:
        rows.append([
            str(item.get("id", "")),
            str(item.get("adapter", "")),
            str(item.get("status", "")),
            str(item.get("started_at", "")),
            str(item.get("files_scanned", "")),
            str(item.get("objects_seen", "")),
            str(item.get("records_seen", "")),
        ])
    return _plain_table(["id", "adapter", "status", "started", "files", "objects", "records"], rows)


def context_markdown(package: Dict[str, Any]) -> str:
    lines: List[str] = []
    if "packages" in package:
        lines.append("# Agent Context")
        for child in package["packages"]:
            lines.append(context_markdown(child))
        return "\n\n".join(lines)
    obj = package.get("objects", [{}])[0]
    lines.append(f"# {obj.get('object_type', 'object')}: {obj.get('title', '')}")
    lines.append(f"- id: {obj.get('id')}")
    lines.append(f"- status: {obj.get('status')}")
    lines.append(f"- source: {obj.get('canonical_source')} / {obj.get('source_item_id')}")
    lines.append(f"- location: {obj.get('file_path')}:{obj.get('line_start') or ''}")
    lines.append("\n## Records")
    for record in package.get("records", []):
        lines.append(f"- `{record.get('role', record.get('record_type'))}` {record.get('file_path')}:{record.get('line_start')}")
        lines.append(f"  {record.get('raw_text', '').strip()}")
    if package.get("annotations"):
        lines.append("\n## Annotations")
        for annotation in package["annotations"]:
            lines.append(f"- [{annotation.get('status')}] {annotation.get('annotation_type')} by {annotation.get('author')}: {annotation.get('content')}")
    lines.append(f"\n_Redaction: {package.get('redaction')}_")
    return "\n".join(lines)


def format_output(data: Any, fmt: str, table_kind: str = "objects") -> str:
    if fmt == "json":
        return to_json(data)
    if fmt == "markdown":
        if isinstance(data, dict):
            return context_markdown(data)
        return to_json(data)
    if table_kind == "annotations":
        return annotations_table(data)
    if table_kind == "sync_runs":
        return sync_runs_table(data)
    if isinstance(data, dict):
        return to_json(data)
    return objects_table(data)


def _plain_table(headers: List[str], rows: List[List[str]]) -> str:
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))
    def line(values: List[str]) -> str:
        return "  ".join(value.ljust(widths[i]) for i, value in enumerate(values))
    return "\n".join([line(headers), line(["-" * w for w in widths])] + [line(row) for row in rows])
