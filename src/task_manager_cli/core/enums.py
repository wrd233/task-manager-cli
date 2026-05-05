from enum import Enum


class ObjectType(str, Enum):
    PROJECT = "project"
    TASK = "task"
    IDEA = "idea"


class RecordType(str, Enum):
    PAGE = "page"
    JOURNAL = "journal"
    BLOCK = "block"
    MEMO = "memo"


class RelationType(str, Enum):
    BELONGS_TO = "belongs_to"
    REFERENCES = "references"
    RELATED_TO = "related_to"
    DERIVED_FROM = "derived_from"


class AnnotationStatus(str, Enum):
    OPEN = "open"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    ARCHIVED = "archived"
