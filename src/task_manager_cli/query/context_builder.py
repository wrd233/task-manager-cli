from typing import Any, Dict, List

from task_manager_cli.privacy.redactor import Redactor


class ContextBuilder:
    def __init__(self, repo, redactor: Redactor):
        self.repo = repo
        self.redactor = redactor

    def build_object_context(self, object_id: int, redact: bool = True, record_limit: int = 80, include_annotations: bool = True) -> Dict[str, Any]:
        obj = self.repo.get_object(object_id)
        if not obj:
            raise KeyError(f"Object not found: {object_id}")
        records = []
        redacted_count = 0
        for record in self.repo.records_for_object(object_id, limit=record_limit):
            metadata = record.get("metadata", {})
            raw = record.get("raw_text", "")
            normalized = record.get("normalized_text", "")
            if redact:
                result = self.redactor.redact(raw, private=bool(metadata.get("private")))
                raw = result.text
                redacted_count += 1 if result.redacted else 0
                normalized_result = self.redactor.redact(normalized, private=bool(metadata.get("private")))
                normalized = normalized_result.text
                redacted_count += 1 if normalized_result.redacted else 0
            records.append({**record, "raw_text": raw, "normalized_text": normalized})
        obj = {**obj, **self.repo.object_activity(object_id)}
        return {
            "query": {"object_id": object_id, "record_limit": record_limit},
            "objects": [obj],
            "records": records,
            "relations": self.repo.relations_for_object(object_id),
            "annotations": self.repo.list_annotations(target_object_id=object_id, limit=50) if include_annotations else [],
            "truncation": {"record_limit": record_limit, "records_returned": len(records)},
            "redaction": {"enabled": redact, "records_redacted": redacted_count},
        }

    def build_agent_context(self, object_type: str = None, limit: int = 20, redact: bool = True, include_annotations: bool = True) -> Dict[str, Any]:
        objects = self.repo.list_objects(object_type=object_type, limit=limit)
        packages: List[Dict[str, Any]] = []
        for obj in objects:
            packages.append(self.build_object_context(int(obj["id"]), redact=redact, record_limit=20, include_annotations=include_annotations))
        return {
            "query": {"object_type": object_type, "limit": limit},
            "packages": packages,
            "redaction": {"enabled": redact},
            "truncation": {"object_limit": limit, "objects_returned": len(packages), "per_object_record_limit": 20},
        }
