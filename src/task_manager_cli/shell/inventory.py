"""Context inventory: unified object listing for the Human Shell."""

from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

from task_manager_cli.adapters.logseq.extractors import strip_bullet
from task_manager_cli.projects.tree import ProjectTreeService
from task_manager_cli.storage.repositories import Repository

ROOTS = {"today", "dashboard", "inbox", "waiting", "someday", "ideas", "projects", "mini", "reviews", "proposals"}

DEFAULT_LIMIT = 20
MAX_LIMIT = 50


def build_inventory(conn, shell_context, repo: Repository, settings) -> dict:
    """Return structured inventory for the current virtual directory.

    Args:
        conn: SQLite connection.
        shell_context: ShellContext dataclass with path, project_ref, project_node_id, etc.
        repo: Repository instance.
        settings: Settings instance.

    Returns:
        dict with keys: context, project_ref, project_node_id, project_node_title,
        project_node_path, sections (list of {type, label, items}), overflow (dict).
    """
    path = shell_context.path if hasattr(shell_context, 'path') else str(shell_context.get('path', '/today'))

    current_object_id = _get_attr(shell_context, 'current_object_id')
    if current_object_id:
        return _inventory_object_context(repo, int(current_object_id), path)
    if path == "/" or path == "":
        return _inventory_root()
    elif path == "/projects":
        return _inventory_projects(repo)
    elif path == "/mini":
        return _inventory_mini_projects(repo)
    elif path.startswith("/projects/") and _get_attr(shell_context, 'project_ref'):
        return _inventory_project_context(conn, shell_context, repo, settings)
    elif path == "/today":
        return _inventory_today(repo, settings, _ctx_val(shell_context, "journal_date") or date.today().isoformat())
    elif path == "/dashboard":
        return _inventory_dashboard(repo)
    elif path == "/inbox":
        return _inventory_inbox(repo)
    elif path == "/waiting":
        return _inventory_waiting(repo)
    elif path == "/someday":
        return _inventory_by_tag(repo, "someday", "Someday Tasks")
    elif path == "/ideas":
        return _inventory_ideas(repo)
    elif path == "/reviews":
        return _inventory_reviews(repo)
    elif path == "/proposals":
        return _inventory_proposals(repo)
    else:
        return _empty_inventory(path)


# ─── entry helpers ────────────────────────────────────────────────────────────

def _get_attr(obj, name):
    """Get attribute from dataclass or dict-like object."""
    if hasattr(obj, name):
        return getattr(obj, name)
    if isinstance(obj, dict):
        return obj.get(name)
    return None


def _ctx_val(shell_context, name, default=None):
    return _get_attr(shell_context, name) if shell_context else default


def _empty_inventory(path: str, **extra) -> dict:
    return {"context": path, "project_ref": None, "project_node_id": None,
            "project_node_title": None, "project_node_path": None,
            "sections": [], "overflow": {}, **extra}


def _item(obj_id, obj_type, title, status=None, label=None, actionable=True,
          source_location="", object_id=None, attribution=None, **extra) -> dict:
    return {
        "id": obj_id, "object_id": object_id or obj_id, "type": obj_type,
        "status": status, "title": title or "", "label": label,
        "actionable": actionable, "source_location": source_location,
        "attribution": attribution, **extra,
    }


def _section(section_type: str, label: str, items: List[dict]) -> dict:
    return {"type": section_type, "label": label, "items": items}


def _source_location(row: dict) -> str:
    page = row.get("page_name") or row.get("journal_date") or ""
    line = row.get("line_start")
    if page and line:
        return f"{page}:{line}"
    return page or ""


# ─── root inventory ───────────────────────────────────────────────────────────

def _inventory_root() -> dict:
    roots = sorted(ROOTS)
    items = [_item(name, "root", name, actionable=False, source_location="") for name in roots]
    return {
        "context": "/",
        "project_ref": None, "project_node_id": None,
        "project_node_title": None, "project_node_path": None,
        "sections": [_section("roots", "Virtual Roots", items)],
        "overflow": {},
    }


# ─── projects inventory ──────────────────────────────────────────────────────

