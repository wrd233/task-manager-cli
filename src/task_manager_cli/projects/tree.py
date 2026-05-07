import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from task_manager_cli.adapters.logseq.extractors import (
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
    "价值层": "value_layer",
    "目标层": "goal_layer",
    "里程碑": "milestone",
    "工作流": "workflow",
    "小任务": "mini_project",
    "具体事务": "specific_work",
    "资源": "resource",
    "项目收件箱": "project_inbox",
    "成果": "result",
    "无成果": "no_result",
    "想法": "idea",
    "反思": "reflection",
    "注": "user_annotation",
    "AI注": "ai_annotation",
    "待澄清": "needs_clarify",
}

LABEL_BY_NODE_TYPE = {
    "objective": "目标",
    "value_layer": "价值层",
    "goal_layer": "目标层",
    "milestone": "里程碑",
    "workflow": "工作流",
    "mini_project": "小任务",
    "specific_work": "具体事务",
    "resource": "资源",
    "project_inbox": "项目收件箱",
    "result": "成果",
    "no_result": "无成果",
    "idea": "想法",
    "reflection": "反思",
    "user_annotation": "注",
    "ai_annotation": "AI注",
    "needs_clarify": "待澄清",
    "action_item": "行动",
}


STATUS_COLOR = {
    "todo": "33",
    "doing": "36",
    "waiting": "35",
    "done": "32",
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
        roots: List[Dict[str, Any]] = []
        raw_block_count = 0
        for block in parsed.blocks:
            if block.properties.get("__property_block__") == "true":
                continue
            raw_block_count += 1
            if block.parent is None:
                roots.extend(self._semantic_nodes(block, source_map, detail=detail))
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
                "recognized_node_count": self._count_nodes(roots),
                "raw_block_count": raw_block_count,
                "filtered_raw_block_count": max(raw_block_count - self._count_nodes(roots), 0),
                "has_structured_markers": bool(roots),
                "readonly": True,
                "semantic_only": True,
            },
        }

    def render_markdown(
        self,
        tree: Dict[str, Any],
        detail: bool = False,
        *,
        color: Optional[bool] = None,
        root_node_id: Optional[str] = None,
    ) -> str:
        project = tree["project"]
        lines = [f"# 项目树：{project['title']}", ""]
        summary = tree.get("summary", {})
        nodes = tree.get("tree", [])
        if root_node_id:
            root = self.find_node(nodes, root_node_id)
            nodes = root.get("children", []) if root else []
            if not nodes:
                lines.append("该节点下没有可识别的结构化子节点。可使用 show 查看完整 Logseq 子树。")
                return "\n".join(lines)
        if not nodes:
            lines.append("未找到可展示的结构化项目节点。可使用 show 查看完整 Logseq 子树。")
            return "\n".join(lines)
        for index, node in enumerate(nodes):
            if index > 0:
                lines.append("")
            self._render_node(lines, node, depth=0, detail=detail, color=self._use_color(color))
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
        node_type = NODE_TYPE_BY_MARKER[marker] if marker in NODE_TYPE_BY_MARKER else "unknown"
        title = self._title(block, marker)
        obj = source_map.get(source_item_id)
        status = obj.get("status") if obj else None
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
            "semantic_depth": 0,
            "object_id": obj.get("id") if obj else None,
            "object_type": obj.get("object_type") if obj else None,
            "status": status,
            "location": {
                "source_type": "logseq",
                "source_item_id": source_item_id,
                "file_path": str(block.file_path) if detail else None,
                "page_name": block.page_name,
                "line_start": block.line_number,
                "line_end": self._subtree_end_line(block),
                "block_uuid": block.uuid,
                "block_path": block.block_path(),
            },
            "metadata": metadata,
            "children": [],
        }

    def _semantic_nodes(self, block: LogseqBlock, source_map: Dict[str, Dict[str, Any]], detail: bool = False) -> List[Dict[str, Any]]:
        if block.properties.get("__property_block__") == "true":
            return []
        marker = semantic_marker(block.raw)
        children: List[Dict[str, Any]] = []
        for child in block.children:
            children.extend(self._semantic_nodes(child, source_map, detail=detail))
        if marker not in NODE_TYPE_BY_MARKER:
            return children
        node = self._node(block, source_map, detail=detail)
        node["children"] = children
        for child in children:
            child["semantic_depth"] = node.get("semantic_depth", 0) + 1
        return [node]

    def _title(self, block: LogseqBlock, marker: Optional[str]) -> str:
        if block.task:
            return block.task[1]
        if marker:
            content = semantic_marker_content(block.raw)
            return content or normalize_text(block.text.replace("**", ""))
        return block.normalized_text

    def _render_node(self, lines: List[str], node: Dict[str, Any], depth: int, detail: bool, color: bool) -> None:
        indent = "  " * depth
        label = LABEL_BY_NODE_TYPE.get(node["node_type"], node["node_type"])
        label_text = f"[{label}]"
        if color:
            label_text = f"\033[1;33m{label_text}\033[0m"
        status = ""
        if node.get("status") and node["status"].lower() in STATUS_COLOR:
            status = node["status"].upper()
            if color:
                status = f"\033[{STATUS_COLOR[node['status'].lower()]}m{status}\033[0m"
            status = f"{status} "
        title = self._truncate(node["title"])
        suffix = ""
        if detail:
            loc = node.get("location", {})
            suffix = (
                f"  (id: {node['id']}, type: {node['node_type']}, "
                f"line: {loc.get('line_start')}, children: {len(node.get('children', []))})"
            )
        lines.append(f"{indent}{label_text} {status}{title}{suffix}".rstrip())
        for child in node.get("children", []):
            self._render_node(lines, child, depth + 1, detail=detail, color=color)

    def render_raw_subtree(
        self,
        block: LogseqBlock,
        *,
        detail: bool = False,
        color: Optional[bool] = None,
        max_title: int = 160,
    ) -> str:
        lines: List[str] = []
        base_indent = block.indent
        self._render_raw_block(lines, block, base_indent=base_indent, detail=detail, color=self._use_color(color), max_title=max_title)
        return "\n".join(lines)

    def render_block_context(self, block: LogseqBlock, *, max_ancestors: int = 6, color: Optional[bool] = None) -> str:
        ancestors = block.ancestors()[-max_ancestors:]
        if not ancestors:
            return "(root)"
        lines = []
        for depth, ancestor in enumerate(ancestors):
            marker = semantic_marker(ancestor.raw)
            title = self._title(ancestor, marker)
            prefix = f"[{marker}] " if marker else ""
            label = prefix
            if marker and self._use_color(color):
                label = f"\033[1;33m[{marker}]\033[0m "
            lines.append(f"{'  ' * depth}{label}{self._truncate(title, 120)}")
        return "\n".join(lines)

    def find_block(self, project_ref: str, source_item_id: str) -> Optional[LogseqBlock]:
        project = self._project(project_ref)
        parsed = parse_logseq_file(Path(project["file_path"]), project.get("title") or project.get("page_name"))
        for block in parsed.blocks:
            if self._block_source_id(block) == source_item_id:
                return block
        return None

    def find_block_for_object(self, obj: Dict[str, Any]) -> Optional[LogseqBlock]:
        file_path = obj.get("file_path")
        if not file_path or not Path(file_path).exists():
            return None
        parsed = parse_logseq_file(Path(file_path), obj.get("page_name"))
        block_uuid = obj.get("block_uuid")
        line_start = obj.get("line_start")
        for block in parsed.blocks:
            if block_uuid and block.uuid == block_uuid:
                return block
            if line_start and block.line_number == line_start:
                return block
        return None

    def find_node(self, nodes: List[Dict[str, Any]], node_id: str) -> Optional[Dict[str, Any]]:
        for node in nodes:
            if node.get("id") == node_id:
                return node
            found = self.find_node(node.get("children", []), node_id)
            if found:
                return found
        return None

    def raw_subtree_for_node(self, project_ref: str, node_id: str, *, detail: bool = False, color: Optional[bool] = None) -> Optional[str]:
        block = self.find_block(project_ref, node_id)
        if not block:
            return None
        return self.render_raw_subtree(block, detail=detail, color=color)

    def _render_raw_block(self, lines: List[str], block: LogseqBlock, *, base_indent: int, detail: bool, color: bool, max_title: int) -> None:
        if block.properties.get("__property_block__") == "true":
            return
        depth = max(block.indent - base_indent, 0)
        text = self._truncate(block.text, max_title)
        marker = semantic_marker(block.raw)
        if marker and color:
            text = text.replace(f"[{marker}]", f"\033[1;33m[{marker}]\033[0m", 1)
        suffix = f"  (line: {block.line_number})" if detail else ""
        lines.append(f"{'  ' * depth}{text}{suffix}")
        for key, value in block.properties.items():
            if key == "__property_block__":
                continue
            prop_suffix = f"  (line: {block.line_number})" if detail else ""
            lines.append(f"{'  ' * (depth + 1)}{key}:: {value}{prop_suffix}")
        for child in block.children:
            self._render_raw_block(lines, child, base_indent=base_indent, detail=detail, color=color, max_title=max_title)

    def _objects_by_source(self) -> Dict[str, Dict[str, Any]]:
        rows = self.conn.execute("SELECT * FROM objects").fetchall()
        return {row["source_item_id"]: dict(row) for row in rows}

    def _block_source_id(self, block: LogseqBlock) -> str:
        if block.uuid:
            return f"block:{block.uuid}"
        rel = self._relative(block.file_path)
        return f"block:{rel}:{block.line_number}"

    def _relative(self, path: Path) -> str:
        graph = self.settings.logseq_graph_path
        if graph:
            try:
                return str(path.relative_to(graph))
            except ValueError:
                pass
        return str(path)

    def _project(self, project_ref: str) -> Dict[str, Any]:
        project_id = self.repo.resolve_object_id(project_ref)
        if project_id is None:
            raise NotFoundError(f"Project not found: {project_ref}")
        project = self.repo.get_object(project_id)
        if not project or project.get("object_type") != ObjectType.PROJECT.value:
            raise TaskManagerError(f"Object is not a project: {project_ref}")
        if not project.get("file_path"):
            raise ConfigError("Project tree requires a Logseq project page file.")
        return project

    def _subtree_end_line(self, block: LogseqBlock) -> int:
        descendants = block.descendants()
        if not descendants:
            return block.line_number
        return max(item.line_number for item in descendants)

    def _truncate(self, text: str, max_chars: int = 140) -> str:
        if len(text) <= max_chars:
            return text
        return text[: max_chars - 1].rstrip() + "…"

    def _use_color(self, color: Optional[bool]) -> bool:
        if color is not None:
            return color
        if os.environ.get("NO_COLOR"):
            return False
        return sys.stdout.isatty()

    def _count_nodes(self, nodes: List[Dict[str, Any]]) -> int:
        return sum(1 + self._count_nodes(node.get("children", [])) for node in nodes)

    def _flatten(self, nodes: List[Dict[str, Any]], flat: List[Dict[str, Any]]) -> None:
        for node in nodes:
            flat.append(node)
            self._flatten(node.get("children", []), flat)


def project_tree_json(tree: Dict[str, Any]) -> str:
    return json.dumps(tree, ensure_ascii=False, indent=2, sort_keys=True)
