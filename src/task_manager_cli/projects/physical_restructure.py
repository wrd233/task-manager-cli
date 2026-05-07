"""Conservative physical project-page restructuring for Logseq graphs."""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from task_manager_cli.adapters.logseq.extractors import semantic_marker


STANDARD_SECTIONS = ["目标", "项目收件箱", "具体事务", "小任务", "资源", "成果", "想法", "反思"]
PLACED_SECTIONS = {"目标", "里程碑", "工作流", "具体事务", "小任务", "资源", "成果", "想法", "反思", "无成果"}
INBOX_SECTIONS = {"项目收件箱", "待澄清"}
MARKER_RENAMES = {
    "具体目标": "目标",
    "资源列表": "资源",
    "头脑风暴": "想法",
}
TASK_RE = re.compile(r"^\s*-\s*(TODO|DOING|DONE|WAITING)\b")
LINK_RE = re.compile(r"https?://|\[\[[^\]]+\]\]|\(\([0-9a-fA-F-]{8,}\)\)")
ID_RE = re.compile(r"^\s*id::\s*")
BULLET_RE = re.compile(r"^(\s*)-\s+(.*)$")
SENSITIVE_RE = re.compile(r"(api[_-]?key|token|cookie|password|secret|sk-[A-Za-z0-9])", re.IGNORECASE)


@dataclass
class ProjectFileMetrics:
    line_count: int
    non_empty_line_count: int
    bullet_count: int
    task_count: int
    link_count: int
    id_property_count: int
    sha256: str


@dataclass
class ProjectRestructureResult:
    project_id: int
    title: str
    file_path: str
    classification: str
    modified: bool
    skipped: bool
    skip_reason: Optional[str]
    before: ProjectFileMetrics
    after: ProjectFileMetrics
    renamed_markers: Dict[str, int]
    added_sections: List[str]
    existing_sections_before: List[str]
    existing_sections_after: List[str]
    preservation_ok: bool
    preservation_warnings: List[str]
    before_health: Optional[Dict[str, Any]] = None
    after_health: Optional[Dict[str, Any]] = None


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def metrics(text: str) -> ProjectFileMetrics:
    lines = text.splitlines()
    return ProjectFileMetrics(
        line_count=len(lines),
        non_empty_line_count=sum(1 for line in lines if line.strip()),
        bullet_count=sum(1 for line in lines if BULLET_RE.match(line)),
        task_count=sum(1 for line in lines if TASK_RE.match(line)),
        link_count=len(LINK_RE.findall(text)),
        id_property_count=sum(1 for line in lines if ID_RE.match(line)),
        sha256=sha256_text(text),
    )


def section_names(text: str) -> List[str]:
    names: List[str] = []
    for line in text.splitlines():
        marker = semantic_marker(line)
        if marker and marker not in names:
            names.append(marker)
    return names


def classify_project(row: Dict[str, Any]) -> str:
    title = row.get("title") or ""
    metadata = row.get("metadata") or {}
    props = metadata.get("page_properties") or {}
    reasons = set(metadata.get("reasons") or [])
    para = str(props.get("PARA") or props.get("para") or "")
    status = str(row.get("status") or props.get("state") or "")
    if title == "contents" or title.startswith("hypothesis__"):
        return "template-like"
    if props.get("type") in {"[[video]]", "[[article]]"} or props.get("source"):
        return "archive-candidate"
    if "PARA/Archive" in para or "已完成" in status or "Completed" in status:
        return "historical"
    if "para_project" in reasons:
        return "active"
    if title.startswith(("项目-", "任务-", "学习-", "课程-", "阶段-", "自学-", "旅游-", "英语-", "健身-", "创造-", "调研-")):
        return "stale"
    return "malformed"


def should_skip(classification: str, row: Dict[str, Any]) -> Optional[str]:
    if classification == "template-like":
        return "template-like or generated index page"
    title = row.get("title") or ""
    metadata = row.get("metadata") or {}
    props = metadata.get("page_properties") or {}
    if title.startswith("hypothesis__") or props.get("hypothesis-uri"):
        return "web annotation/article page, not a physical project workspace"
    return None