def _inventory_projects(repo: Repository) -> dict:
    rows = repo.list_objects("project", limit=MAX_LIMIT)
    items = []
    for row in rows:
        loc = _source_location(row)
        items.append(_item(
            row["id"], "project", row["title"],
            status=row.get("status"), label=None, actionable=True,
            source_location=loc,
        ))
    return {
        "context": "/projects",
        "project_ref": None, "project_node_id": None,
        "project_node_title": None, "project_node_path": None,
        "sections": [_section("projects", "Projects", items)],
        "overflow": {},
    }


# ─── mini projects inventory ──────────────────────────────────────────────────

def _inventory_mini_projects(repo: Repository) -> dict:
    rows = repo.list_objects("mini_project", limit=MAX_LIMIT)
    items = []
    for row in rows:
        loc = _source_location(row)
        items.append(_item(
            row["id"], "mini_project", row["title"],
            status=row.get("status"), label=None, actionable=True,
            source_location=loc,
        ))
    return {
        "context": "/mini",
        "project_ref": None, "project_node_id": None,
        "project_node_title": None, "project_node_path": None,
        "sections": [_section("mini_projects", "Mini Projects", items)],
        "overflow": {},
    }


# ─── ideas inventory ──────────────────────────────────────────────────────────

def _inventory_ideas(repo: Repository) -> dict:
    rows = repo.list_objects("idea", limit=MAX_LIMIT)
    items = [_item(r["id"], "idea", r["title"], source_location=_source_location(r))
             for r in rows]
    return {
        "context": "/ideas",
        "project_ref": None, "project_node_id": None,
        "project_node_title": None, "project_node_path": None,
        "sections": [_section("ideas", "Ideas", items)],
        "overflow": {},
    }


# ─── today / inbox / waiting / somedays ───────────────────────────────────────

def _inventory_today_legacy_global_view(repo: Repository) -> dict:
    tasks = repo.list_objects("task", status=None, limit=MAX_LIMIT)
    task_items = []
    for row in tasks:
        if row.get("status") in ("todo", "doing"):
            task_items.append(_item(
                row["id"], "task", row["title"],
                status=row.get("status"), source_location=_source_location(row),
            ))
    ideas = repo.list_objects("idea", limit=DEFAULT_LIMIT)
    idea_items = [_item(r["id"], "idea", r["title"], source_location=_source_location(r))
                  for r in ideas]
    projects = repo.list_objects("project", limit=DEFAULT_LIMIT)
    project_items = [_item(r["id"], "project", r["title"], actionable=False,
                           source_location=_source_location(r)) for r in projects]

    sections = []
    if task_items:
        sections.append(_section("actions", "Today's Tasks", task_items))
    if idea_items:
        sections.append(_section("ideas", "Ideas", idea_items))
    if project_items:
        sections.append(_section("projects", "Active Projects", project_items))
    return {
        "context": "/today",
        "project_ref": None, "project_node_id": None,
        "project_node_title": None, "project_node_path": None,
        "sections": sections, "overflow": {},
    }


def _inventory_inbox(repo: Repository) -> dict:
    ideas = repo.list_objects("idea", limit=MAX_LIMIT)
    unlinked = []
    for row in ideas:
        rels = repo.relations_for_object(row["id"])
        has_project = any(r.get("relation_type") == "belongs_to" for r in rels)
        if not has_project:
            unlinked.append(_item(
                row["id"], "idea", row["title"], source_location=_source_location(row),
            ))
    return {
        "context": "/inbox",
        "project_ref": None, "project_node_id": None,
        "project_node_title": None, "project_node_path": None,
        "sections": [_section("ideas", "Unlinked Ideas", unlinked)],
        "overflow": {},
    }


def _inventory_waiting(repo: Repository) -> dict:
    tasks = repo.list_objects("task", status=None, limit=MAX_LIMIT)
    items = []
    for row in tasks:
        if row.get("status") == "waiting":
            items.append(_item(
                row["id"], "task", row["title"],
                status="waiting", source_location=_source_location(row),
            ))
    return {
        "context": "/waiting",
        "project_ref": None, "project_node_id": None,
        "project_node_title": None, "project_node_path": None,
        "sections": [_section("actions", "Waiting", items)],
        "overflow": {},
    }


