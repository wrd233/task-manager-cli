from dataclasses import dataclass, field
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from task_manager_cli.adapters.logseq.extractors import (
    block_refs,
    embeds,
    has_project_marker,
    is_embed_reference,
    is_pure_reference,
    normalize_text,
    page_refs,
    parse_idea,
    parse_priority,
    parse_task,
    strip_bullet,
)


PROPERTY_RE = re.compile(r"^([\w\u4e00-\u9fff-]+)::\s*(.*)$")


@dataclass
class LogseqBlock:
    raw: str
    line_number: int
    indent: int
    file_path: Path
    page_name: str
    children: List["LogseqBlock"] = field(default_factory=list)
    parent: Optional["LogseqBlock"] = None
    properties: Dict[str, str] = field(default_factory=dict)

    @property
    def text(self) -> str:
        return strip_bullet(self.raw)

    @property
    def normalized_text(self) -> str:
        return normalize_text(self.text)

    @property
    def task(self):
        return parse_task(self.raw)

    @property
    def idea_title(self) -> Optional[str]:
        return parse_idea(self.raw)

    @property
    def priority(self) -> Optional[str]:
        return parse_priority(self.raw)

    @property
    def uuid(self) -> Optional[str]:
        return self.properties.get("id")

    @property
    def is_pure_reference(self) -> bool:
        return is_pure_reference(self.raw)

    @property
    def is_embed_reference(self) -> bool:
        return is_embed_reference(self.raw)

    @property
    def block_refs(self) -> List[str]:
        return block_refs(self.raw)

    @property
    def embeds(self) -> List[str]:
        return embeds(self.raw)

    @property
    def page_refs(self) -> List[str]:
        return page_refs(self.raw)

    @property
    def is_project_marker(self) -> bool:
        return has_project_marker(self.raw)

    def add_child(self, child: "LogseqBlock") -> None:
        child.parent = self
        self.children.append(child)

    def ancestors(self) -> List["LogseqBlock"]:
        items = []
        cur = self.parent
        while cur:
            items.append(cur)
            cur = cur.parent
        return list(reversed(items))

    def descendants(self) -> List["LogseqBlock"]:
        items: List[LogseqBlock] = []
        stack = list(self.children)
        while stack:
            item = stack.pop(0)
            items.append(item)
            stack[0:0] = item.children
        return items

    def block_path(self) -> List[str]:
        return [b.normalized_text for b in self.ancestors()] + [self.normalized_text]

    def section_markers(self) -> List[str]:
        markers = []
        for ancestor in self.ancestors():
            if ancestor.is_project_marker:
                markers.append(ancestor.normalized_text)
        return markers


@dataclass
class ParsedLogseqFile:
    file_path: Path
    page_name: str
    page_properties: Dict[str, str]
    blocks: List[LogseqBlock]
    content_start_line: int

    @property
    def all_text(self) -> str:
        return "\n".join(block.raw for block in self.blocks)


def indent_level(line: str) -> int:
    leading_ws = line[: len(line) - len(line.lstrip(" \t"))]
    tabs = leading_ws.count("\t")
    spaces = leading_ws.count(" ")
    return tabs + spaces // 4


def parse_page_properties(lines: List[str]) -> Tuple[Dict[str, str], int]:
    props: Dict[str, str] = {}
    content_start = 0
    in_frontmatter = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped == "---" and not in_frontmatter:
            in_frontmatter = True
            continue
        if stripped == "---" and in_frontmatter:
            content_start = i + 1
            break
        match = PROPERTY_RE.match(stripped)
        if match:
            props[match.group(1)] = match.group(2).strip()
            content_start = i + 1
            continue
        break
    return props, content_start


def parse_logseq_file(path: Path, page_name: Optional[str] = None) -> ParsedLogseqFile:
    path = Path(path)
    lines = path.read_text(encoding="utf-8").splitlines()
    props, start = parse_page_properties(lines)
    blocks: List[LogseqBlock] = []
    stack: List[LogseqBlock] = []
    in_code = False
    current_page = page_name or path.stem.replace("%2F", "/")

    for index, line in enumerate(lines[start:], start + 1):
        stripped = line.strip()
        bullet_text = re.sub(r"^\s*-\s*", "", line).strip()
        if bullet_text.startswith("```"):
            in_code = not in_code
            continue
        if in_code or not stripped:
            continue
        if not re.match(r"^\s*-", line):
            prop_match = PROPERTY_RE.match(stripped)
            if prop_match and stack:
                ind = indent_level(line)
                parent = next((candidate for candidate in reversed(stack) if candidate.indent < ind), stack[-1])
                parent.properties[prop_match.group(1)] = prop_match.group(2).strip()
            continue
        block = LogseqBlock(raw=line, line_number=index, indent=indent_level(line), file_path=path, page_name=current_page)
        while stack and stack[-1].indent >= block.indent:
            stack.pop()
        if stack:
            stack[-1].add_child(block)
        blocks.append(block)
        stack.append(block)

    attach_block_properties(blocks)
    return ParsedLogseqFile(path, current_page, props, blocks, start + 1)


def attach_block_properties(blocks: Iterable[LogseqBlock]) -> None:
    property_blocks = set()
    for block in blocks:
        for child in block.children:
            match = PROPERTY_RE.match(child.text)
            if match:
                block.properties[match.group(1)] = match.group(2).strip()
                property_blocks.add(id(child))
    for block in blocks:
        if id(block) in property_blocks:
            block.properties["__property_block__"] = "true"
