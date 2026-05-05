import hashlib
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


PROJECT_MARKERS = [
    "[具体目标]",
    "[具体事务]",
    "[资源列表]",
    "[头脑风暴]",
    "[反思]",
    "[价值层]",
    "[目标层]",
    "[里程碑]",
    "[阶段]",
    "[子阶段]",
    "[待澄清]",
]

PROJECT_PREFIXES = ("项目-", "任务-", "学习-", "课程-", "阶段-")
TASK_RE = re.compile(r"^\s*-\s*(TODO|DOING|DONE)\b\s*(.*)$")
PRIORITY_RE = re.compile(r"\[#([ABC])\]")
IDEA_RE = re.compile(r"(?:\*\*)?\[(想法|随想)\](?:\*\*)?\s*(.*)")
BLOCK_REF_RE = re.compile(r"\(\(([0-9a-fA-F-]{8,})\)\)")
EMBED_RE = re.compile(r"\{\{embed\s+\(\(([0-9a-fA-F-]{8,})\)\)\}\}")
PAGE_REF_RE = re.compile(r"\[\[([^\]]+)\]\]")
SCHEDULED_RE = re.compile(r"SCHEDULED:\s*<([^>]+)>")
DEADLINE_RE = re.compile(r"DEADLINE:\s*<([^>]+)>")
CLOCK_RE = re.compile(r"CLOCK:\s*(.+)$")


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def content_hash(*parts: str) -> str:
    h = hashlib.sha1()
    for part in parts:
        h.update(part.encode("utf-8", "ignore"))
        h.update(b"\0")
    return h.hexdigest()[:16]


def page_name_from_path(path: Path) -> str:
    return path.stem.replace("%2F", "/")


def journal_date_from_path(path: Path) -> Optional[str]:
    stem = path.stem
    if re.match(r"^\d{4}_\d{2}_\d{2}$", stem):
        return stem.replace("_", "-")
    return None


def strip_bullet(raw: str) -> str:
    return re.sub(r"^\s*-\s*", "", raw.rstrip("\n")).strip()


def parse_task(raw: str) -> Optional[Tuple[str, str]]:
    match = TASK_RE.match(raw)
    if not match:
        return None
    return match.group(1), normalize_task_title(match.group(2))


def normalize_task_title(text: str) -> str:
    text = PRIORITY_RE.sub("", text)
    text = SCHEDULED_RE.sub("", text)
    text = DEADLINE_RE.sub("", text)
    return normalize_text(text.replace("**", ""))


def parse_priority(text: str) -> Optional[str]:
    match = PRIORITY_RE.search(text)
    return match.group(1) if match else None


def parse_idea(raw: str) -> Optional[str]:
    text = strip_bullet(raw)
    match = IDEA_RE.search(text)
    if not match:
        return None
    title = match.group(2).strip() or text
    return normalize_text(title.replace("**", ""))


def block_refs(text: str) -> List[str]:
    return BLOCK_REF_RE.findall(text)


def embeds(text: str) -> List[str]:
    return EMBED_RE.findall(text)


def page_refs(text: str) -> List[str]:
    return PAGE_REF_RE.findall(text)


def is_pure_reference(raw: str) -> bool:
    return bool(re.match(r"^\s*-\s*\(\([0-9a-fA-F-]{8,}\)\)\s*$", raw))


def is_embed_reference(raw: str) -> bool:
    return bool(re.match(r"^\s*-\s*\{\{embed\s+\(\([0-9a-fA-F-]{8,}\)\)\}\}\s*$", raw))


def has_project_marker(text: str) -> bool:
    return any(marker in text for marker in PROJECT_MARKERS)


def project_confidence(page_name: str, page_props: Dict[str, str], all_text: str, task_count: int) -> Tuple[Optional[str], float, List[str]]:
    para = "PARA/Project" in page_props.get("PARA", "") or "PARA/Project" in page_props.get("para", "")
    markers = [marker for marker in PROJECT_MARKERS if marker in all_text]
    prefix = page_name.startswith(PROJECT_PREFIXES)
    reasons: List[str] = []
    if para:
        reasons.append("para_project")
    if markers:
        reasons.append("project_structure_markers")
    if prefix:
        reasons.append("project_like_prefix")
    if para and markers:
        return "high", 0.95, reasons
    if para or markers:
        return "medium", 0.75, reasons
    if prefix and (task_count > 0 or markers):
        return "low", 0.5, reasons
    return None, 0.0, reasons


def role_for_child(text: str) -> str:
    stripped = strip_bullet(text)
    if "[想法]" in stripped or "[随想]" in stripped:
        return "idea_note"
    if "[反思]" in stripped:
        return "reflection"
    if "[问题]" in stripped:
        return "question"
    if "[部署]" in stripped:
        return "process_note"
    if "[注]" in stripped:
        return "process_note"
    if stripped.startswith("CLOCK:") or stripped == ":LOGBOOK:":
        return "process_note"
    if "http://" in stripped or "https://" in stripped:
        return "resource"
    return "child_record"