def _inventory_by_tag(repo: Repository, tag: str, label: str) -> dict:
    rows = repo.list_objects("task", limit=MAX_LIMIT)
    items = []
    for row in rows:
        try:
            records = repo.records_for_object(row["id"], limit=20)
        except Exception:
            records = []
        tagged = any(_tag_in_records(rec, tag) for rec in records)
        if tagged:
            items.append(_item(
                row["id"], "task", row["title"],
                status=row.get("status"), source_location=_source_location(row),
            ))
    return {
        "context": f"/{tag}",
        "project_ref": None, "project_node_id": None,
        "project_node_title": None, "project_node_path": None,
        "sections": [_section("actions", label, items)],
        "overflow": {},
    }


def _tag_in_records(record: dict, tag: str) -> bool:
    normalized = record.get("normalized_text") or record.get("raw_text") or ""
    meta = record.get("metadata")
    if isinstance(meta, dict):
        meta_str = str(meta)
    elif isinstance(meta, str):
        meta_str = meta
    else:
        meta_str = ""
    return f"#{tag}" in normalized or f"#{tag}" in meta_str


def _inventory_object_context(repo: Repository, object_id: int, path: str) -> dict:
    obj = repo.get_object(object_id)
    if not obj:
        return _empty_inventory(path)
    records = repo.records_for_object(object_id, limit=100)
    child_items = []
    result_items = []
    note_items = []
    for rec in records:
        if rec.get("role") == "definition":
            continue
        title = rec.get("normalized_text") or rec.get("raw_text") or ""
        item = _item(
            rec["id"],
            "record",
            title,
            label=rec.get("role"),
            actionable=False,
            source_location=_source_location(rec),
        )
        role = rec.get("role")
        if role in {"result_marker", "no_result_marker"}:
            result_items.append(item)
        elif role in {"user_annotation", "ai_annotation", "clarification_marker"}:
            note_items.append(item)
        else:
            child_items.append(item)
    sections = []
    if child_items:
        sections.append(_section("children", "Child Blocks", child_items))
    if note_items:
        sections.append(_section("notes", "Notes", note_items))
    if result_items:
        sections.append(_section("results", "Results", result_items))
    return {
        "context": path,
        "project_ref": None,
        "project_node_id": None,
        "project_node_title": None,
        "project_node_path": [],
        "sections": sections,
        "overflow": {},
        "_project_title": f"#{obj['id']} {obj['object_type']} {obj['title']}",
    }


# ─── reviews / proposals ──────────────────────────────────────────────────────

def _inventory_reviews(repo: Repository) -> dict:
    try:
        rows = repo.list_sync_runs(limit=MAX_LIMIT)
    except Exception:
        rows = []
    items = [_item(r["id"], "review", f"Review #{r['id']}", actionable=False,
                   source_location="") for r in rows]
    return {
        "context": "/reviews",
        "project_ref": None, "project_node_id": None,
        "project_node_title": None, "project_node_path": None,
        "sections": [_section("reviews", "Reviews", items)],
        "overflow": {},
    }


def _inventory_proposals(repo: Repository) -> dict:
    return {
        "context": "/proposals",
        "project_ref": None, "project_node_id": None,
        "project_node_title": None, "project_node_path": None,
        "sections": [_section("proposals", "Proposals — run `proposals` to see pending", [])],
        "overflow": {},
    }


# ─── project context inventory (core) ─────────────────────────────────────────

