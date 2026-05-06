import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from task_manager_cli.adapters.logseq.extractors import has_project_marker
from task_manager_cli.config.settings import Settings
from task_manager_cli.core.enums import ProposalType
from task_manager_cli.projects.tree import ProjectTreeService
from task_manager_cli.storage.repositories import Repository


MEMBERSHIP_TYPES = {
    ProposalType.LINK_TO_PROJECT.value,
    ProposalType.LINK_TO_PROJECT_NODE.value,
    ProposalType.LINK_IDEA_TO_PROJECT.value,
    ProposalType.LINK_RESOURCE_TO_PROJECT.value,
    ProposalType.ATTACH_TO_MINI_PROJECT.value,
}


class ProjectQualityService:
    def __init__(self, conn, settings: Settings):
        self.conn = conn
        self.settings = settings
        self.repo = Repository(conn)
        self.tree_service = ProjectTreeService(conn, settings)

    def project_tree_quality(self) -> Dict[str, Any]:
        pages = self._page_records()
        projects = self.repo.list_objects("project", limit=100000)
        project_source_ids = {item["source_item_id"] for item in projects}
        node_types: Counter = Counter()
        suspicious: List[Dict[str, Any]] = []
        parse_warnings: List[Dict[str, Any]] = []
        empty_projects: List[Dict[str, Any]] = []
        suspicious_projects: List[Dict[str, Any]] = []
        structured = 0
        without_structured = 0
        total_nodes = 0
        duplicate_node_ids = 0
        orphan_nodes = 0
        truncations = 0
        marker_counts: Counter = Counter()
        source_location_mismatches = self._source_location_mismatches()
        for project in projects:
            try:
                tree = self.tree_service.build(str(project["id"]), detail=True)
            except Exception as exc:  # report diagnostics should not fail the whole run
                parse_warnings.append({"project": project["title"], "error": str(exc)})
                continue
            flat = list(self._flatten(tree.get("tree", [])))
            total_nodes += len(flat)
            ids = [node["id"] for node in flat]
            duplicate_node_ids += len(ids) - len(set(ids))
            if tree["summary"].get("has_structured_markers"):
                structured += 1
            else:
                without_structured += 1
            if not flat:
                empty_projects.append({"project_id": project["id"], "title": project["title"]})
            if tree["summary"].get("node_count", 0) > 80:
                truncations += 1
            for node in flat:
                node_types[node["node_type"]] += 1
                if node.get("marker"):
                    marker_counts[node["marker"]] += 1
                if node["depth"] > 8:
                    suspicious.append(self._node_example(project, node, "very_deep_node"))
                if node["node_type"] == "unknown" and self._looks_actionable(node.get("title", "")):
                    suspicious.append(self._node_example(project, node, "unknown_action_like_node"))
                if node["node_type"] == "resource" and (node.get("status") in {"todo", "doing", "done", "waiting"}):
                    suspicious.append(self._node_example(project, node, "resource_has_task_status"))
            if not tree["summary"].get("has_structured_markers") or any(item["project"] == project["title"] for item in suspicious[-10:]):
                suspicious_projects.append({"project_id": project["id"], "title": project["title"]})
        skipped_non_projects = [
            {"page": page["page_name"], "file_path": page["file_path"]}
            for page in pages
            if page["source_item_id"] not in project_source_ids
        ]
        return {
            "view": "project-tree-quality",
            "scanned_project_pages": len(pages),
            "recognized_project_pages": len(projects),
            "skipped_non_project_pages": len(skipped_non_projects),
            "project_pages_with_structured_markers": structured,
            "project_pages_without_structured_markers": without_structured,
            "total_tree_nodes": total_nodes,
            "node_type_distribution": dict(sorted(node_types.items())),
            "projects_with_empty_tree": empty_projects,
            "projects_with_suspicious_tree": suspicious_projects,
            "mini_project_count": node_types.get("mini_project", 0),
            "resource_node_count": node_types.get("resource", 0),
            "idea_node_count": node_types.get("idea", 0),
            "result_marker_count": node_types.get("result", 0) + node_types.get("no_result", 0),
            "source_location_mismatch_count": len(source_location_mismatches),
            "duplicate_node_id_count": duplicate_node_ids,
            "orphan_node_count": orphan_nodes,
            "parse_warnings": parse_warnings,
            "large_project_page_truncation_status": {"payload_summary_would_truncate": truncations},
            "marker_distribution": dict(sorted(marker_counts.items())),
            "examples_of_suspicious_nodes": suspicious[:10],
            "source_location_mismatches": source_location_mismatches[:10],
            "skipped_non_project_examples": skipped_non_projects[:10],
        }

    def mini_project_quality(self) -> Dict[str, Any]:
        mini_projects = self.repo.list_objects("mini_project", limit=100000)
        duplicate_titles: Dict[str, List[int]] = defaultdict(list)
        suspicious: List[Dict[str, Any]] = []
        from_journals = 0
        from_pages = 0
        with_child_actions = 0
        with_resources = 0
        with_results = 0
        without_children = 0
        for item in mini_projects:
            duplicate_titles[item["title"]].append(item["id"])
            if item.get("journal_date"):
                from_journals += 1
            else:
                from_pages += 1
            records = self.repo.records_for_object(int(item["id"]), limit=100)
            child_roles = [record.get("role") for record in records if record.get("role") != "definition"]
            if any(role == "child_record" for role in child_roles):
                with_child_actions += 1
            if any(role == "resource" for role in child_roles):
                with_resources += 1
            if any(role == "result_marker" for role in child_roles):
                with_results += 1
            if not child_roles:
                without_children += 1
                suspicious.append(self._object_example(item, "mini_project_without_children"))
            if item["title"].strip() in {"", "未命名小任务"}:
                suspicious.append(self._object_example(item, "empty_or_default_title"))
        duplicate_examples = [
            {"title": title, "object_ids": ids}
            for title, ids in duplicate_titles.items()
            if len(ids) > 1
        ]
        wrongly_promoted = self.conn.execute(
            """
            SELECT COUNT(*) AS c FROM objects
            WHERE object_type='project' AND metadata_json LIKE '%logseq_mini_project_marker%'
            """
        ).fetchone()["c"]
        return {
            "view": "mini-project-quality",
            "mini_project_count": len(mini_projects),
            "mini_projects_from_project_pages": from_pages,
            "mini_projects_from_journals": from_journals,
            "mini_projects_with_child_action_items": with_child_actions,
            "mini_projects_with_resources": with_resources,
            "mini_projects_with_result_markers": with_results,
            "mini_projects_without_children": without_children,
            "mini_projects_wrongly_promoted_to_project": int(wrongly_promoted),
            "duplicate_mini_projects": len(duplicate_examples),
            "duplicate_mini_project_examples": duplicate_examples[:10],
            "suspicious_mini_projects": suspicious[:10],
            "source_location_mismatch_count": len(self._source_location_mismatches(object_type="mini_project")),
            "examples": [self._object_example(item, "sample") for item in mini_projects[:10]],
        }

    def membership_quality(self) -> Dict[str, Any]:
        candidates = self._membership_candidates()
        proposals = self._membership_proposals()
        proposal_types = Counter(item["proposal_type"] for item in proposals)
        risks = Counter(item["risk"] for item in proposals)
        source_distribution = Counter(item["source"] for item in proposals)
        confidence_counts = Counter(candidate["confidence_label"] for candidate in candidates)
        duplicates = self._duplicate_membership_proposals(proposals)
        existing_relations = self._applied_membership_relations()
        target_missing = [item for item in proposals if item.get("payload", {}).get("target_project_id") and not self.repo.get_object(int(item["payload"]["target_project_id"]))]
        node_missing = [item for item in proposals if item.get("payload", {}).get("target_project_node_id") and not self._node_exists(item["payload"].get("target_project_id"), item["payload"].get("target_project_node_id"))]
        reference_wrong = [
            item
            for item in proposals
            if self._target_object_type(item) in {"reference", "resource"} and item["proposal_type"] not in {"link_resource_to_project", "link_to_project_node"}
        ]
        return {
            "view": "membership-quality",
            "candidate_count": len(candidates),
            "proposals_generated": len(proposals),
            "high_confidence_count": confidence_counts.get("high", 0),
            "medium_confidence_count": confidence_counts.get("medium", 0),
            "low_confidence_candidate_count": confidence_counts.get("low", 0),
            "low_confidence_not_promoted_count": sum(1 for item in candidates if item["confidence_label"] == "low" and not item["would_promote_to_proposal"]),
            "candidate_source_distribution": dict(Counter(item["source"] for item in candidates)),
            "proposal_type_distribution": dict(sorted(proposal_types.items())),
            "risk_distribution": dict(sorted(risks.items())),
            "proposal_source_distribution": dict(sorted(source_distribution.items())),
            "project_target_missing_count": len(target_missing),
            "node_target_missing_count": len(node_missing),
            "duplicate_proposal_count": len(duplicates),
            "duplicate_proposal_examples": duplicates[:10],
            "reference_wrongly_proposed_as_action_count": len(reference_wrong),
            "idea_to_project_proposal_count": proposal_types.get("link_idea_to_project", 0),
            "resource_to_project_proposal_count": proposal_types.get("link_resource_to_project", 0),
            "false_positive_examples": reference_wrong[:10],
            "unresolved_ambiguous_candidates": [item for item in candidates if item["confidence_label"] == "low"][:10],
            "existing_applied_relation_count": len(existing_relations),
        }

    def markdown(self, report: Dict[str, Any]) -> str:
        title = report.get("view", "quality-report").replace("-", " ").title()
        lines = [f"# {title}", ""]
        for key, value in report.items():
            if key == "view":
                continue
            label = key.replace("_", " ")
            if isinstance(value, (int, float, str, bool)) or value is None:
                lines.append(f"- `{key}`: `{value}`")
            elif isinstance(value, dict):
                lines.extend([f"## {label.title()}", ""])
                for subkey, subvalue in value.items():
                    lines.append(f"- `{subkey}`: `{subvalue}`")
                lines.append("")
            elif isinstance(value, list):
                lines.extend([f"## {label.title()}", ""])
                if not value:
                    lines.append("- none")
                for item in value[:10]:
                    lines.append(f"- {json.dumps(item, ensure_ascii=False, sort_keys=True)}")
                lines.append("")
        return "\n".join(lines).rstrip() + "\n"

    def _page_records(self) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT r.source_item_id, l.file_path, l.page_name, r.raw_text
            FROM source_records r
            JOIN locations l ON l.id=r.location_id
            WHERE r.record_type='page' AND l.journal_date IS NULL
            ORDER BY l.page_name
            """
        ).fetchall()
        return [dict(row) for row in rows]

    def _source_location_mismatches(self, object_type: Optional[str] = None) -> List[Dict[str, Any]]:
        params: List[Any] = []
        where = ""
        if object_type:
            where = "AND o.object_type=?"
            params.append(object_type)
        rows = self.conn.execute(
            f"""
            SELECT o.id, o.title, o.object_type, cl.source_item_id AS canonical_source_item_id,
                   cl.file_path AS canonical_file_path, cl.line_start AS canonical_line_start,
                   rl.source_item_id AS definition_source_item_id,
                   rl.file_path AS definition_file_path, rl.line_start AS definition_line_start
            FROM objects o
            JOIN locations cl ON cl.id=o.canonical_location_id
            JOIN object_record_links orl ON orl.object_id=o.id AND orl.role='definition'
            JOIN source_records r ON r.id=orl.record_id
            JOIN locations rl ON rl.id=r.location_id
            WHERE (
                COALESCE(cl.file_path, '') != COALESCE(rl.file_path, '')
                OR COALESCE(cl.line_start, -1) != COALESCE(rl.line_start, -1)
                OR COALESCE(cl.source_item_id, '') != COALESCE(rl.source_item_id, '')
            ) {where}
            ORDER BY o.id
            """,
            params,
        ).fetchall()
        return [dict(row) for row in rows]

    def _membership_candidates(self) -> List[Dict[str, Any]]:
        projects = self.repo.list_objects("project", limit=100000)
        project_titles = {item["title"]: item for item in projects}
        objects = []
        for object_type in ("task", "idea", "mini_project", "reference", "resource"):
            objects.extend(self.repo.list_objects(object_type, limit=100000))
        candidates: List[Dict[str, Any]] = []
        for obj in objects:
            metadata = obj.get("metadata") or {}
            refs = metadata.get("page_refs") or []
            for ref in refs:
                project = project_titles.get(ref)
                if not project:
                    continue
                confidence = 0.82
                if obj.get("page_name") == ref:
                    confidence = 0.92
                    source = "project_page"
                else:
                    source = "explicit_page_ref"
                candidates.append(self._candidate(obj, project, confidence, source))
            if obj.get("page_name") in project_titles:
                candidates.append(self._candidate(obj, project_titles[obj["page_name"]], 0.92, "project_page"))
            for title, project in project_titles.items():
                if title in obj.get("title", "") and not any(c["object_id"] == obj["id"] and c["project_id"] == project["id"] for c in candidates):
                    candidates.append(self._candidate(obj, project, 0.62, "title_keyword"))
                    continue
                weak = title
                for prefix in ("项目-", "任务-", "学习-", "课程-", "阶段-"):
                    weak = weak.removeprefix(prefix)
                if weak and len(weak) >= 2 and weak in obj.get("title", "") and not any(c["object_id"] == obj["id"] and c["project_id"] == project["id"] for c in candidates):
                    candidates.append(self._candidate(obj, project, 0.45, "weak_keyword"))
        return candidates

    def _candidate(self, obj: Dict[str, Any], project: Dict[str, Any], confidence: float, source: str) -> Dict[str, Any]:
        label = "high" if confidence >= 0.8 else ("medium" if confidence >= 0.6 else "low")
        return {
            "object_id": obj["id"],
            "object_title": obj["title"],
            "object_type": obj["object_type"],
            "project_id": project["id"],
            "project_title": project["title"],
            "confidence": confidence,
            "confidence_label": label,
            "source": source,
            "would_promote_to_proposal": confidence >= 0.6,
        }

    def _membership_proposals(self) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT * FROM proposals
            WHERE proposal_type IN ('link_to_project', 'link_to_project_node', 'link_idea_to_project', 'link_resource_to_project', 'attach_to_mini_project')
            ORDER BY id
            """
        ).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            item["payload"] = json.loads(item.pop("payload_json") or "{}")
            item["metadata"] = json.loads(item.pop("metadata_json") or "{}")
            items.append(item)
        return items

    def _duplicate_membership_proposals(self, proposals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        active = [item for item in proposals if item.get("status") in {"suggested", "accepted", "edited"}]
        buckets: Dict[tuple, List[int]] = defaultdict(list)
        for item in active:
            payload = item.get("payload") or {}
            key = (
                item.get("target_object_id"),
                payload.get("target_project_id"),
                payload.get("target_project_node_id"),
                item.get("proposal_type"),
            )
            buckets[key].append(item["id"])
        return [
            {"target_object_id": key[0], "target_project_id": key[1], "target_project_node_id": key[2], "proposal_type": key[3], "proposal_ids": ids}
            for key, ids in buckets.items()
            if len(ids) > 1
        ]

    def _applied_membership_relations(self) -> List[Dict[str, Any]]:
        rows = self.conn.execute("SELECT id, metadata_json FROM relations WHERE relation_type='belongs_to' AND metadata_json LIKE '%proposal_id%'").fetchall()
        return [dict(row) for row in rows]

    def _target_object_type(self, proposal: Dict[str, Any]) -> Optional[str]:
        object_id = proposal.get("target_object_id")
        if not object_id:
            return None
        obj = self.repo.get_object(int(object_id))
        return obj.get("object_type") if obj else None

    def _node_exists(self, project_id: Optional[int], node_id: Optional[str]) -> bool:
        if not project_id or not node_id:
            return True
        project = self.repo.get_object(int(project_id))
        if not project:
            return False
        try:
            tree = self.tree_service.build(str(project_id), detail=False)
        except Exception:
            return False
        return any(node["id"] == node_id for node in self._flatten(tree.get("tree", [])))

    def _flatten(self, nodes: Iterable[Dict[str, Any]]) -> Iterable[Dict[str, Any]]:
        for node in nodes:
            yield node
            yield from self._flatten(node.get("children", []))

    def _node_example(self, project: Dict[str, Any], node: Dict[str, Any], reason: str) -> Dict[str, Any]:
        return {
            "reason": reason,
            "project": project["title"],
            "node_id": node["id"],
            "node_type": node["node_type"],
            "title": node["title"],
            "line_start": node.get("location", {}).get("line_start"),
        }

    def _object_example(self, obj: Dict[str, Any], reason: str) -> Dict[str, Any]:
        return {
            "reason": reason,
            "object_id": obj["id"],
            "title": obj["title"],
            "page_name": obj.get("page_name"),
            "journal_date": obj.get("journal_date"),
            "line_start": obj.get("line_start"),
        }

    def _looks_actionable(self, text: str) -> bool:
        return any(token in text for token in ("TODO", "待办", "处理", "确认", "完成"))
