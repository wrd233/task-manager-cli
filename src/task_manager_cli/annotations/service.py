from typing import Any, Dict, List, Optional

from task_manager_cli.core.enums import AnnotationStatus
from task_manager_cli.core.errors import NotFoundError
from task_manager_cli.storage.repositories import Repository


class AnnotationService:
    def __init__(self, conn):
        self.repo = Repository(conn)

    def add(self, target_object_ref: Optional[str], content: str, author: str = "agent", annotation_type: str = "comment", target_record_ref: Optional[str] = None) -> int:
        object_id = None
        record_id = None
        if target_object_ref:
            object_id = self.repo.resolve_object_id(target_object_ref)
            if object_id is None:
                raise NotFoundError(f"Target object not found: {target_object_ref}")
        if target_record_ref:
            record_id = self.repo.resolve_record_id(target_record_ref)
            if record_id is None:
                raise NotFoundError(f"Target record not found: {target_record_ref}")
        if object_id is None and record_id is None:
            raise ValueError("Annotation requires an object or record target.")
        return self.repo.add_annotation(object_id, record_id, author, annotation_type, content)

    def list(self, target_object_ref: Optional[str] = None, status: Optional[str] = None, limit: int = 50, target_record_ref: Optional[str] = None) -> List[Dict[str, Any]]:
        object_id = None
        record_id = None
        if target_object_ref:
            object_id = self.repo.resolve_object_id(target_object_ref)
            if object_id is None:
                raise NotFoundError(f"Target object not found: {target_object_ref}")
        if target_record_ref:
            record_id = self.repo.resolve_record_id(target_record_ref)
            if record_id is None:
                raise NotFoundError(f"Target record not found: {target_record_ref}")
        return self.repo.list_annotations(target_object_id=object_id, target_record_id=record_id, status=status, limit=limit)

    def update_status(self, annotation_id: int, status: str) -> bool:
        if status not in {item.value for item in AnnotationStatus}:
            raise ValueError(f"Unsupported annotation status: {status}")
        ok = self.repo.update_annotation_status(annotation_id, status)
        if not ok:
            raise NotFoundError(f"Annotation not found: {annotation_id}")
        return ok