def _inventory_project_context(conn, shell_context, repo: Repository, settings) -> dict:
    project_ref = _ctx_val(shell_context, 'project_ref')
    project_node_id = _ctx_val(shell_context, 'project_node_id')
    project_node_title = _ctx_val(shell_context, 'project_node_title')
    path = _ctx_val(shell_context, 'path', '/')

    if not project_ref:
        return _empty_inventory(path)

    project_id = repo.resolve_object_id(project_ref)
    if not project_id:
        return _empty_inventory(path)

    project_obj = repo.get_object(project_id)
    project_title = project_obj["title"] if project_obj else project_ref

    tree_service = ProjectTreeService(conn, settings)
    try:
        tree = tree_service.build(project_ref, detail=False)
    except Exception:
        tree = {"tree": [], "summary": {}}

    sections = []

    # Nodes
    flat_nodes = _flatten_tree_nodes(tree.get("tree", []))
    if flat_nodes:
        sections.append(_section("nodes", "Nodes", flat_nodes))

    # Determine if we're in a node context
    if project_node_id and flat_nodes:
        node_info = _find_node_info(flat_nodes, project_node_id)
        if node_info:
            attribution_note = _build_attribution_note(node_info, repo, conn, project_id)
            sections = _add_attributed_objects(
                sections, conn, repo, project_id, node_info, flat_nodes, settings,
            )
            if attribution_note:
                sections.append(_section("_note", "", []))
                # We'll attach the note in the output formatting
            return {
                "context": path,
                "project_ref": project_ref,
                "project_node_id": project_node_id,
                "project_node_title": project_title,
                "project_node_path": node_info.get("block_path", []),
                "sections": sections,
                "overflow": {},
                "_attribution_note": attribution_note,
                "_project_title": project_title,
            }

    # Project-level: get all child objects
    project_children = _get_project_children(conn, repo, project_id)
    inbox_children = [item for item in project_children if _is_project_inbox_child(item)]
    unplaced_children = [item for item in project_children if _is_project_unplaced_child(item)]
    if inbox_children:
        sections.append(_section("inbox", "Project Inbox", [_child_item(row) for row in inbox_children]))
    if unplaced_children:
        sections.append(_section("unplaced", "Unplaced Items", [_child_item(row) for row in unplaced_children]))
    _add_child_sections(sections, project_children, repo)

    return {
        "context": path,
        "project_ref": project_ref,
        "project_node_id": project_node_id,
        "project_node_title": project_title,
        "project_node_path": [],
        "sections": sections,
        "overflow": {},
        "_project_title": project_title,
    }


def _flatten_tree_nodes(nodes: List[dict], path: Optional[List[str]] = None) -> List[dict]:
    """Flatten project tree nodes into a list of inventory items."""
    if path is None:
        path = []
    result = []
    for node in nodes:
        node_title = node.get("title", "")
        node_id = node.get("id", "")
        node_type = node.get("node_type", "unknown")
        label = node.get("marker") or node_type
        loc = node.get("location", {})
        src = f"{loc.get('page_name', '')}:{loc.get('line_start', '')}" if loc else ""
        children = node.get("children", [])
        this_path = path + [node_title]
        result.append(_item(
            node_id, "node", node_title, label=label, actionable=False,
            source_location=src, node_id=node_id, block_path=this_path,
            line_start=loc.get("line_start"), depth=node.get("depth", 0),
            line_end=loc.get("line_end"),
            children=[c.get("id") for c in children],
        ))
        result.extend(_flatten_tree_nodes(children, this_path))
    return result


def _find_node_info(flat_nodes: List[dict], node_id: str) -> Optional[dict]:
    for n in flat_nodes:
        if n.get("node_id") == node_id:
            return n
    return None


def _build_attribution_note(node_info, repo, conn, project_id) -> Optional[str]:
    """Check if node has directly attributed objects; if not, note fallback."""
    return None  # attribution notes are generated during section building


def _add_attributed_objects(sections, conn, repo, project_id, node_info, flat_nodes, settings):
    """Add object sections attributed to a specific node, with fallback handling."""
    node_id = node_info.get("node_id", "")
    node_line_start = node_info.get("line_start")
    node_depth = node_info.get("depth", 0)

    children = _get_project_children(conn, repo, project_id)

    attributed = {att: [] for att in ["relation", "source_path", "wiki_link", "fallback"]}
    for child in children:
        att = _object_attribution(child, node_info, children, repo)
        attributed.setdefault(att, []).append(child)

    relation_count = len(attributed.get("relation", []))
    source_count = len(attributed.get("source_path", []))
    wiki_count = len(attributed.get("wiki_link", []))
    fallback_count = len(attributed.get("fallback", []))

    # Combine relation + source_path + wiki_link as direct
    direct = attributed.get("relation", []) + attributed.get("source_path", []) + attributed.get("wiki_link", [])
    fallback = attributed.get("fallback", [])

    if direct:
        _add_child_sections(sections, direct, repo)
    elif fallback:
        # All fallback: add note
        sections.append(_section("_fallback_note", "", []))
        _add_child_sections(sections, fallback, repo)
    else:
        sections.append(_section("_note", "", []))

    return sections


