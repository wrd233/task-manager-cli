from dataclasses import dataclass, field
from typing import Dict, List

from task_manager_cli.core.models import ActionObject, ObjectRecordLink, Relation, SourceRecord


@dataclass
class CandidateWarning:
    source_item_id: str
    message: str
    severity: str = "warning"
    metadata: Dict[str, str] = field(default_factory=dict)


@dataclass
class AdapterResult:
    objects: List[ActionObject] = field(default_factory=list)
    records: List[SourceRecord] = field(default_factory=list)
    links: List[ObjectRecordLink] = field(default_factory=list)
    relations: List[Relation] = field(default_factory=list)
    warnings: List[CandidateWarning] = field(default_factory=list)
    files_scanned: int = 0

    def stats(self) -> Dict[str, int]:
        return {
            "files_scanned": self.files_scanned,
            "records_seen": len(self.records),
            "objects_seen": len(self.objects),
            "warnings_seen": len(self.warnings),
        }
