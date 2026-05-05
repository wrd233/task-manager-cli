from typing import Any, Dict, List, Optional

from task_manager_cli.core.enums import ObjectType, ProposalType, RelationType
from task_manager_cli.core.errors import NotFoundError, TaskManagerError
from task_manager_cli.proposals.service import ProposalService
from task_manager_cli.storage.repositories import Repository


MEMBERSHIP_PROPOSAL_TYPES = {
    ProposalType.LINK_TO_PROJECT.value,
    ProposalType.LINK_TO_PROJECT_NODE.value,
    ProposalType.LINK_IDEA_TO_PROJECT.value,
    ProposalType.LINK_RESOURCE_TO_PROJECT.value,
    ProposalType.ATTACH_TO_MINI_PROJECT.value,
}


class ProjectMembershipService:
    def __init__(self, conn, proposal_service: Optional[ProposalService] = None):
        self.conn = conn
        self.repo = Repository(conn)
        self.proposals = proposal_service or ProposalService(conn)

    def propose(
        self,
        object_ref: str,
        project_ref: str,
        project_node_id: Optional[str] = None,
        proposal_type: Optional[str] = None,
        confidence: Optional[float] = None,
        reason: Optional[str] = None,
        source: str = "rule",
    ) -> int:
        obj, project = self._resolve_pair(object_ref, project_ref)
        ptype = proposal_type or self._proposal_type_for(obj, project_node_id)
        if ptype not in MEMBERSHIP_PROPOSAL_TYPES and ptype != ProposalType.PROMOTE_TO_MINI_PROJECT.value:
            raise TaskManagerError(f"Unsupported project membership proposal type: {ptype}")
        if obj.get("object_type") == ObjectType.REFERENCE.value and ptype not in {ProposalType.LINK_RESOURCE_TO_PROJECT.value, ProposalType.LINK_TO_PROJECT_NODE.value}:
            raise TaskManagerError("Reference objects cannot be proposed as action items.")
        evidence = self.evidence(obj, project, project_node_id=project_node_id)
        proposal_confidence = confidence if confidence is not None else evidence["confidence"]
        payload = {
            "relation_type": RelationType.BELONGS_TO.value,
            "target_project_id": project["id"],
            "target_project_title": project["title"],
            "target_project_node_id": project_node_id,
            "confidence": proposal_confidence,
            "source_evidence": evidence["reasons"],
            "writeback_suggested": False,
        }
        return self.proposals.create(
            ptype,
            f"Link {obj['title']} to project {project['title']}",
            payload,
            risk="low",
            target_object_ref=str(obj["id"]),
            source=source,
            rationale=reason or "; ".join(evidence["reasons"]) or "Project membership proposal.",
            metadata={
                "project_membership": True,
                "target_project_id": project["id"],
                "target_project_node_id": project_node_id,
                "confidence": proposal_confidence,
            },
        )

    def propose_promote_to_mini_project(self, object_ref: str, reason: Optional[str] = None, source: str = "rule") -> int:
        object_id = self.repo.resolve_object_id(object_ref)
        if object_id is None:
            raise NotFoundError(f"Object not found: {object_ref}")
        obj = self.repo.get_object(object_id)
        if not obj:
            raise NotFoundError(f"Object not found: {object_ref}")
        payload = {
            "source_object_id": obj["id"],
            "source_object_title": obj["title"],
            "suggested_mini_project_title": obj["title"],
            "writeback_suggested": False,
        }
        return self.proposals.create(
            ProposalType.PROMOTE_TO_MINI_PROJECT.value,
            f"Promote to mini project: {obj['title']}",
            payload,
            risk="medium",
            target_object_ref=str(obj["id"]),
            source=source,
            rationale=reason or "This item may require multiple action items but is not necessarily a formal project.",
            metadata={"mini_project": True, "confidence": 0.65},
        )

    def evidence(self, obj: Dict[str, Any], project: Dict[str, Any], project_node_id: Optional[str] = None) -> Dict[str, Any]:
        reasons: List[str] = []
        confidence = 0.4
        project_title = project["title"]
        obj_metadata = obj.get("metadata", {}) or {}
        page_refs = set(obj_metadata.get("page_refs") or [])
        page_name = obj.get("page_name")
        if page_name == project_title:
            reasons.append("object_on_project_page")
            confidence = max(confidence, 0.92)
        if project_title in page_refs:
            reasons.append("explicit_project_page_ref")
            confidence = max(confidence, 0.82)
        if project_title in obj.get("title", ""):
            reasons.append("project_keyword_in_title")
            confidence = max(confidence, 0.62)
        if project_node_id:
            reasons.append("target_project_node_selected")
            confidence = max(confidence, 0.75)
        if not reasons:
            reasons.append("manual_membership_review")
        return {"confidence": confidence, "reasons": reasons}

    def _resolve_pair(self, object_ref: str, project_ref: str) -> tuple:
        object_id = self.repo.resolve_object_id(object_ref)
        project_id = self.repo.resolve_object_id(project_ref)
        if object_id is None:
            raise NotFoundError(f"Object not found: {object_ref}")
        if project_id is None:
            raise NotFoundError(f"Project not found: {project_ref}")
        obj = self.repo.get_object(object_id)
        project = self.repo.get_object(project_id)
        if not obj or not project:
            raise NotFoundError("Object or project not found.")
        if project.get("object_type") != ObjectType.PROJECT.value:
            raise TaskManagerError(f"Target is not a project: {project_ref}")
        return obj, project

    def _proposal_type_for(self, obj: Dict[str, Any], project_node_id: Optional[str]) -> str:
        if project_node_id:
            return ProposalType.LINK_TO_PROJECT_NODE.value
        if obj.get("object_type") == ObjectType.IDEA.value:
            return ProposalType.LINK_IDEA_TO_PROJECT.value
        if obj.get("object_type") in {ObjectType.REFERENCE.value, ObjectType.RESOURCE.value}:
            return ProposalType.LINK_RESOURCE_TO_PROJECT.value
        return ProposalType.LINK_TO_PROJECT.value