def restructure_text(text: str, *, project_title: str, classification: str) -> Tuple[str, Dict[str, int], List[str]]:
    lines = text.splitlines()
    renamed: Dict[str, int] = {}
    new_lines: List[str] = []
    for line in lines:
        updated = line
        for old, new in MARKER_RENAMES.items():
            changed = re.sub(rf"(\*\*)?\[{re.escape(old)}\](\*\*)?", lambda m: f"{m.group(1) or ''}[{new}]{m.group(2) or ''}", updated)
            if changed != updated:
                renamed[old] = renamed.get(old, 0) + 1
                updated = changed
        new_lines.append(updated)

    working = "\n".join(new_lines)
    if text.endswith("\n"):
        working += "\n"
    existing = set(section_names(working))
    missing = [section for section in STANDARD_SECTIONS if section not in existing]

    if classification in {"active", "stale", "malformed"} and "PARA:: [[PARA/Project]]" not in working:
        insert_at = _first_bullet_index(new_lines)
        props = ["PARA:: [[PARA/Project]]", "status:: active"]
        if insert_at is None:
            new_lines = props + [""] + new_lines
        else:
            new_lines = new_lines[:insert_at] + props + [""] + new_lines[insert_at:]

    if missing:
        root_index = _project_root_index(new_lines)
        if root_index is not None:
            insert_at = _subtree_end_index(new_lines, root_index)
            prefix = _child_prefix(new_lines, root_index)
        else:
            insert_at = len(new_lines)
            prefix = ""
        section_block = _section_lines(missing, prefix)
        if insert_at > 0 and new_lines[insert_at - 1].strip():
            section_block = [""] + section_block
        new_lines = new_lines[:insert_at] + section_block + new_lines[insert_at:]

    result = "\n".join(new_lines).rstrip() + "\n"
    return result, renamed, missing


def preservation_warnings(before: ProjectFileMetrics, after: ProjectFileMetrics) -> List[str]:
    warnings: List[str] = []
    if after.non_empty_line_count < before.non_empty_line_count:
        warnings.append("non-empty line count decreased")
    if after.bullet_count < before.bullet_count:
        warnings.append("bullet count decreased")
    if after.task_count < before.task_count:
        warnings.append("task marker count decreased")
    if after.link_count < before.link_count:
        warnings.append("link/ref count decreased")
    if after.id_property_count < before.id_property_count:
        warnings.append("id:: property count decreased")
    return warnings


def apply_project(row: Dict[str, Any], *, apply: bool = False) -> ProjectRestructureResult:
    path = Path(row["file_path"])
    classification = classify_project(row)
    skip = should_skip(classification, row)
    original = path.read_text(encoding="utf-8")
    before = metrics(original)
    if skip:
        return ProjectRestructureResult(
            project_id=int(row["id"]),
            title=row["title"],
            file_path=str(path),
            classification=classification,
            modified=False,
            skipped=True,
            skip_reason=skip,
            before=before,
            after=before,
            renamed_markers={},
            added_sections=[],
            existing_sections_before=section_names(original),
            existing_sections_after=section_names(original),
            preservation_ok=True,
            preservation_warnings=[],
        )
    updated, renamed, added = restructure_text(original, project_title=row["title"], classification=classification)
    after = metrics(updated)
    warnings = preservation_warnings(before, after)
    modified = updated != original
    if apply and modified:
        path.write_text(updated, encoding="utf-8")
    return ProjectRestructureResult(
        project_id=int(row["id"]),
        title=row["title"],
        file_path=str(path),
        classification=classification,
        modified=modified,
        skipped=False,
        skip_reason=None,
        before=before,
        after=after,
        renamed_markers=renamed,
        added_sections=added,
        existing_sections_before=section_names(original),
        existing_sections_after=section_names(updated),
        preservation_ok=not warnings,
        preservation_warnings=warnings,
    )


