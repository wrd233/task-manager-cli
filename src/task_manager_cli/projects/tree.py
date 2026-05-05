import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from task_manager_cli.adapters.logseq.extractors import (
    content_hash,
    is_reference_record,
    normalize_text,
    semantic_marker,
    semantic_marker_content,
)
from task_manager_cli.adapters.logseq.parser import LogseqBlock, parse_logseq_file
from task_manager_cli.config.settings import Settings
from task_manager_cli.core.enums import ObjectType
from task_manager_cli.core.errors import ConfigError, NotFoundError, TaskManagerError
from task_manager_cli.storage.repositories import Repository


NODE_TYPE_BY_MARKER = {
    "目标": "objective",
    "里程碑": "milestone",
    "工作流": "workflow",
    "小任务": "mini_project",
    "具体事务": "specific_work",
    "资源": "resource",
    "成果": "result",
    "无成果": "no_result",
    "想法": "idea",
    "注": "user_annotation",
    "AI注": "ai_annotation",
    "待澄清": "needs_clarify",
}

LABEL_BY_NODE_TYPE = {
    "objective": "目标",
    "milestone": "里程碑",
    "workflow": "工作流",
    "mini_project": "小任务",
    "specific_work": "具体事务",
    "resource": "资源",
    "result": "成果",
    "no_result": "无成果",
    "idea": "想法",
    "user_annotation": "注",
    "ai_annotation": "AI注",
    "needs_clarify": "待澄清",
    "action_item": "行动",
    "unknown": "未识别",
}


