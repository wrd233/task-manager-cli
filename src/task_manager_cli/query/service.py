from typing import Any, Dict, List, Optional

from task_manager_cli.core.errors import NotFoundError
from task_manager_cli.privacy.redactor import Redactor
from task_manager_cli.query.context_builder import ContextBuilder
from task_manager_cli.storage.repositories import Repository


class QueryService:
    def __init__(self, conn, sensitive_patterns=None):
        self.repo = Repository(conn)
        self.builder = ContextBuilder(self.repo, Redactor(sensitive_patterns or []))

    def list_objects(self, object_type: Optional[str] = None, status: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        return self.repo.list_objects(object_type=object_type, status=status, limit=limit)

    def show_object(self, ref: str) -> Dict[str, Any]:
        object_id = self.repo.resolve_object_id(ref)
        if object_id is None:
            raise NotFoundError(f"Object not found: {ref}")
        obj = self.repo.get_object(object_id)
        if obj is None:
            raise NotFoundError(f"Object not found: {ref}")
        return obj

    def object_context(self, ref: str, redact: bool = True, record_limit: int = 80) -> Dict[str, Any]:
        object_id = self.repo.resolve_object_id(ref)
        if object_id is None:
            raise NotFoundError(f"Object not found: {ref}")
        return self.builder.build_object_context(object_id, redact=redact, record_limit=record_limit)

    def agent_context(self, object_type: Optional[str] = None, limit: int = 20, redact: bool = True) -> Dict[str, Any]:
        return self.builder.build_agent_context(object_type=object_type, limit=limit, redact=redact)