def _object_attribution(obj: dict, node_info: dict, all_children: List[dict], repo) -> str:
    """Determine how an object is attributed to a node.

    Priority: relation > source_path > wiki_link > fallback.
    """
    node_id = node_info.get("node_id", "")
    node_line_start = node_info.get("line_start")
    obj_id = obj.get("object_id") or obj.get("id")

    # 1. Check relations
    if _has_relation_to(obj, node_id, repo):
        return "relation"

    # 2. Check source/block path: obj's definition record line_start within node subtree
    if node_line_start is not None:
        def_rec = obj.get("_definition_record") or repo.definition_record_for_object(obj["id"])
        if def_rec:
            rec_line = def_rec.get("line_start")
            if rec_line is not None:
                subtree_end = _node_subtree_end(node_info, all_children)
                if node_line_start <= rec_line <= subtree_end:
                    return "source_path"

    # 3. Check wiki/project link
    meta = obj.get("metadata")
    if isinstance(meta, dict):
        page_refs = meta.get("page_refs", [])
        block_refs = meta.get("block_refs", [])
        node_title = node_info.get("title", "")
        if node_title and (node_title in str(page_refs) or node_title in str(block_refs)):
            return "wiki_link"

    # 4. Fallback
    return "fallback"


def _has_relation_to(obj: dict, node_id: str, repo) -> bool:
    """Check if object has a belongs_to relation to the given node."""
    obj_id = obj.get("id")
    if not obj_id:
        return False
    try:
        rels = repo.relations_for_object(obj_id)
    except Exception:
        return False
    for rel in rels:
        if rel.get("relation_type") == "belongs_to":
            to_id = rel.get("to_id")
            if to_id and str(to_id) == str(node_id):
                return True
            to_source = rel.get("to_source_item_id") or ""
            if to_source and str(to_source) == str(node_id):
                return True
    return False


def _node_subtree_end(node_info: dict, flat_nodes: List[dict]) -> int:
    """Estimate the line where a node's subtree ends."""
    line_start = node_info.get("line_start", 0)
    if not line_start:
        return line_start
    line_end = node_info.get("line_end")
    if line_end:
        return int(line_end)

    node_depth = node_info.get("depth", 0)
    node_id = node_info.get("node_id", "")
    reached_self = False
    end = line_start

    for n in flat_nodes:
        n_id = n.get("node_id", "")
        if n_id == node_id:
            reached_self = True
            continue
        if reached_self:
            n_depth = n.get("depth", 0)
            n_line = n.get("line_start", 0)
            if n_line and n_depth <= node_depth:
                break
            if n_line:
                end = max(end, n_line)
    return end


def _get_project_children(conn, repo: Repository, project_id: int) -> List[dict]:
    """Get objects visible in a project via relation, page location, or journal link."""
    project = repo.get_object(project_id)
    project_file = project.get("file_path") if project else None
    project_title = project.get("title") if project else None
    children_by_id: Dict[int, dict] = {}
    for obj_type in ("task", "idea", "mini_project", "reference", "resource"):
        try:
            rows = repo.list_objects(obj_type, limit=MAX_LIMIT)
        except Exception:
            continue
        for row in rows:
            obj_id = row["id"]
            attribution = None
            try:
                rels = repo.relations_for_object(obj_id)
            except Exception:
                rels = []
            belongs = any(
                r.get("relation_type") == "belongs_to" and (
                    str(r.get("to_id")) == str(project_id) or
                    str(r.get("to_object_id")) == str(project_id)
                )
                for r in rels
            )
            if belongs:
                linked_rule = any(
                    r.get("relation_type") == "belongs_to"
                    and isinstance(r.get("metadata"), dict)
                    and str(r.get("metadata", {}).get("rule", "")).endswith("page_ref")
                    for r in rels
                )
                attribution = "journal-link" if linked_rule and row.get("journal_date") else "relation"
            elif project_file and row.get("file_path") == project_file:
                attribution = "page"
            elif project_title and _object_links_project(row, project_title, repo):
                attribution = "journal-link"
            if attribution and obj_id not in children_by_id:
                copy = dict(row)
                copy["_attribution"] = attribution
                children_by_id[obj_id] = copy
    return list(children_by_id.values())


