import json
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

from task_manager_cli.adapters.logseq.adapter import LogseqAdapter
from task_manager_cli.adapters.logseq.extractors import semantic_marker_content
from task_manager_cli.config.settings import Settings
from task_manager_cli.core.enums import ObjectType, ProposalType, RelationType
from task_manager_cli.core.errors import ConfigError, NotFoundError, TaskManagerError
from task_manager_cli.core.models import ActionObject, Location
from task_manager_cli.ingest.merger import Merger
from task_manager_cli.projects.tree import LABEL_BY_NODE_TYPE, ProjectTreeService
from task_manager_cli.proposals.service import ProposalService
from task_manager_cli.providers.base import ProviderResult, provider_from_settings
from task_manager_cli.storage.repositories import Repository
from task_manager_cli.writes.logseq_writer import LogseqWriter, WritePreview


PROJECT_SECTIONS = {
    "todo": "项目收件箱",
    "idea": "想法",
    "resource": "资源",
    "result": "成果",
    "note": "反思",
    "mini": "小任务",
}

ALLOWED_OPERATIONS = [
    "create_project",
    "capture_project_item",
    "clarify_unplaced",
    "create_project_node",
    "link_object_to_node",
    "append_block_ref_to_node",
    "promote_to_mini_project",
    "mark_object_as_result",
]
FORBIDDEN_OPERATIONS = ["move_original_block", "delete_block", "merge_blocks", "mass_reorder"]
PROPOSAL_REQUIRED_OPERATIONS = [
    "create_project_node",
    "link_object_to_node",
    "append_block_ref_to_node",
    "promote_to_mini_project",
    "convert_idea_to_task",
    "archive_project_item",
]


