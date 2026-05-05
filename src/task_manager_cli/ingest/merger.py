from dataclasses import dataclass
from typing import Dict

from task_manager_cli.adapters.base import AdapterResult
from task_manager_cli.storage.repositories import Repository


@dataclass
class IngestStats:
    records_seen: int = 0
    objects_seen: int = 0
    links_seen: int = 0
    relations_seen: int = 0
    warnings_seen: int = 0
    files_scanned: int = 0

    def as_dict(self) -> Dict[str, int]:
        return {
            "records_seen": self.records_seen,
            "objects_seen": self.objects_seen,
            "links_seen": self.links_seen,
            "relations_seen": self.relations_seen,
            "warnings_seen": self.warnings_seen,
            "files_scanned": self.files_scanned,
        }


class Merger:
    def __init__(self, repo: Repository):
        self.repo = repo

    def ingest(self, result: AdapterResult) -> IngestStats:
        stats = IngestStats(
            records_seen=len(result.records),
            objects_seen=len(result.objects),
            links_seen=len(result.links),
            relations_seen=len(result.relations),
            warnings_seen=len(result.warnings),
            files_scanned=result.files_scanned,
        )
        record_ids = {}
        object_ids = {}
        locations_by_source = {record.source_item_id: record.location for record in result.records}

        for record in result.records:
            record_ids[record.source_item_id] = self.repo.upsert_record(record)
        for obj in result.objects:
            location = locations_by_source.get(obj.source_item_id)
            if location is None:
                for record in result.records:
                    if record.source_item_id == obj.source_item_id:
                        location = record.location
                        break
            if location is None:
                continue
            object_ids[obj.source_item_id] = self.repo.upsert_object(obj, location)
        for link in result.links:
            obj_id = object_ids.get(link.object_source_item_id)
            rec_id = record_ids.get(link.record_source_item_id)
            if obj_id and rec_id:
                self.repo.link_object_record(obj_id, rec_id, link.role, link.metadata)
        for relation in result.relations:
            self.repo.upsert_relation_by_source(relation)
        return stats