def _object_links_project(row: dict, project_title: str, repo: Repository) -> bool:
    meta = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    refs = meta.get("page_refs") or []
    if project_title in refs:
        return True
    try:
        records = repo.records_for_object(row["id"], limit=20)
    except Exception:
        return False
    needles = {project_title, project_title.removeprefix("项目-")}
    for rec in records:
        text = rec.get("raw_text") or rec.get("normalized_text") or ""
        if any(f"[[{needle}]]" in text for needle in needles if needle):
            return True
    return False


def _add_child_sections(sections: List[dict], children: List[dict], repo: Repository):
    """Add action, idea, resource, mini_project sections from children."""
    actions = []
    ideas = []
    resources = []
    minis = []

    for row in children:
        obj_type = row.get("object_type", "task")
        loc = _source_location(row)
        item = _item(
            row["id"], obj_type, row["title"],
            status=row.get("status"), source_location=loc,
            attribution=row.get("_attribution"),
        )
        if obj_type == "task":
            actions.append(item)
        elif obj_type == "idea":
            ideas.append(item)
        elif obj_type in ("reference", "resource"):
            resources.append(item)
        elif obj_type == "mini_project":
            minis.append(item)

    if actions:
        sections.append(_section("actions", "Open Actions", actions))
    if ideas:
        sections.append(_section("ideas", "Ideas", ideas))
    if resources:
        sections.append(_section("resources", "Resources", resources))
    if minis:
        sections.append(_section("mini_projects", "Mini Projects", minis))


def _child_item(row: dict) -> dict:
    return _item(
        row["id"],
        row.get("object_type", "task"),
        row["title"],
        status=row.get("status"),
        source_location=_source_location(row),
        attribution=row.get("_attribution"),
    )


def _is_project_inbox_child(row: dict) -> bool:
    meta = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    return meta.get("placement_status") == "unplaced" or _has_section_marker(meta.get("section_markers") or [], {"项目收件箱", "待澄清"}) or row.get("_attribution") == "page"


def _is_project_unplaced_child(row: dict) -> bool:
    meta = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    markers = meta.get("section_markers") or []
    if meta.get("placement_status") in {"unplaced", "project_level", "needs_node"}:
        return True
    if _has_section_marker(markers, {"目标", "里程碑", "工作流", "具体事务", "小任务", "资源", "成果", "想法", "反思", "无成果"}):
        return False
    return _has_section_marker(markers, {"项目收件箱", "待澄清"}) or row.get("_attribution") == "page"


def _has_section_marker(section_markers: List[str], marker_names: set) -> bool:
    return any(any(f"[{name}]" in marker or name == marker for name in marker_names) for marker in section_markers)


# ─── today / dashboard v2 overrides ───────────────────────────────────────────

def _inventory_today(repo: Repository, settings, journal_date: str) -> dict:
    journal_items = _journal_record_items(repo, journal_date)
    task_items = _objects_on_journal(repo, journal_date, "task")
    idea_items = _objects_on_journal(repo, journal_date, "idea")
    exposed_items = _journal_exposed_items(repo, journal_date)
    result_items = _journal_marker_items(repo, journal_date, "成果", "result")
    note_items = _journal_marker_items(repo, journal_date, "注", "record")

    sections = []
    if journal_items:
        sections.append(_section("journal", f"Journal {journal_date}", journal_items))
    if task_items:
        sections.append(_section("actions", "Tasks Today", task_items))
    if exposed_items:
        sections.append(_section("exposed", "Exposed Today", exposed_items))
    if idea_items:
        sections.append(_section("ideas", "Ideas Today", idea_items))
    if result_items:
        sections.append(_section("results", "Results Today", result_items))
    if note_items:
        sections.append(_section("notes", "Notes Today", note_items))

    extra = {}
    if not journal_items:
        extra["_note"] = f"Today journal not found or empty: {_journal_path(settings, journal_date)}"
    return {
        "context": "/today",
        "project_ref": None, "project_node_id": None, "project_node_title": None, "project_node_path": None,
        "sections": sections, "overflow": {},
        **extra,
    }


