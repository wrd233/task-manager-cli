from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set

from task_manager_cli.adapters.base import AdapterResult, CandidateWarning
from task_manager_cli.adapters.logseq.extractors import (
    block_refs,
    content_hash,
    embeds,
    journal_date_from_path,
    normalize_text,
    page_name_from_path,
    page_refs,
    idea_marker,
    is_reference_record,
    project_confidence,
    role_for_child,
    semantic_marker,
    semantic_tags,
    suspicious_idea_reason,
)
from task_manager_cli.adapters.logseq.parser import LogseqBlock, ParsedLogseqFile, parse_logseq_file
from task_manager_cli.core.enums import ObjectType, RecordType, RelationType
from task_manager_cli.core.models import ActionObject, Location, ObjectRecordLink, Relation, SourceRecord


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class LogseqAdapter:
    source_type = "logseq"

    def __init__(self, graph_path: Path, ignored_embed_uuids: Optional[List[str]] = None):
        self.graph_path = Path(graph_path).expanduser()
        self.ignored_embed_uuids: Set[str] = set(ignored_embed_uuids or [])
        self._project_page_sources: Dict[str, str] = {}

    def scan(self, recent_journals: Optional[int] = None) -> AdapterResult:
        result = AdapterResult()
        for path in self._iter_markdown_files(recent_journals=recent_journals):
            page_name = page_name_from_path(path)
            parsed = parse_logseq_file(path, page_name)
            self._extract_file(parsed, result)
            result.files_scanned += 1
        return result

    def parse_file(self, path: Path) -> AdapterResult:
        parsed = parse_logseq_file(Path(path), page_name_from_path(Path(path)))
        result = AdapterResult(files_scanned=1)
        self._extract_file(parsed, result)
        return result

    def _iter_markdown_files(self, recent_journals: Optional[int] = None) -> Iterable[Path]:
        pages = self.graph_path / "pages"
        journals = self.graph_path / "journals"
        if pages.exists():
            yield from sorted(pages.rglob("*.md"))
        journal_paths = sorted(journals.rglob("*.md")) if journals.exists() else []
        if recent_journals:
            journal_paths = journal_paths[-recent_journals:]
        yield from journal_paths

    def _relative(self, path: Path) -> str:
        try:
            return str(path.relative_to(self.graph_path))
        except ValueError:
            return str(path)

    def _page_source_id(self, parsed: ParsedLogseqFile) -> str:
        return f"page:{self._relative(parsed.file_path)}"

    def _block_source_id(self, block: LogseqBlock) -> str:
        rel = self._relative(block.file_path)
        if block.uuid:
            return f"block:{block.uuid}"
        return f"block:{rel}:{block.line_number}:{content_hash(block.raw)}"

    def _location_for_page(self, parsed: ParsedLogseqFile) -> Location:
        source_id = self._page_source_id(parsed)
        return Location(
            source_type=self.source_type,
            source_item_id=source_id,
            graph_path=str(self.graph_path),
            file_path=str(parsed.file_path),
            page_name=parsed.page_name,
            journal_date=journal_date_from_path(parsed.file_path),
            line_start=1,
            line_end=max(1, len(parsed.blocks)),
            block_path=[parsed.page_name],
            metadata={"page_properties": parsed.page_properties},
        )

    def _location_for_block(self, block: LogseqBlock) -> Location:
        source_id = self._block_source_id(block)
        return Location(
            source_type=self.source_type,
            source_item_id=source_id,
            graph_path=str(self.graph_path),
            file_path=str(block.file_path),
            page_name=block.page_name,
            journal_date=journal_date_from_path(block.file_path),
            block_uuid=block.uuid,
            line_start=block.line_number,
            line_end=block.line_number,
            block_path=block.block_path(),
            metadata={"indent": block.indent},
        )

    def _record_for_page(self, parsed: ParsedLogseqFile) -> SourceRecord:
        text = parsed.all_text
        return SourceRecord(
            source_type=self.source_type,
            source_item_id=self._page_source_id(parsed),
            raw_text=text,
            normalized_text=normalize_text(text),
            record_type=RecordType.JOURNAL.value if journal_date_from_path(parsed.file_path) else RecordType.PAGE.value,
            location=self._location_for_page(parsed),
            source_created_at=self._file_time(parsed.file_path),
            source_updated_at=self._file_time(parsed.file_path),
            metadata={"page_properties": parsed.page_properties},
        )

    def _record_for_block(self, block: LogseqBlock) -> SourceRecord:
        metadata = {
            "properties": block.properties,
            "priority": block.priority,
            "block_refs": block.block_refs,
            "embeds": block.embeds,
            "page_refs": block.page_refs,
            "semantic_marker": semantic_marker(block.raw),
            "semantic_tags": semantic_tags(block.raw),
            "is_reference": is_reference_record(block.raw),
            "private": self._is_private(block),
        }
        task = block.task
        if task:
            metadata["task_status"] = task[0]
            if block.idea_title:
                metadata["idea_marker"] = True
                metadata["idea_marker_type"] = idea_marker(block.raw)
            suspicious = suspicious_idea_reason(block.raw)
            if suspicious:
                metadata["suspicious_idea_reason"] = suspicious
        return SourceRecord(
            source_type=self.source_type,
            source_item_id=self._block_source_id(block),
            raw_text=block.raw,
            normalized_text=block.normalized_text,
            record_type=RecordType.BLOCK.value,
            parent_source_item_id=self._block_source_id(block.parent) if block.parent else self._page_source_id_from_block(block),
            location=self._location_for_block(block),
            metadata=metadata,
        )

    def _page_source_id_from_block(self, block: LogseqBlock) -> str:
        return f"page:{self._relative(block.file_path)}"

    def _file_time(self, path: Path) -> Optional[str]:
        try:
            return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).replace(microsecond=0).isoformat()
        except OSError:
            return None

    def _extract_file(self, parsed: ParsedLogseqFile, result: AdapterResult) -> None:
        page_record = self._record_for_page(parsed)
        result.records.append(page_record)

        task_count = sum(1 for block in parsed.blocks if block.task and not block.is_pure_reference and not block.is_embed_reference)
        page_project_source_id: Optional[str] = None
        confidence_label, confidence, reasons = project_confidence(parsed.page_name, parsed.page_properties, parsed.all_text, task_count)
        if confidence_label and not journal_date_from_path(parsed.file_path):
            page_project_source_id = self._page_source_id(parsed)
            created_at = parsed.page_properties.get("start") or self._file_time(parsed.file_path)
            created_source = "page_property_start" if parsed.page_properties.get("start") else "file_stat"
            project = ActionObject(
                object_type=ObjectType.PROJECT.value,
                title=parsed.page_name,
                source_type=self.source_type,
                source_item_id=page_project_source_id,
                status=parsed.page_properties.get("state"),
                created_at=created_at,
                created_at_source=created_source,
                confidence=confidence,
                metadata={
                    "confidence_label": confidence_label,
                    "reasons": reasons,
                    "page_properties": parsed.page_properties,
                    "extraction_rule": "logseq_project_page",
                },
            )
            result.objects.append(project)
            result.links.append(ObjectRecordLink(page_project_source_id, page_record.source_item_id, "definition"))
            self._project_page_sources[parsed.page_name] = page_project_source_id

        for block in parsed.blocks:
            result.records.append(self._record_for_block(block))
            if block.is_embed_reference:
                for uuid in block.embeds:
                    if uuid in self.ignored_embed_uuids:
                        result.warnings.append(CandidateWarning(self._block_source_id(block), f"Ignored structural embed {uuid}", "info"))
                continue
            if block.is_pure_reference:
                self._extract_journal_exposure(block, parsed, result)
                continue

            self._extract_task(block, parsed, result, page_project_source_id)
            self._extract_idea(block, parsed, result, page_project_source_id)

    def _extract_task(self, block: LogseqBlock, parsed: ParsedLogseqFile, result: AdapterResult, page_project_source_id: Optional[str]) -> None:
        parsed_task = block.task
        if not parsed_task:
            return
        if is_reference_record(block.raw):
            return
        status, title = parsed_task
        source_id = self._block_source_id(block)
        journal_date = journal_date_from_path(parsed.file_path)
        task = ActionObject(
            object_type=ObjectType.TASK.value,
            title=title,
            source_type=self.source_type,
            source_item_id=source_id,
            status=status.lower(),
            created_at=journal_date,
            created_at_source="journal_date" if journal_date else "first_seen_at",
            confidence=0.98,
            metadata={
                "priority": block.priority,
                "page_name": parsed.page_name,
                "section_markers": block.section_markers(),
                "block_refs": block.block_refs,
                "embeds": block.embeds,
                "page_refs": block.page_refs,
                "extraction_rule": "logseq_task_marker",
            },
        )
        result.objects.append(task)
        result.links.append(ObjectRecordLink(source_id, source_id, "definition"))
        for child in block.descendants():
            if child.properties.get("__property_block__") == "true":
                continue
            result.links.append(ObjectRecordLink(source_id, self._block_source_id(child), role_for_child(child.raw)))
        if page_project_source_id:
            result.relations.append(Relation(source_id, page_project_source_id, RelationType.BELONGS_TO.value, 0.9, {"rule": "same_project_page"}))
        else:
            self._add_page_ref_project_relations(block, source_id, result, confidence=0.75, rule="journal_page_ref")

    def _extract_idea(self, block: LogseqBlock, parsed: ParsedLogseqFile, result: AdapterResult, page_project_source_id: Optional[str]) -> None:
        title = block.idea_title
        if not title:
            return
        if is_reference_record(block.raw):
            return
        source_id = self._block_source_id(block)
        journal_date = journal_date_from_path(parsed.file_path)
        idea = ActionObject(
            object_type=ObjectType.IDEA.value,
            title=title,
            source_type=self.source_type,
            source_item_id=source_id,
            status="captured",
            created_at=journal_date,
            created_at_source="journal_date" if journal_date else "first_seen_at",
            confidence=0.9,
            metadata={
                "page_name": parsed.page_name,
                "section_markers": block.section_markers(),
                "idea_marker": idea_marker(block.raw),
                "original_raw_text": block.raw,
                "normalized_title": title,
                "page_refs": block.page_refs,
                "extraction_rule": "logseq_idea_marker",
            },
        )
        result.objects.append(idea)
        result.links.append(ObjectRecordLink(source_id, source_id, "definition"))
        for child in block.descendants():
            if child.properties.get("__property_block__") == "true":
                continue
            result.links.append(ObjectRecordLink(source_id, self._block_source_id(child), role_for_child(child.raw)))

        parent_task = self._nearest_task_ancestor(block)
        if parent_task:
            result.relations.append(Relation(source_id, self._block_source_id(parent_task), RelationType.BELONGS_TO.value, 0.95, {"rule": "idea_under_task"}))
        elif page_project_source_id and any("头脑风暴" in marker for marker in block.section_markers()):
            result.relations.append(Relation(source_id, page_project_source_id, RelationType.BELONGS_TO.value, 0.85, {"rule": "idea_under_brainstorm"}))
        elif page_project_source_id:
            result.relations.append(Relation(source_id, page_project_source_id, RelationType.BELONGS_TO.value, 0.65, {"rule": "same_project_page"}))
        else:
            self._add_page_ref_project_relations(block, source_id, result, confidence=0.75, rule="journal_page_ref")

    def _add_page_ref_project_relations(self, block: LogseqBlock, source_id: str, result: AdapterResult, confidence: float, rule: str) -> None:
        for ref in block.page_refs:
            project_source_id = self._project_page_sources.get(ref)
            if project_source_id:
                result.relations.append(Relation(source_id, project_source_id, RelationType.BELONGS_TO.value, confidence, {"rule": rule, "page_ref": ref}))

    def _extract_journal_exposure(self, block: LogseqBlock, parsed: ParsedLogseqFile, result: AdapterResult) -> None:
        if not journal_date_from_path(parsed.file_path):
            return
        for ref in block.block_refs:
            result.links.append(
                ObjectRecordLink(
                    object_source_item_id=f"block:{ref}",
                    record_source_item_id=self._block_source_id(block),
                    role="journal_exposure",
                    metadata={"journal_date": journal_date_from_path(parsed.file_path), "rule": "pure_block_reference"},
                )
            )

    def _nearest_task_ancestor(self, block: LogseqBlock) -> Optional[LogseqBlock]:
        for ancestor in reversed(block.ancestors()):
            if ancestor.task and not ancestor.is_pure_reference and not ancestor.is_embed_reference:
                return ancestor
        return None

    def _is_private(self, block: LogseqBlock) -> bool:
        text = block.raw.lower()
        return block.properties.get("private", "").lower() == "true" or "private:: true" in text or "**[敏感]**" in block.raw or "[敏感]" in block.raw
