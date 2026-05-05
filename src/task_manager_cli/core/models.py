from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


JsonDict = Dict[str, Any]


@dataclass
class Location:
    source_type: str
    source_item_id: str
    graph_path: Optional[str] = None
    file_path: Optional[str] = None
    page_name: Optional[str] = None
    journal_date: Optional[str] = None
    block_uuid: Optional[str] = None
    line_start: Optional[int] = None
    line_end: Optional[int] = None
    block_path: List[str] = field(default_factory=list)
    external_url: Optional[str] = None
    metadata: JsonDict = field(default_factory=dict)


@dataclass
class SourceRecord:
    source_type: str
    source_item_id: str
    raw_text: str
    normalized_text: str
    record_type: str
    location: Location
    parent_source_item_id: Optional[str] = None
    source_created_at: Optional[str] = None
    source_updated_at: Optional[str] = None
    metadata: JsonDict = field(default_factory=dict)


@dataclass
class ActionObject:
    object_type: str
    title: str
    source_type: str
    source_item_id: str
    status: Optional[str] = None
    created_at: Optional[str] = None
    created_at_source: str = "first_seen_at"
    confidence: float = 1.0
    metadata: JsonDict = field(default_factory=dict)


@dataclass
class ObjectRecordLink:
    object_source_item_id: str
    record_source_item_id: str
    role: str
    metadata: JsonDict = field(default_factory=dict)


@dataclass
class Relation:
    from_source_item_id: str
    to_source_item_id: str
    relation_type: str
    confidence: float = 1.0
    metadata: JsonDict = field(default_factory=dict)


@dataclass
class Annotation:
    target_object_id: Optional[str]
    target_record_id: Optional[str]
    author: str
    annotation_type: str
    content: str
    status: str = "open"
    metadata: JsonDict = field(default_factory=dict)


@dataclass
class Proposal:
    proposal_type: str
    title: str
    payload: JsonDict
    risk: str
    status: str = "suggested"
    target_object_id: Optional[int] = None
    target_record_id: Optional[int] = None
    review_session_id: Optional[int] = None
    source: str = "agent"
    rationale: Optional[str] = None
    metadata: JsonDict = field(default_factory=dict)


@dataclass
class ReviewSession:
    review_type: str
    status: str = "open"
    title: Optional[str] = None
    scope: JsonDict = field(default_factory=dict)
    metadata: JsonDict = field(default_factory=dict)


@dataclass
class ContextPackage:
    query: JsonDict
    objects: List[JsonDict]
    records: List[JsonDict]
    relations: List[JsonDict]
    annotations: List[JsonDict]
    truncation: JsonDict
    redaction: JsonDict