def _inventory_dashboard(repo: Repository) -> dict:
    tasks = repo.list_objects("task", status=None, limit=MAX_LIMIT)
    active_items = []
    waiting_items = []
    for row in tasks:
        if row.get("status") in ("todo", "doing"):
            active_items.append(_item(row["id"], "task", row["title"], status=row.get("status"), source_location=_source_location(row)))
        elif row.get("status") == "waiting":
            waiting_items.append(_item(row["id"], "task", row["title"], status="waiting", source_location=_source_location(row)))
    projects = repo.list_objects("project", limit=DEFAULT_LIMIT)
    project_items = [_item(r["id"], "project", r["title"], actionable=False, source_location=_source_location(r)) for r in projects]
    ideas = repo.list_objects("idea", limit=DEFAULT_LIMIT)
    idea_items = [_item(r["id"], "idea", r["title"], source_location=_source_location(r)) for r in ideas]
    proposal_items = _proposal_items(repo, statuses=("suggested", "accepted", "edited"))
    review_items = _open_review_items(repo)
    project_health_items = _dashboard_project_health_items(repo, projects)
    unplaced_items = _dashboard_unplaced_items(repo)

    sections = []
    if project_health_items:
        sections.append(_section("quality", "Projects Needing Attention", project_health_items))
    if unplaced_items:
        sections.append(_section("unplaced", "Unplaced Items", unplaced_items))
    if project_items:
        sections.append(_section("projects", "Active Projects", project_items))
    if active_items:
        sections.append(_section("actions", "Active Tasks", active_items))
    if waiting_items:
        sections.append(_section("waiting", "Waiting", waiting_items))
    if proposal_items:
        sections.append(_section("proposals", "Pending Proposals", proposal_items))
    if review_items:
        sections.append(_section("reviews", "Open Reviews", review_items))
    if idea_items:
        sections.append(_section("ideas", "Ideas", idea_items))
    return {
        "context": "/dashboard",
        "project_ref": None, "project_node_id": None, "project_node_title": None, "project_node_path": None,
        "sections": sections, "overflow": {},
    }


def _journal_path(settings, journal_date: str) -> Optional[Path]:
    graph = getattr(settings, "logseq_graph_path", None)
    if not graph:
        return None
    return Path(graph) / "journals" / f"{journal_date.replace('-', '_')}.md"


def _journal_record_items(repo: Repository, journal_date: str) -> List[dict]:
    rows = repo.conn.execute(
        """
        SELECT r.id, r.raw_text, r.normalized_text, l.page_name, l.journal_date, l.line_start
        FROM source_records r
        JOIN locations l ON l.id=r.location_id
        WHERE l.journal_date=? AND r.record_type='block'
        ORDER BY l.line_start, r.id
        LIMIT ?
        """,
        (journal_date, MAX_LIMIT),
    ).fetchall()
    return [
        _item(row["id"], "record", strip_bullet(row["raw_text"]), source_location=_source_location(dict(row)), actionable=False)
        for row in rows
    ]


def _objects_on_journal(repo: Repository, journal_date: str, object_type: str) -> List[dict]:
    rows = repo.conn.execute(
        """
        SELECT o.*, l.file_path, l.page_name, l.journal_date, l.block_uuid, l.line_start
        FROM objects o
        LEFT JOIN locations l ON l.id=o.canonical_location_id
        WHERE o.object_type=? AND l.journal_date=?
        ORDER BY l.line_start, o.id
        LIMIT ?
        """,
        (object_type, journal_date, MAX_LIMIT),
    ).fetchall()
    return [
        _item(row["id"], object_type, row["title"], status=row["status"], source_location=_source_location(dict(row)))
        for row in rows
    ]