class ProjectTreeService:
    def __init__(self, conn, settings: Settings):
        self.conn = conn
        self.settings = settings
        self.repo = Repository(conn)

    def build(self, project_ref: str, detail: bool = False) -> Dict[str, Any]:
        project_id = self.repo.resolve_object_id(project_ref)
        if project_id is None:
            raise NotFoundError(f"Project not found: {project_ref}")
        project = self.repo.get_object(project_id)
        if not project or project.get("object_type") != ObjectType.PROJECT.value:
            raise TaskManagerError(f"Object is not a project: {project_ref}")
        file_path = project.get("file_path")
        if not file_path:
            raise ConfigError("Project tree requires a Logseq project page file.")
        path = Path(file_path)
        if not path.exists():
            raise ConfigError(f"Project page file not found: {file_path}")
        parsed = parse_logseq_file(path, project.get("title") or project.get("page_name"))
        source_map = self._objects_by_source()
        roots = [self._node(block, source_map, detail=detail) for block in parsed.blocks if block.parent is None]
        recognized = self._count_recognized(roots)
        return {
            "project": {
                "id": project["id"],
                "title": project["title"],
                "source_item_id": project["source_item_id"],
                "file_path": file_path if detail else None,
                "page_name": project.get("page_name"),
                "confidence": project.get("confidence"),
            },
            "tree": roots,
            "summary": {
                "node_count": self._count_nodes(roots),
                "recognized_node_count": recognized,
                "has_structured_markers": recognized > 0,
                "readonly": True,
            },
        }

    def render_markdown(self, tree: Dict[str, Any], detail: bool = False) -> str:
        project = tree["project"]
        lines = [f"# 项目树：{project['title']}", ""]
        summary = tree.get("summary", {})
        if not summary.get("node_count"):
            lines.append("未找到可展示的项目页块。")
            return "\n".join(lines)
        if not summary.get("has_structured_markers"):
            lines.append("未识别到结构化项目 marker，以下按 Logseq 原始层级展示。")
            lines.append("")
        for node in tree.get("tree", []):
            self._render_node(lines, node, depth=0, detail=detail)
        return "\n".join(lines)

    def agent_view(self, project_ref: str, detail: bool = False) -> Dict[str, Any]:
        tree = self.build(project_ref, detail=detail)
        tree["agent_context"] = {
            "included": [
                "project metadata",
                "node tree",
                "node source/location",
                "action/idea/resource/result/annotation markers",
            ],
            "omitted_by_default": ["full project page raw text", "linked record bodies"],
        }
        return tree

    def summary_for_payload(self, project_ref: Optional[str], max_nodes: int = 24) -> Optional[Dict[str, Any]]:
        if not project_ref:
            return None
        tree = self.build(project_ref, detail=False)
        flat: List[Dict[str, Any]] = []
        self._flatten(tree.get("tree", []), flat)
        return {
            "project": tree["project"],
            "summary": tree["summary"],
            "nodes": [
                {
                    "node_id": node["id"],
                    "type": node["node_type"],
                    "title": node["title"][:120],
                    "depth": node["depth"],
                    "line_start": node["location"].get("line_start"),
                }
                for node in flat[:max_nodes]
            ],
            "truncated": len(flat) > max_nodes,
        }

    def _node(self, block: LogseqBlock, source_map: Dict[str, Dict[str, Any]], detail: bool = False) -> Dict[str, Any]:
        source_item_id = self._block_source_id(block)
        marker = semantic_marker(block.raw)
        node_type = self._node_type(block, marker)
        title = self._title(block, marker)
        obj = source_map.get(source_item_id)
        metadata: Dict[str, Any] = {}
        if detail:
            metadata = {
                "raw_text": block.text,
                "page_refs": block.page_refs,
                "block_refs": block.block_refs,
                "semantic_marker": marker,
            }
        return {
            "id": source_item_id,
            "node_type": node_type,
            "marker": marker,
            "title": title,
            "depth": block.indent,
            "object_id": obj.get("id") if obj else None,
            "object_type": obj.get("object_type") if obj else None,
            "status": block.task[0].lower() if block.task else (obj.get("status") if obj else None),
            "location": {
                "source_type": "logseq",
                "source_item_id": source_item_id,
                "file_path": str(block.file_path) if detail else None,
                "page_name": block.page_name,
                "line_start": block.line_number,
                "block_uuid": block.uuid,
                "block_path": block.block_path(),
            },
            "metadata": metadata,
            "children": [self._node(child, source_map, detail=detail) for child in block.children if child.properties.get("__property_block__") != "true"],
        }

    def _node_type(self, block: LogseqBlock, marker: Optional[str]) -> str:
        if block.task:
            return "action_item"
        if marker in NODE_TYPE_BY_MARKER:
            return NODE_TYPE_BY_MARKER[marker]
        if is_reference_record(block.raw) or "http://" in block.text or "https://" in block.text:
            return "resource"
        if block.idea_title:
            return "idea"
        return "unknown"

    def _title(self, block: LogseqBlock, marker: Optional[str]) -> str:
        if block.task:
            return block.task[1]
        if marker:
            content = semantic_marker_content(block.raw)
            return content or normalize_text(block.text.replace("**", ""))
        return block.normalized_text

    def _render_node(self, lines: List[str], node: Dict[str, Any], depth: int, detail: bool) -> None:
        indent = "  " * depth
        label = LABEL_BY_NODE_TYPE.get(node["node_type"], node["node_type"])
        status = f"{node['status'].upper()} " if node.get("status") and node["node_type"] == "action_item" else ""
        suffix = ""
        if detail:
            suffix = f"  (id: {node['id']}, line: {node['location'].get('line_start')})"
        lines.append(f"{indent}[{label}] {status}{node['title']}{suffix}".rstrip())
        for child in node.get("children", []):
            self._render_node(lines, child, depth + 1, detail=detail)

    def _objects_by_source(self) -> Dict[str, Dict[str, Any]]:
        rows = self.conn.execute("SELECT * FROM objects").fetchall()
        return {row["source_item_id"]: dict(row) for row in rows}

    def _block_source_id(self, block: LogseqBlock) -> str:
        if block.uuid:
            return f"block:{block.uuid}"
        rel = self._relative(block.file_path)
        return f"block:{rel}:{block.line_number}:{content_hash(block.raw)}"

    def _relative(self, path: Path) -> str:
        graph = self.settings.logseq_graph_path
        if graph:
            try:
                return str(path.relative_to(graph))
            except ValueError:
                pass
        return str(path)

    def _count_nodes(self, nodes: List[Dict[str, Any]]) -> int:
        return sum(1 + self._count_nodes(node.get("children", [])) for node in nodes)

    def _count_recognized(self, nodes: List[Dict[str, Any]]) -> int:
        return sum(
            (0 if node["node_type"] == "unknown" else 1) + self._count_recognized(node.get("children", []))
            for node in nodes
        )

    def _flatten(self, nodes: List[Dict[str, Any]], flat: List[Dict[str, Any]]) -> None:
        for node in nodes:
            flat.append(node)
            self._flatten(node.get("children", []), flat)


def project_tree_json(tree: Dict[str, Any]) -> str:
    return json.dumps(tree, ensure_ascii=False, indent=2, sort_keys=True)