def load_project_rows(database_path: Path) -> List[Dict[str, Any]]:
    conn = sqlite3.connect(database_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT o.id, o.title, o.status, o.metadata_json, l.file_path, l.page_name, l.line_start
        FROM objects o
        LEFT JOIN locations l ON l.id=o.canonical_location_id
        WHERE o.object_type='project' AND l.file_path IS NOT NULL
        ORDER BY o.id
        """
    ).fetchall()
    result: List[Dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["metadata"] = json.loads(item.pop("metadata_json") or "{}")
        if item.get("file_path") and Path(item["file_path"]).exists():
            result.append(item)
    conn.close()
    return result


def diff_summary(original: str, updated: str, path: Path, max_lines: int = 80) -> str:
    diff = list(difflib.unified_diff(original.splitlines(True), updated.splitlines(True), fromfile=str(path), tofile=str(path)))
    if len(diff) > max_lines:
        return "".join(diff[:max_lines]) + f"\n... diff truncated, total lines={len(diff)}\n"
    return "".join(diff)


def write_reports(results: List[ProjectRestructureResult], reports_dir: Path, *, backup_dir: Optional[Path], graph_path: Path) -> None:
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "projects").mkdir(parents=True, exist_ok=True)
    manifest = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "graph_path": str(graph_path),
        "backup_dir": str(backup_dir) if backup_dir else None,
        "scanned_projects": len(results),
        "modified_projects": sum(1 for item in results if item.modified),
        "skipped_projects": sum(1 for item in results if item.skipped),
        "failed_preservation_checks": [item.title for item in results if not item.preservation_ok],
        "projects": [_result_json(item) for item in results],
    }
    (reports_dir / "project_restructure_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (reports_dir / "summary.md").write_text(_summary_markdown(results, backup_dir, graph_path), encoding="utf-8")
    (reports_dir / "diff_summary.md").write_text(_diff_summary_markdown(results), encoding="utf-8")
    (reports_dir / "original_project_patterns.md").write_text(_patterns_markdown(results), encoding="utf-8")
    for item in results:
        report_path = reports_dir / "projects" / f"{_safe_filename(item.title)}.md"
        report_path.write_text(_project_markdown(item), encoding="utf-8")
    rollback = reports_dir / "rollback.sh"
    rollback.write_text(
        "#!/usr/bin/env bash\nset -euo pipefail\n"
        f"rsync -a {json.dumps(str(backup_dir / 'Logseq_File') + '/') if backup_dir else '<backup>/Logseq_File/'} {json.dumps(str(graph_path) + '/')}\n",
        encoding="utf-8",
    )
    rollback.chmod(0o755)


def _result_json(item: ProjectRestructureResult) -> Dict[str, Any]:
    data = asdict(item)
    return data


def _summary_markdown(results: List[ProjectRestructureResult], backup_dir: Optional[Path], graph_path: Path) -> str:
    modified = [item for item in results if item.modified]
    skipped = [item for item in results if item.skipped]
    failed = [item for item in results if not item.preservation_ok]
    classes: Dict[str, int] = {}
    for item in results:
        classes[item.classification] = classes.get(item.classification, 0) + 1
    lines = [
        "# Project Physical Restructure Summary",
        "",
        f"- graph path: `{graph_path}`",
        f"- backup: `{backup_dir}`",
        f"- scanned projects: `{len(results)}`",
        f"- modified projects: `{len(modified)}`",
        f"- skipped projects: `{len(skipped)}`",
        f"- preservation failures: `{len(failed)}`",
        f"- classification: `{classes}`",
        "",
        "## What Changed",
        "",
        "- Standardized legacy section aliases: `[具体目标] -> [目标]`, `[资源列表] -> [资源]`, `[头脑风暴] -> [想法]`.",
        "- Added missing standard Project sections without deleting or collapsing existing blocks.",
        "- Kept archive-like or generated pages conservative; skipped pages that were likely web annotations or indexes.",
        "",
        "## Modified Projects",
        "",
    ]
    if not modified:
        lines.append("- none")
    for item in modified:
        lines.append(f"- `{item.title}`: added={item.added_sections}, renamed={item.renamed_markers}")
    lines.extend(["", "## Skipped Projects", ""])
    if not skipped:
        lines.append("- none")
    for item in skipped:
        lines.append(f"- `{item.title}`: {item.skip_reason}")
    return "\n".join(lines).rstrip() + "\n"


def _diff_summary_markdown(results: List[ProjectRestructureResult]) -> str:
    lines = ["# Project Restructure Diff Summary", ""]
    for item in results:
        if not item.modified:
            continue
        lines.extend(
            [
                f"## {item.title}",
                "",
                f"- file: `{item.file_path}`",
                f"- before hash: `{item.before.sha256}`",
                f"- after hash: `{item.after.sha256}`",
                f"- lines: `{item.before.line_count}` -> `{item.after.line_count}`",
                f"- bullets: `{item.before.bullet_count}` -> `{item.after.bullet_count}`",
                f"- tasks: `{item.before.task_count}` -> `{item.after.task_count}`",
                f"- links: `{item.before.link_count}` -> `{item.after.link_count}`",
                f"- id properties: `{item.before.id_property_count}` -> `{item.after.id_property_count}`",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def _patterns_markdown(results: List[ProjectRestructureResult]) -> str:
    alias_counts: Dict[str, int] = {}
    missing_counts: Dict[str, int] = {}
    class_counts: Dict[str, int] = {}
    for item in results:
        class_counts[item.classification] = class_counts.get(item.classification, 0) + 1
        for key, value in item.renamed_markers.items():
            alias_counts[key] = alias_counts.get(key, 0) + value
        for section in item.added_sections:
            missing_counts[section] = missing_counts.get(section, 0) + 1
    return "\n".join(
        [
            "# Original Project Patterns",
            "",
            "## Common Structure Patterns",
            "",
            "- Most older projects used a single top project block with nested project sections.",
            "- The dominant historical aliases were `[具体目标]`, `[资源列表]`, and `[头脑风暴]`.",
            "- Course and learning projects commonly keep dense resources under a resource section and long TODO subtrees under concrete work.",
            "- Historical/archive pages often still carry project structure markers, so they need lighter treatment than active pages.",
            "",
            "## Common Drift Patterns",
            "",
            f"- alias replacements observed: `{alias_counts}`",
            f"- missing standard sections filled: `{missing_counts}`",
            f"- classification distribution: `{class_counts}`",
            "",
            "## CLI Capability Gaps Found",
            "",
            "- Project placement must understand section marker aliases, not only canonical marker names.",
            "- Unplaced detection should not treat every object on a project page as unplaced when it lives under a semantic section.",
            "- Reports need a physical migration manifest with before/after hashes and preservation counters.",
            "- Project discovery needs a way to separate true workspaces from article/highlight pages with project-like markers.",
            "",
            "## Recommended Marker Aliases",
            "",
            "- `[具体目标] -> [目标]`",
            "- `[资源列表] -> [资源]`",
            "- `[头脑风暴]` and `[随想] -> [想法]`",
            "- `[心得]`, `[复盘]`, `[经验] -> [反思]`",
            "- `[产出]`, `[交付物] -> [成果]`",
        ]
    ) + "\n"


def _project_markdown(item: ProjectRestructureResult) -> str:
    lines = [
        f"# {item.title}",
        "",
        f"- classification: `{item.classification}`",
        f"- file: `{item.file_path}`",
        f"- modified: `{item.modified}`",
        f"- skipped: `{item.skipped}`",
        f"- skip reason: `{item.skip_reason or ''}`",
        f"- before hash: `{item.before.sha256}`",
        f"- after hash: `{item.after.sha256}`",
        f"- line count: `{item.before.line_count}` -> `{item.after.line_count}`",
        f"- bullet count: `{item.before.bullet_count}` -> `{item.after.bullet_count}`",
        f"- task count: `{item.before.task_count}` -> `{item.after.task_count}`",
        f"- link count: `{item.before.link_count}` -> `{item.after.link_count}`",
        f"- id properties: `{item.before.id_property_count}` -> `{item.after.id_property_count}`",
        f"- renamed markers: `{item.renamed_markers}`",
        f"- added sections: `{item.added_sections}`",
        f"- sections before: `{item.existing_sections_before}`",
        f"- sections after: `{item.existing_sections_after}`",
        f"- preservation ok: `{item.preservation_ok}`",
        f"- preservation warnings: `{item.preservation_warnings}`",
    ]
    return "\n".join(lines).rstrip() + "\n"


def _section_lines(sections: List[str], prefix: str) -> List[str]:
    lines: List[str] = []
    for section in sections:
        lines.append(f"{prefix}- **[{section}]**")
        if section == "目标":
            lines.append(f"{prefix}    - **[待澄清]** 这个项目当前最重要的目标是什么？")
    return lines


def _first_bullet_index(lines: List[str]) -> Optional[int]:
    for index, line in enumerate(lines):
        if BULLET_RE.match(line):
            return index
    return None


def _project_root_index(lines: List[str]) -> Optional[int]:
    for index, line in enumerate(lines):
        match = BULLET_RE.match(line)
        if not match:
            continue
        text = match.group(2)
        lookahead = "\n".join(lines[index : index + 6])
        if "Project" in text or "#项目清单" in text or "type:: [[项目]]" in lookahead:
            return index
    return None


def _indent_width(prefix: str) -> int:
    return prefix.count("\t") * 4 + prefix.count(" ")


def _subtree_end_index(lines: List[str], root_index: int) -> int:
    root_match = BULLET_RE.match(lines[root_index])
    root_width = _indent_width(root_match.group(1) if root_match else "")
    for index in range(root_index + 1, len(lines)):
        match = BULLET_RE.match(lines[index])
        if match and _indent_width(match.group(1)) <= root_width:
            return index
    return len(lines)


def _child_prefix(lines: List[str], root_index: int) -> str:
    root_match = BULLET_RE.match(lines[root_index])
    root_prefix = root_match.group(1) if root_match else ""
    root_width = _indent_width(root_prefix)
    for line in lines[root_index + 1 :]:
        match = BULLET_RE.match(line)
        if match and _indent_width(match.group(1)) > root_width:
            return match.group(1)
    if any(line.startswith("\t-") for line in lines):
        return root_prefix + "\t"
    return root_prefix + "    "


def _safe_filename(name: str) -> str:
    cleaned = re.sub(r"[^\w\u4e00-\u9fff.-]+", "_", name).strip("_")
    return cleaned[:120] or "project"


def _redacted(text: str) -> str:
    if SENSITIVE_RE.search(text):
        return "[redacted]"
    return text


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Conservatively normalize Logseq project pages.")
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--graph", required=True, type=Path)
    parser.add_argument("--reports", required=True, type=Path)
    parser.add_argument("--backup", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)

    rows = load_project_rows(args.db)
    results = [apply_project(row, apply=args.apply) for row in rows]
    write_reports(results, args.reports, backup_dir=args.backup, graph_path=args.graph)
    print(json.dumps({"scanned": len(results), "modified": sum(1 for item in results if item.modified), "skipped": sum(1 for item in results if item.skipped)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