def _journal_exposed_items(repo: Repository, journal_date: str) -> List[dict]:
    rows = repo.conn.execute(
        """
        SELECT DISTINCT o.*, l.file_path, l.page_name, l.journal_date, l.line_start
        FROM object_record_links orl
        JOIN objects o ON o.id=orl.object_id
        LEFT JOIN locations l ON l.id=o.canonical_location_id
        JOIN source_records r ON r.id=orl.record_id
        JOIN locations rl ON rl.id=r.location_id
        WHERE orl.role='journal_exposure' AND rl.journal_date=?
        ORDER BY o.id DESC
        LIMIT ?
        """,
        (journal_date, MAX_LIMIT),
    ).fetchall()
    return [
        _item(row["id"], row["object_type"], row["title"], status=row["status"], source_location=_source_location(dict(row)), attribution="journal-ref")
        for row in rows
    ]


def _journal_marker_items(repo: Repository, journal_date: str, marker: str, item_type: str) -> List[dict]:
    rows = repo.conn.execute(
        """
        SELECT r.id, r.raw_text, r.normalized_text, l.page_name, l.journal_date, l.line_start
        FROM source_records r
        JOIN locations l ON l.id=r.location_id
        WHERE l.journal_date=? AND r.metadata_json LIKE ?
        ORDER BY l.line_start, r.id
        LIMIT ?
        """,
        (journal_date, f'%"semantic_marker": "{marker}"%', MAX_LIMIT),
    ).fetchall()
    return [
        _item(row["id"], item_type, strip_bullet(row["raw_text"]), source_location=_source_location(dict(row)), actionable=False)
        for row in rows
    ]


def _proposal_items(repo: Repository, statuses: tuple) -> List[dict]:
    placeholders = ",".join("?" for _ in statuses)
    rows = repo.conn.execute(
        f"SELECT * FROM proposals WHERE status IN ({placeholders}) ORDER BY id DESC LIMIT ?",
        (*statuses, MAX_LIMIT),
    ).fetchall()
    return [
        _item(row["id"], "proposal", row["title"], actionable=False, proposal_id=row["id"], proposal_type=row["proposal_type"], risk=row["risk"])
        for row in rows
    ]


def _open_review_items(repo: Repository) -> List[dict]:
    try:
        rows = repo.conn.execute(
            "SELECT * FROM review_sessions WHERE status IN ('open', 'in_progress', 'paused') ORDER BY id DESC LIMIT ?",
            (MAX_LIMIT,),
        ).fetchall()
    except Exception:
        rows = []
    return [_item(row["id"], "review", row["title"] or f"Review #{row['id']}", actionable=False) for row in rows]


def _dashboard_project_health_items(repo: Repository, projects: List[dict]) -> List[dict]:
    items = []
    for project in projects:
        unplaced = len([row for row in _project_children_for_dashboard(repo, project) if _is_project_unplaced_child(row)])
        pending = repo.conn.execute(
            """
            SELECT COUNT(*) AS c FROM proposals
            WHERE status IN ('suggested', 'accepted', 'edited')
              AND (target_object_id=? OR payload_json LIKE ?)
            """,
            (project["id"], f'%"target_project_id": {project["id"]}%'),
        ).fetchone()["c"]
        if unplaced or int(pending):
            items.append(_item(project["id"], "project", f"{project['title']} unplaced={unplaced} proposals={int(pending)}", source_location=_source_location(project)))
    return items


def _dashboard_unplaced_items(repo: Repository) -> List[dict]:
    items = []
    for project in repo.list_objects("project", limit=MAX_LIMIT):
        for row in _project_children_for_dashboard(repo, project):
            if _is_project_unplaced_child(row):
                items.append(_child_item(row))
    return items[:MAX_LIMIT]


def _project_children_for_dashboard(repo: Repository, project: dict) -> List[dict]:
    return _get_project_children(repo.conn, repo, int(project["id"]))
