from enum import Enum


class ObjectType(str, Enum):
    PROJECT = "project"
    TASK = "task"
    ACTION_ITEM = "action_item"
    IDEA = "idea"
    REFERENCE = "reference"
    RESOURCE = "resource"
    MINI_PROJECT = "mini_project"


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


class ProposalType(str, Enum):
    STATUS_CHANGE = "status_change"
    RELATION_CHANGE = "relation_change"
    ANNOTATION = "annotation"
    NEEDS_CLARIFICATION = "needs_clarification"
    LOGSEQ_APPEND_MARKER = "logseq_append_marker"
    LOGSEQ_TASK_MARKER = "logseq_task_marker"
    CREATE_MINI_PROJECT = "create_mini_project"
    RESULT_MARKER = "result_marker"
    CREATE_PROJECT_NODE = "create_project_node"
    DELETE = "delete"
    MERGE = "merge"
    BULK_LOGSEQ_WRITEBACK = "bulk_logseq_writeback"
    REWRITE_TITLE = "rewrite_title"
    PROJECT_TREE_REWRITE = "project_tree_rewrite"


class ProposalStatus(str, Enum):
    SUGGESTED = "suggested"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EDITED = "edited"
    APPLIED = "applied"
    ROLLED_BACK = "rolled_back"
    SUPERSEDED = "superseded"
    EXPIRED = "expired"


class ProposalRisk(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ReviewStatus(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