class ProjectLifecycleService:
    def __init__(self, conn, settings: Settings):
        self.conn = conn
        self.settings = settings
        self.repo = Repository(conn)
        if not settings.logseq_graph_path:
            raise ConfigError("Logseq graph path is not configured.")
        self.graph_path = Path(settings.logseq_graph_path)
        self.writer = LogseqWriter(self.graph_path)
        self.tree_service = ProjectTreeService(conn, settings)
        self.proposals = ProposalService(conn, settings)

    def create_project(
        self,
        name: str,
        *,
        template: str = "standard",
        goal: Optional[str] = None,
        preview: bool = False,
    ) -> Dict[str, Any]:
        if template not in {"minimal", "standard"}:
            raise ValueError("Project template must be minimal or standard.")
        page_name = name.strip()
        if not page_name:
            raise ValueError("Project name is required.")
        content = project_template(template, goal=goal)
        write_preview = self.writer.preview_create_page(page_name, content)
        if preview:
            return {"project": page_name, "preview_diff": write_preview.diff, "file_path": str(write_preview.file_path)}
        backup = self.writer.apply(write_preview, write_preview.original_sha256, self.settings.write_backup_dir or self.settings.app_dir / "backups")
        self._ingest_file(write_preview.file_path)
        project_id = self._ensure_project_object(page_name, write_preview.file_path, template, goal)
        return {
            "project": page_name,
            "project_id": project_id,
            "file_path": str(write_preview.file_path),
            "backup_path": str(backup) if str(backup) else None,
            "created_file": True,
        }

    def project_inbox(self, project_ref: str) -> List[Dict[str, Any]]:
        return [item for item in self.project_items(project_ref) if self._is_inbox_item(item)]

    def unplaced(self, project_ref: str) -> List[Dict[str, Any]]:
        return [item for item in self.project_items(project_ref) if self._is_unplaced(item)]

    def project_items(self, project_ref: str) -> List[Dict[str, Any]]:
        project = self._project(project_ref)
        project_id = int(project["id"])
        project_file = project.get("file_path")
        items: Dict[int, Dict[str, Any]] = {}
        for object_type in ("task", "idea", "mini_project", "reference", "resource"):
            for obj in self.repo.list_objects(object_type, limit=100000):
                belongs = False
                placement_status = None
                project_node_id = None
                for rel in self.repo.relations_for_object(int(obj["id"])):
                    meta = rel.get("metadata") or {}
                    if rel.get("relation_type") == RelationType.BELONGS_TO.value and str(rel.get("to_id")) == str(project_id):
                        belongs = True
                        placement_status = placement_status or meta.get("placement_status")
                        project_node_id = project_node_id or meta.get("target_project_node_id")
                if project_file and obj.get("file_path") == project_file:
                    belongs = True
                if belongs:
                    copy = dict(obj)
                    copy["belongs_to_project"] = True
                    copy["project_id"] = project_id
                    copy["project_title"] = project["title"]
                    copy["belongs_to_node"] = bool(project_node_id)
                    copy["project_node_id"] = project_node_id
                    copy["placement_status"] = placement_status or self._placement_from_location(project, copy)
                    items[int(obj["id"])] = copy
        return list(items.values())

    def clarify_project(self, project_ref: str, *, target: str = "unplaced", mode: str = "quick", provider_name: str = "mock") -> Dict[str, Any]:
        project = self._project(project_ref)
        candidates = self.unplaced(project_ref) if target == "unplaced" else self.project_inbox(project_ref)
        proposal_ids: List[int] = []
        questions: List[Dict[str, Any]] = []
        if provider_name == "mock":
            for obj in candidates:
                proposal_ids.extend(self._default_clarify_proposals(project, obj))
        else:
            provider = provider_from_settings(self.settings, override_name=provider_name)
            payload = {
                "project": {"id": project["id"], "title": project["title"]},
                "target": target,
                "mode": mode,
                "items": [self._pack_object(item) for item in candidates],
                "constraints": self.constraints(),
            }
            result = provider.generate(payload)
            questions = result.questions_for_user
            proposal_ids.extend(self._provider_result_to_project_proposals(project, result))
        return {
            "project": project["title"],
            "target": target,
            "mode": mode,
            "candidate_count": len(candidates),
            "questions_for_user": questions,
            "proposal_ids": proposal_ids,
            "proposals": [self.proposals.get(pid) for pid in proposal_ids],
        }

    def project_pack(self, project_ref: str) -> Dict[str, Any]:
        project = self._project(project_ref)
        return {
            "view": "agent-project-pack",
            "project": self._pack_project(project),
            "semantic_tree": self.tree_service.agent_view(str(project["id"]), detail=False),
            "project_inbox": [self._pack_object(item) for item in self.project_inbox(str(project["id"]))],
            "unplaced_objects": [self._pack_object(item) for item in self.unplaced(str(project["id"]))],
            "tasks": [self._pack_object(item) for item in self.project_items(str(project["id"])) if item["object_type"] == "task"],
            "ideas": [self._pack_object(item) for item in self.project_items(str(project["id"])) if item["object_type"] == "idea"],
            "resources": [self._pack_object(item) for item in self.project_items(str(project["id"])) if item["object_type"] in {"reference", "resource"}],
            "results": self.result_records(str(project["id"])),
            "mini_projects": [self._pack_object(item) for item in self.project_items(str(project["id"])) if item["object_type"] == "mini_project"],
            "recent_records": self._recent_project_records(project, limit=12),
            "project_health": self.project_health(str(project["id"])),
            "constraints": self.constraints(),
            "available_operations": ALLOWED_OPERATIONS,
        }

    def restructure_pack(self, project_ref: str) -> Dict[str, Any]:
        project = self._project(project_ref)
        tree = self.tree_service.agent_view(str(project["id"]), detail=False)
        flat: List[Dict[str, Any]] = []
        self.tree_service._flatten(tree.get("tree", []), flat)
        return {
            "view": "agent-project-restructure-pack",
            "project": self._pack_project(project),
            "semantic_tree": tree,
            "unplaced_objects": [self._pack_object(item) for item in self.unplaced(str(project["id"]))],
            "project_health": self.project_health(str(project["id"])),
            "node_summaries": [
                {
                    "node_id": node["id"],
                    "type": node["node_type"],
                    "title": node["title"],
                    "raw_evidence_command": f"tm agent project-node {node['id']} --project \"{project['title']}\"",
                }
                for node in flat
            ],
            "raw_evidence_references": ["Use tm agent project-node <node-id> --project <project> for raw subtree evidence."],
            "proposal_schema": agent_output_schema(),
            "allowed_proposal_types": [
                "create_project_node",
                "link_object_to_node",
                "append_block_ref_to_node",
                "promote_to_mini_project",
                "convert_idea_to_task",
                "mark_object_as_result",
            ],
            "forbidden_operations": FORBIDDEN_OPERATIONS,
            "expected_output_schema": agent_output_schema(),
        }

    def proposals_from_agent_output(self, project_ref: str, file_path: Path) -> Dict[str, Any]:
        project = self._project(project_ref)
        try:
            data = json.loads(Path(file_path).read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError("Agent output must be valid JSON.") from exc
        validate_agent_output(data)
        proposal_ids: List[int] = []
        for node in data.get("proposed_nodes", []):
            proposal_ids.append(
                self.proposals.create(
                    ProposalType.CREATE_PROJECT_NODE.value,
                    f"Create project node: {node.get('title')}",
                    {
                        "target_project_id": project["id"],
                        "node_title": node.get("title"),
                        "node_type": node.get("node_type") or node.get("type") or "specific_work",
                        "parent_node_id": node.get("parent_node_id"),
                        "section": node.get("section"),
                    },
                    target_object_ref=str(project["id"]),
                    source="agent-output",
                    rationale=data.get("summary"),
                )
            )
        for mapping in data.get("object_mappings", []):
            object_ref = str(mapping.get("object_id") or mapping.get("object_ref") or "")
            if not object_ref:
                continue
            proposal_ids.append(
                self.proposals.create(
                    ProposalType.LINK_OBJECT_TO_NODE.value,
                    "Link object to project node",
                    {
                        "relation_type": RelationType.BELONGS_TO.value,
                        "target_project_id": project["id"],
                        "target_project_node_id": mapping.get("target_project_node_id") or mapping.get("node_id"),
                        "placement_status": "placed",
                        "confidence": mapping.get("confidence", 0.75),
                    },
                    target_object_ref=object_ref,
                    source="agent-output",
                    rationale=mapping.get("reason") or data.get("summary"),
                )
            )
        for candidate in data.get("proposal_candidates", []):
            proposal_ids.append(self._candidate_to_proposal(project, candidate, data.get("summary")))
        return {"project": project["title"], "proposal_ids": proposal_ids, "proposals": [self.proposals.get(pid) for pid in proposal_ids]}

    def mock_restructure(self, project_ref: str, dry_run: bool = False) -> Dict[str, Any]:
        project = self._project(project_ref)
        unplaced = self.unplaced(str(project["id"]))
        candidate = {
            "summary": "Mock restructure proposes a review node and maps unplaced items.",
            "questions_for_user": [],
            "proposed_nodes": [{"title": "待归位整理", "node_type": "specific_work", "section": "具体事务"}],
            "object_mappings": [
                {"object_id": item["id"], "target_project_node_id": None, "confidence": 0.65, "reason": "mock unplaced grouping"}
                for item in unplaced[:10]
            ],
            "proposal_candidates": [],
            "risks": [],
            "unplaced_remaining": [item["id"] for item in unplaced[10:]],
        }
        if dry_run:
            return candidate
        tmp = self.settings.app_dir / "mock-project-restructure-output.json"
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps(candidate, ensure_ascii=False, indent=2), encoding="utf-8")
        return self.proposals_from_agent_output(str(project["id"]), tmp)

    def project_health(self, project_ref: str) -> Dict[str, Any]:
        project = self._project(project_ref)
        items = self.project_items(str(project["id"]))
        tasks = [item for item in items if item["object_type"] == "task"]
        results = self.result_records(str(project["id"]))
        tree = self.tree_service.build(str(project["id"]), detail=False)
        flat: List[Dict[str, Any]] = []
        self.tree_service._flatten(tree.get("tree", []), flat)
        pending = self.conn.execute(
            """
            SELECT COUNT(*) AS c FROM proposals
            WHERE status IN ('suggested', 'accepted', 'edited')
              AND (target_object_id=? OR payload_json LIKE ?)
            """,
            (project["id"], f'%"target_project_id": {project["id"]}%'),
        ).fetchone()["c"]
        open_reviews = self.conn.execute(
            """
            SELECT COUNT(*) AS c FROM review_sessions
            WHERE status IN ('open', 'in_progress', 'paused') AND (title LIKE ? OR scope_json LIKE ?)
            """,
            (f"%{project['title']}%", f"%{project['id']}%"),
        ).fetchone()["c"]
        done_without_result = sum(1 for task in tasks if task.get("status") == "done" and not self._object_has_result(task["id"]))
        unplaced_count = len(self.unplaced(str(project["id"])))
        health_score = max(0, 100 - unplaced_count * 8 - int(pending) * 3 - done_without_result * 5)
        last_activity = max([item.get("last_seen_at") for item in items if item.get("last_seen_at")] + [project.get("last_seen_at") or ""], default=None)
        return {
            "view": "project-health",
            "project": {"id": project["id"], "title": project["title"]},
            "active_tasks_count": sum(1 for item in tasks if item.get("status") in {"todo", "doing"}),
            "waiting_count": sum(1 for item in tasks if item.get("status") == "waiting"),
            "unplaced_count": unplaced_count,
            "ideas_count": sum(1 for item in items if item["object_type"] == "idea"),
            "resources_count": sum(1 for item in items if item["object_type"] in {"reference", "resource"}),
            "results_count": len(results),
            "done_without_result_count": done_without_result,
            "pending_proposals_count": int(pending),
            "open_reviews_count": int(open_reviews),
            "tree_depth": max([node.get("semantic_depth", 0) for node in flat], default=0),
            "tree_node_count": len(flat),
            "last_activity": last_activity,
            "recent_results": results[:5],
            "health_score": health_score,
        }

    def result_records(self, project_ref: str) -> List[Dict[str, Any]]:
        project = self._project(project_ref)
        rows = self.conn.execute(
            """
            SELECT r.id, r.raw_text, r.normalized_text, l.file_path, l.page_name, l.line_start, r.metadata_json
            FROM source_records r
            JOIN locations l ON l.id=r.location_id
            WHERE l.file_path=? AND r.metadata_json LIKE '%"semantic_marker": "成果"%'
            ORDER BY l.line_start DESC, r.id DESC
            LIMIT 100
            """,
            (project.get("file_path"),),
        ).fetchall()
        return [self._record_row(row) for row in rows if semantic_marker_content(row["raw_text"])]

    def markdown_pack(self, data: Dict[str, Any]) -> str:
        lines = [f"# {data.get('view', 'project-pack')}", ""]
        project = data.get("project", {})
        lines.append(f"- project: {project.get('title')} (#{project.get('id')})")
        if data.get("project_health"):
            health = data["project_health"]
            lines.append(f"- health_score: {health.get('health_score')}")
            lines.append(f"- unplaced_count: {health.get('unplaced_count')}")
        lines.extend(["", "## Constraints", ""])
        for key, value in self.constraints().items():
            lines.append(f"- `{key}`: {value}")
        if data.get("unplaced_objects") is not None:
            lines.extend(["", "## Unplaced Objects", ""])
            for item in data.get("unplaced_objects", [])[:20]:
                lines.append(f"- #{item['id']} `{item['object_type']}` {item.get('status') or ''} {item['title']}")
        if data.get("node_summaries") is not None:
            lines.extend(["", "## Node Evidence", ""])
            for node in data.get("node_summaries", [])[:30]:
                lines.append(f"- `{node['node_id']}` {node['type']} {node['title']} -> `{node['raw_evidence_command']}`")
        return "\n".join(lines).rstrip() + "\n"

    def constraints(self) -> Dict[str, Any]:
        return {
            "allowed_operations": ALLOWED_OPERATIONS,
            "forbidden_operations": FORBIDDEN_OPERATIONS,
            "proposal_required_operations": PROPOSAL_REQUIRED_OPERATIONS,
            "writeback_policy": "append-only; preview, backup, and rollback required before Logseq changes",
            "raw_logseq_policy": "do not move, delete, merge, or reorder original blocks",
        }

    def _default_clarify_proposals(self, project: Dict[str, Any], obj: Dict[str, Any]) -> List[int]:
        ids = []
        ids.append(
            self.proposals.create(
                ProposalType.LINK_OBJECT_TO_NODE.value,
                f"Clarify placement for {obj['title']}",
                {
                    "relation_type": RelationType.BELONGS_TO.value,
                    "target_project_id": project["id"],
                    "target_project_node_id": None,
                    "placement_status": "needs_node",
                    "confidence": 0.62,
                },
                target_object_ref=str(obj["id"]),
                source="project-clarify",
                rationale="Unplaced project item should be reviewed and assigned to a node.",
            )
        )
        if obj.get("object_type") == "idea":
            ids.append(
                self.proposals.create(
                    ProposalType.CONVERT_IDEA_TO_TASK.value,
                    f"Consider converting idea to task: {obj['title']}",
                    {"source_object_id": obj["id"], "writeback_suggested": False},
                    target_object_ref=str(obj["id"]),
                    source="project-clarify",
                    rationale="Idea may imply a concrete next action.",
                )
            )
        return ids

    def _provider_result_to_project_proposals(self, project: Dict[str, Any], result: ProviderResult) -> List[int]:
        return [self._candidate_to_proposal(project, candidate, result.summary) for candidate in result.proposal_candidates]

    def _candidate_to_proposal(self, project: Dict[str, Any], candidate: Dict[str, Any], summary: Optional[str]) -> int:
        ptype = candidate.get("proposal_type")
        if ptype not in {item.value for item in ProposalType}:
            raise ValueError(f"Unsupported proposal type: {ptype}")
        payload = dict(candidate.get("payload") or {})
        payload.setdefault("target_project_id", project["id"])
        target = candidate.get("target") or {}
        target_ref = str(target.get("object_id") or payload.get("source_object_id") or project["id"])
        return self.proposals.create(
            ptype,
            candidate.get("title") or summary or "Project lifecycle proposal",
            payload,
            risk=candidate.get("risk"),
            target_object_ref=target_ref,
            source="agent-output",
            rationale=candidate.get("reasoning_summary") or summary,
            metadata={"risks": candidate.get("risks", [])},
        )

    def _placement_from_location(self, project: Dict[str, Any], obj: Dict[str, Any]) -> str:
        metadata = obj.get("metadata") or {}
        if metadata.get("placement_status"):
            return metadata["placement_status"]
        section_markers = metadata.get("section_markers") or []
        if _has_section_marker(section_markers, {"项目收件箱", "待澄清"}):
            return "unplaced"
        if _has_section_marker(section_markers, {"目标", "里程碑", "工作流", "具体事务", "小任务", "资源", "成果", "想法", "反思", "无成果"}):
            return "placed"
        if obj.get("file_path") == project.get("file_path"):
            return "project_level"
        return "unplaced"

    def _is_unplaced(self, item: Dict[str, Any]) -> bool:
        return not item.get("belongs_to_node") and item.get("placement_status") in {"unplaced", "project_level", "needs_node"}

    def _is_inbox_item(self, item: Dict[str, Any]) -> bool:
        meta = item.get("metadata") or {}
        return item.get("placement_status") == "unplaced" or _has_section_marker(meta.get("section_markers") or [], {"项目收件箱", "待澄清"})

    def _object_has_result(self, object_id: int) -> bool:
        return any(record.get("role") == "result_marker" for record in self.repo.records_for_object(int(object_id), limit=100))

    def _recent_project_records(self, project: Dict[str, Any], limit: int = 12) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT r.id, r.raw_text, r.normalized_text, l.file_path, l.page_name, l.journal_date, l.line_start, r.metadata_json
            FROM source_records r
            JOIN locations l ON l.id=r.location_id
            WHERE l.file_path=?
            ORDER BY r.updated_at DESC, r.id DESC
            LIMIT ?
            """,
            (project.get("file_path"), limit),
        ).fetchall()
        return [self._record_row(row) for row in rows]

    def _record_row(self, row) -> Dict[str, Any]:
        data = dict(row)
        if "metadata_json" in data:
            data["metadata"] = json.loads(data.pop("metadata_json") or "{}")
        return data

    def _pack_project(self, project: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": project["id"],
            "title": project["title"],
            "status": project.get("status"),
            "source_item_id": project.get("source_item_id"),
            "page_name": project.get("page_name"),
        }

    def _pack_object(self, obj: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": obj["id"],
            "object_type": obj["object_type"],
            "title": obj["title"],
            "status": obj.get("status"),
            "source": f"{obj.get('page_name') or obj.get('journal_date') or ''}:{obj.get('line_start') or ''}",
            "belongs_to_project": bool(obj.get("belongs_to_project")),
            "belongs_to_node": bool(obj.get("belongs_to_node")),
            "project_node_id": obj.get("project_node_id"),
            "placement_status": obj.get("placement_status"),
        }

    def _project(self, project_ref: str) -> Dict[str, Any]:
        project_id = self.repo.resolve_object_id(project_ref)
        if project_id is None:
            raise NotFoundError(f"Project not found: {project_ref}")
        project = self.repo.get_object(project_id)
        if not project or project.get("object_type") != ObjectType.PROJECT.value:
            raise TaskManagerError(f"Object is not a project: {project_ref}")
        return project

    def _ingest_file(self, file_path: Path) -> None:
        result = LogseqAdapter(self.graph_path).parse_file(Path(file_path))
        Merger(self.repo).ingest(result)
        self.conn.commit()

    def _ensure_project_object(self, page_name: str, file_path: Path, template: str, goal: Optional[str]) -> int:
        rel = str(Path(file_path).relative_to(self.graph_path))
        source_id = f"page:{rel}"
        loc = Location(
            source_type="logseq",
            source_item_id=source_id,
            graph_path=str(self.graph_path),
            file_path=str(file_path),
            page_name=page_name,
            line_start=1,
            line_end=len(Path(file_path).read_text(encoding="utf-8").splitlines()),
            block_path=[page_name],
            metadata={"created_by": "project_lifecycle"},
        )
        obj = ActionObject(
            object_type=ObjectType.PROJECT.value,
            title=page_name,
            source_type="logseq",
            source_item_id=source_id,
            status="active",
            created_at=date.today().isoformat(),
            created_at_source="project_lifecycle_create",
            confidence=0.99,
            metadata={
                "extraction_rule": "project_lifecycle_create",
                "template": template,
                "goal": goal,
                "page_properties": {"PARA": "[[PARA/Project]]", "status": "active"},
            },
        )
        project_id = self.repo.upsert_object(obj, loc)
        record_id = self.repo.resolve_record_id(source_id)
        if record_id:
            self.repo.link_object_record(project_id, record_id, "definition")
        self.conn.commit()
        return project_id


def project_template(template: str, *, goal: Optional[str] = None) -> str:
    created = date.today().isoformat()
    if template == "minimal":
        lines = [
            "- Project",
            "  PARA:: [[PARA/Project]]",
            "  status:: active",
            f"  created-at:: {created}",
            "",
            "- **[项目收件箱]**",
            "",
            "- **[具体事务]**",
            "",
            "- **[资源]**",
            "",
            "- **[成果]**",
            "",
            "- **[想法]**",
            "",
            "- **[反思]**",
        ]
    else:
        lines = [
            "- Project",
            "  PARA:: [[PARA/Project]]",
            "  status:: active",
            f"  created-at:: {created}",
            "",
            "- **[目标]**",
            "    - **[待澄清]** 这个项目为什么值得做？",
            "",
            "- **[项目收件箱]**",
            "    - 用于临时承接尚未归位的 TODO / 想法 / 资源 / 成果",
            "",
            "- **[具体事务]**",
            "",
            "- **[小任务]**",
            "",
            "- **[资源]**",
            "",
            "- **[成果]**",
            "",
            "- **[想法]**",
            "",
            "- **[反思]**",
        ]
    if goal:
        for index, line in enumerate(lines):
            if line == "- **[目标]**":
                lines.insert(index + 1, f"    - {goal.strip()}")
                break
        else:
            lines.insert(5, "- **[目标]**")
            lines.insert(6, f"    - {goal.strip()}")
            lines.insert(7, "")
    return "\n".join(lines)


def agent_output_schema() -> Dict[str, Any]:
    return {
        "summary": "string",
        "questions_for_user": "array",
        "proposed_nodes": "array",
        "object_mappings": "array",
        "proposal_candidates": "array",
        "risks": "array",
        "unplaced_remaining": "array",
    }


def validate_agent_output(data: Dict[str, Any]) -> None:
    required = {"summary", "questions_for_user", "proposed_nodes", "object_mappings", "proposal_candidates", "risks", "unplaced_remaining"}
    missing = sorted(required - set(data))
    if missing:
        raise ValueError(f"Agent output missing keys: {', '.join(missing)}")
    for key in required - {"summary"}:
        if not isinstance(data.get(key), list):
            raise ValueError(f"Agent output `{key}` must be a list.")


def _has_section_marker(section_markers: List[str], marker_names: set) -> bool:
    return any(any(f"[{name}]" in marker or name == marker for name in marker_names) for marker in section_markers)
