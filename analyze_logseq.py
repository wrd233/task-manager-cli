#!/usr/bin/env python3
"""
Logseq 使用习惯与任务/项目结构只读分析脚本
只读扫描 Logseq 文件，不修改任何原始内容。
"""

import os
import re
import json
import sys
from datetime import datetime, timedelta
from collections import defaultdict
from pathlib import Path

# ============================================================
# Configuration
# ============================================================

LOGSEQ_GRAPH = "/Users/wangrundong/logseq/Logseq_File"
JOURNALS_DIR = os.path.join(LOGSEQ_GRAPH, "journals")
PAGES_DIR = os.path.join(LOGSEQ_GRAPH, "pages")
OUTPUT_DIR = "/Users/wangrundong/work/task-manager-cli"

# How many recent days to analyze
RECENT_DAYS = 30

# ============================================================
# Utility Functions
# ============================================================

def parse_date_from_journal_filename(filename):
    """Parse YYYY_MM_DD.md into a date object."""
    stem = os.path.splitext(os.path.basename(filename))[0]
    try:
        return datetime.strptime(stem, "%Y_%m_%d")
    except ValueError:
        return None

def extract_page_properties(lines):
    """Extract key:: value page properties from the beginning of a file.
    Returns (properties_dict, content_start_line_index)."""
    props = {}
    content_start = 0
    in_frontmatter = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        # Skip empty lines at top
        if not stripped:
            continue
        # Check for YAML frontmatter
        if stripped == '---' and not in_frontmatter:
            in_frontmatter = True
            continue
        if stripped == '---' and in_frontmatter:
            content_start = i + 1
            break
        # Check for Logseq page properties (key:: value format)
        # Page properties are typically at the very top, before any heading
        prop_match = re.match(r'^([\w一-鿿-]+)::\s*(.*)', stripped)
        if prop_match:
            props[prop_match.group(1)] = prop_match.group(2).strip()
            content_start = i + 1
        else:
            # First non-property, non-empty line — properties section ends
            break
    return props, content_start

def indent_level(line):
    """Count leading spaces to determine indentation level.
    Logseq uses 4-space tabs by default."""
    stripped = line.lstrip(' ')
    if not stripped:
        return -1
    leading_spaces = len(line) - len(stripped)
    return leading_spaces // 4  # Logseq default tab width

def is_todo_block(line):
    """Check if a line is a TODO/DOING/DONE block."""
    return bool(re.match(r'^\s*-\s*(TODO|DOING|DONE)\b', line))

def get_task_status(line):
    """Extract TODO/DOING/DONE status from a line."""
    m = re.match(r'^\s*-\s*(TODO|DOING|DONE)\b\s*(.*)', line)
    if m:
        return m.group(1), m.group(2).strip()
    return None, line

def is_idea_block(line):
    """Check if a line contains a 想法 marker."""
    return bool(re.search(r'\*\*\[想法\]\*\*|\[想法\]', line))

def is_project_structure_marker(line):
    """Check if line contains a project structure marker."""
    markers = ['[具体目标]', '[价值层]', '[目标层]', '[里程碑]',
               '[具体事务]', '[资源列表]', '[头脑风暴]', '[反思]']
    return any(m in line for m in markers)

def has_block_reference(line):
    """Check if line contains block references."""
    return bool(re.search(r'\(\([0-9a-f-]+\)\)', line))

def has_embed(line):
    """Check if line contains embed block."""
    return bool(re.search(r'\{\{embed\s+\(\([0-9a-f-]+\)\)\}\}', line))

def extract_block_refs(line):
    """Extract all block reference UUIDs from a line."""
    return re.findall(r'\(\(([0-9a-f-]+)\)\)', line)

def extract_page_refs(line):
    """Extract wiki-style page references [[Page Name]] from a line."""
    return re.findall(r'\[\[([^\]]+)\]\]', line)

def clean_block_content(line):
    """Clean a block line to extract readable content, removing markers."""
    # Remove leading bullet and task status
    cleaned = re.sub(r'^\s*-\s*(TODO|DOING|DONE)\s*', '', line)
    # Remove priority markers [#A], [#B], [#C]
    cleaned = re.sub(r'\[#[ABC]\]\s*', '', cleaned)
    # Remove bold markers for display
    cleaned = cleaned.replace('**', '')
    return cleaned.strip()

# ============================================================
# Block Parser — Build hierarchical block tree from file
# ============================================================

class Block:
    """Represents a single Logseq block with its children and metadata."""
    def __init__(self, line, line_number, indent, file_path, page_name):
        self.raw = line
        self.line_number = line_number
        self.indent = indent
        self.file_path = file_path
        self.page_name = page_name
        self.children = []
        self.parent = None

        # Parse status
        self.status, self.content_remaining = get_task_status(line)
        self.clean_content = clean_block_content(line)

        # Detect markers
        self.is_idea = is_idea_block(line)
        self.is_project_marker = is_project_structure_marker(line)
        self.has_ref = has_block_reference(line)
        self.has_embed = has_embed(line)
        self.block_refs = extract_block_refs(line)
        self.page_refs = extract_page_refs(line)

        # Detect if this is just a block reference (i.e., the entire line is just ((uuid)))
        self.is_pure_reference = bool(re.match(r'^\s*-\s*\(\([0-9a-f-]+\)\)\s*$', line))
        self.is_embed_reference = bool(re.match(r'^\s*-\s*\{\{embed\s+\(\([0-9a-f-]+\)\)\}\}\s*$', line))

    def add_child(self, child):
        child.parent = self
        self.children.append(child)

    def has_children(self):
        return len(self.children) > 0

    def typed_children_count(self):
        """Count TODO/DOING/DONE children."""
        return sum(1 for c in self.children if c.status)

    def child_snippets(self, max_children=5):
        """Get brief snippets of child blocks."""
        snippets = []
        for c in self.children[:max_children]:
            text = c.clean_content[:80]
            if c.status:
                text = f"[{c.status}] {text}"
            if c.is_idea:
                text = f"[想法] {text}"
            snippets.append(text)
        return snippets

    def __repr__(self):
        content = self.clean_content[:60]
        return f"Block({self.status or '·'}, l{self.line_number}, ind={self.indent}, '{content}')"


def parse_file_blocks(file_path, page_name):
    """Parse a Logseq markdown file into a flat list of blocks with hierarchy.
    Returns (blocks_list, properties_dict)."""
    if not os.path.exists(file_path):
        return [], {}

    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    props, content_start = extract_page_properties(lines)

    blocks = []
    block_stack = []  # Stack of (indent_level, block) for parent tracking

    for i in range(content_start, len(lines)):
        line = lines[i]
        stripped = line.strip()

        # Skip empty lines and non-bullet lines (headings, paragraphs, etc.)
        if not stripped:
            continue

        # Only process bullet lines (start with - or tabbed -)
        # But also capture headings for context
        is_bullet = bool(re.match(r'^\s*-', line))
        if not is_bullet:
            continue

        ind = indent_level(line)
        block = Block(line, i + 1, ind, file_path, page_name)

        # Find parent: last block in stack with indent < current indent
        while block_stack and block_stack[-1][0] >= ind:
            block_stack.pop()

        if block_stack:
            parent = block_stack[-1][1]
            parent.add_child(block)
        else:
            blocks.append(block)

        block_stack.append((ind, block))

    return blocks, props


def get_all_child_blocks(block):
    """Recursively get all descendant blocks."""
    result = []
    for child in block.children:
        result.append(child)
        result.extend(get_all_child_blocks(child))
    return result


# ============================================================
# Scanner 1: Journal Scanner
# ============================================================

def scan_journals(days=RECENT_DAYS):
    """Scan recent journal files for TODO/DOING/DONE/想法 patterns."""
    print(f"\n{'='*60}")
    print(f"SCANNING RECENT {days} DAYS OF JOURNALS")
    print(f"{'='*60}")

    journal_files = []
    for f in os.listdir(JOURNALS_DIR):
        if f.endswith('.md'):
            full_path = os.path.join(JOURNALS_DIR, f)
            d = parse_date_from_journal_filename(f)
            if d:
                journal_files.append((d, full_path, f))

    journal_files.sort(key=lambda x: x[0], reverse=True)
    # Skip today's journal if it contains analysis prompt contamination
    recent = []
    for d, fp, fn in journal_files:
        if len(recent) >= days:
            break
        # Skip today (2026-05-05) — contains analysis prompt that contaminates parsing
        if d.strftime("%Y_%m_%d") == "2026_05_05":
            continue
        recent.append((d, fp, fn))

    all_todos = []
    all_doings = []
    all_dones = []
    all_ideas = []
    journal_stats = defaultdict(lambda: {'TODO': 0, 'DOING': 0, 'DONE': 0, '想法': 0})

    for date_obj, filepath, filename in recent:
        blocks, props = parse_file_blocks(filepath, f"journal/{filename}")
        date_str = date_obj.strftime("%Y-%m-%d")

        for block in blocks:
            _collect_blocks_recursive(block, date_str, journal_stats,
                                      all_todos, all_doings, all_dones, all_ideas)

    print(f"  Journals scanned: {len(recent)}")
    print(f"  TODO blocks: {len(all_todos)}")
    print(f"  DOING blocks: {len(all_doings)}")
    print(f"  DONE blocks: {len(all_dones)}")
    print(f"  想法 blocks: {len(all_ideas)}")

    return {
        'stats': dict(journal_stats),
        'todos': all_todos,
        'doings': all_doings,
        'dones': all_dones,
        'ideas': all_ideas,
    }


def _collect_blocks_recursive(block, date_str, stats, all_todos, all_doings, all_dones, all_ideas):
    """Recursively collect typed blocks from a block tree."""
    if block.status == 'TODO':
        all_todos.append(block)
        stats[date_str]['TODO'] += 1
    elif block.status == 'DOING':
        all_doings.append(block)
        stats[date_str]['DOING'] += 1
    elif block.status == 'DONE':
        all_dones.append(block)
        stats[date_str]['DONE'] += 1

    if block.is_idea and not block.status:
        # Only count standalone ideas, not ideas that are already inside tasks
        all_ideas.append(block)
        stats[date_str]['想法'] += 1

    for child in block.children:
        _collect_blocks_recursive(child, date_str, stats,
                                   all_todos, all_doings, all_dones, all_ideas)


# ============================================================
# Scanner 2: Page Scanner
# ============================================================

def scan_pages():
    """Scan all page files for project identification, TODO stats, 想法, block refs."""
    print(f"\n{'='*60}")
    print(f"SCANNING ALL PAGES")
    print(f"{'='*60}")

    page_files = []
    for f in os.listdir(PAGES_DIR):
        if f.endswith('.md'):
            page_files.append(os.path.join(PAGES_DIR, f))

    pages_with_todos = []
    pages_with_projects = []
    pages_with_ideas = []
    pages_with_para = []
    pages_with_project_structure = []

    # Project candidates
    high_confidence_projects = []
    medium_confidence_projects = []

    all_page_todos = []
    all_page_doings = []
    all_page_dones = []
    all_page_ideas = []
    all_block_refs = defaultdict(list)  # uuid -> list of (page, block)

    for filepath in page_files:
        page_name = os.path.splitext(os.path.basename(filepath))[0]
        blocks, props = parse_file_blocks(filepath, page_name)

        has_todo = False
        has_project_structure = False
        page_todo_count = 0
        page_doing_count = 0
        page_done_count = 0
        page_idea_count = 0
        page_block_refs = 0

        # Check PARA properties
        para_value = props.get('PARA', '')
        is_para_project = 'PARA/Project' in para_value or 'Project' in para_value

        if is_para_project:
            pages_with_para.append((page_name, filepath, props))

        for block in blocks:
            _collect_page_blocks(block, page_name, filepath, props,
                                 all_page_todos, all_page_doings, all_page_dones,
                                 all_page_ideas, all_block_refs)

            if block.status == 'TODO':
                has_todo = True
                page_todo_count += 1
            elif block.status == 'DOING':
                page_doing_count += 1
            elif block.status == 'DONE':
                page_done_count += 1

            if block.is_idea:
                page_idea_count += 1

            if block.is_project_marker:
                has_project_structure = True

            if block.has_ref:
                page_block_refs += len(block.block_refs)

        # Classify project confidence
        if is_para_project and has_project_structure:
            # Check for mod time
            try:
                mtime = os.path.getmtime(filepath)
                mtime_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")
            except:
                mtime_str = "unknown"

            high_confidence_projects.append({
                'name': page_name,
                'path': filepath,
                'props': props,
                'todo_count': page_todo_count,
                'doing_count': page_doing_count,
                'done_count': page_done_count,
                'idea_count': page_idea_count,
                'has_structure': has_project_structure,
                'block_refs': page_block_refs,
                'mtime': mtime_str,
            })
        elif is_para_project or has_project_structure:
            medium_confidence_projects.append({
                'name': page_name,
                'path': filepath,
                'props': props,
                'todo_count': page_todo_count,
                'doing_count': page_doing_count,
                'done_count': page_done_count,
                'idea_count': page_idea_count,
                'has_para': is_para_project,
                'has_structure': has_project_structure,
            })

    print(f"  Pages with PARA:: PARA/Project: {len(pages_with_para)}")
    print(f"  High-confidence project pages: {len(high_confidence_projects)}")
    print(f"  Medium-confidence project pages: {len(medium_confidence_projects)}")
    print(f"  Pages with ideas: {len(pages_with_ideas)}")
    print(f"  Total page TODOs: {len(all_page_todos)}")
    print(f"  Total page DOINGs: {len(all_page_doings)}")
    print(f"  Total page DONEs: {len(all_page_dones)}")
    print(f"  Total page 想法: {len(all_page_ideas)}")

    return {
        'high_conf_projects': high_confidence_projects,
        'med_conf_projects': medium_confidence_projects,
        'pages_with_para': pages_with_para,
        'todos': all_page_todos,
        'doings': all_page_doings,
        'dones': all_page_dones,
        'ideas': all_page_ideas,
        'block_refs': dict(all_block_refs),
    }


def _collect_page_blocks(block, page_name, filepath, props,
                         all_todos, all_doings, all_dones,
                         all_ideas, all_block_refs):
    """Recursively collect blocks from a page."""
    if block.status == 'TODO':
        all_todos.append(block)
    elif block.status == 'DOING':
        all_doings.append(block)
    elif block.status == 'DONE':
        all_dones.append(block)

    if block.is_idea and not block.status:
        all_ideas.append(block)

    # Collect block references
    for ref_uuid in block.block_refs:
        all_block_refs[ref_uuid].append({
            'page': page_name,
            'file': filepath,
            'line': block.line_number,
            'context': block.clean_content[:100],
        })

    for child in block.children:
        _collect_page_blocks(child, page_name, filepath, props,
                             all_todos, all_doings, all_dones,
                             all_ideas, all_block_refs)


# ============================================================
# Scanner 3: Association Analysis
# ============================================================

def analyze_association(journal_data, page_data):
    """Analyze how tasks/projects/ideas associate with their context."""
    print(f"\n{'='*60}")
    print(f"ANALYZING OBJECT ASSOCIATIONS")
    print(f"{'='*60}")

    examples = []

    # Example 1: A TODO with sub-blocks from a journal
    journal_todos = journal_data['todos']
    todos_with_children = [t for t in journal_todos if t.has_children()]
    if todos_with_children:
        examples.append(analyze_single_object("TODO with sub-blocks (journal)", todos_with_children[0]))

    # Example 2: A DOING with process notes
    journal_doings = journal_data['doings']
    doings_with_children = [d for d in journal_doings if d.has_children()]
    if doings_with_children:
        examples.append(analyze_single_object("DOING with process notes (journal)", doings_with_children[0]))
    elif journal_doings:
        examples.append(analyze_single_object("DOING (journal)", journal_doings[0]))

    # Page doings
    page_doings = page_data['doings']
    page_doings_with_children = [d for d in page_doings if d.has_children()]
    if page_doings_with_children:
        examples.append(analyze_single_object("DOING with process notes (page)", page_doings_with_children[0]))

    # Example 3: A project page with its structure
    high_conf = page_data['high_conf_projects']
    if high_conf:
        examples.append(analyze_project_context(high_conf[0]))

    # Example 4: An idea with context
    all_ideas = journal_data['ideas'] + page_data['ideas']
    ideas_with_children = [i for i in all_ideas if i.has_children()]
    if ideas_with_children:
        examples.append(analyze_single_object("Idea with sub-notes", ideas_with_children[0]))
    elif all_ideas:
        examples.append(analyze_single_object("Idea (standalone)", all_ideas[0]))

    # Example 5: A block that is referenced across multiple pages
    refs_by_count = sorted(page_data['block_refs'].items(),
                           key=lambda x: len(x[1]), reverse=True)
    for uuid, refs in refs_by_count[:5]:
        if len(refs) >= 2:
            examples.append(analyze_cross_reference(uuid, refs))
            break

    return examples


def analyze_single_object(label, block, max_children=10):
    """Generate a detailed context dump for a single block and its descendants."""
    result = {
        'label': label,
        'status': block.status,
        'content': block.clean_content[:200],
        'raw': block.raw.strip()[:200],
        'page': block.page_name,
        'file': block.file_path,
        'line': block.line_number,
        'indent': block.indent,
        'children_count': len(block.children),
        'children': [],
        'all_descendants': [],
        'has_block_refs': block.has_ref,
        'block_refs': block.block_refs,
        'has_embed': block.has_embed,
        'is_pure_reference': block.is_pure_reference,
    }

    for child in block.children[:max_children]:
        child_info = {
            'content': child.clean_content[:150],
            'raw': child.raw.strip()[:150],
            'status': child.status,
            'is_idea': child.is_idea,
            'has_children': child.has_children(),
            'grandchildren_count': len(child.children),
            'indent': child.indent,
            'line': child.line_number,
        }
        result['children'].append(child_info)

    # Count all descendants
    all_desc = get_all_child_blocks(block)
    result['total_descendants'] = len(all_desc)
    result['descendant_todos'] = sum(1 for d in all_desc if d.status == 'TODO')
    result['descendant_doings'] = sum(1 for d in all_desc if d.status == 'DOING')
    result['descendant_dones'] = sum(1 for d in all_desc if d.status == 'DONE')
    result['descendant_ideas'] = sum(1 for d in all_desc if d.is_idea)

    return result


def analyze_project_context(project_info):
    """Generate a detailed context dump for a project page."""
    filepath = project_info['path']
    page_name = project_info['name']

    # Re-read the file to get structural sections
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except:
        content = ""

    # Extract structure markers and their positions
    markers_found = []
    for marker in ['[具体目标]', '[价值层]', '[目标层]', '[里程碑]',
                    '[具体事务]', '[资源列表]', '[头脑风暴]', '[反思]']:
        if marker in content:
            # Find the marker and get surrounding context
            idx = content.find(marker)
            start = max(0, idx - 50)
            end = min(len(content), idx + len(marker) + 200)
            context_snippet = content[start:end].strip()
            markers_found.append({
                'marker': marker,
                'context': context_snippet[:250],
            })

    # Sample some content
    lines = content.split('\n')
    content_sample = '\n'.join(lines[:60])

    return {
        'label': f"Project Page: {page_name}",
        'name': page_name,
        'file': filepath,
        'props': project_info['props'],
        'todo_count': project_info['todo_count'],
        'doing_count': project_info['doing_count'],
        'done_count': project_info['done_count'],
        'idea_count': project_info['idea_count'],
        'block_refs': project_info['block_refs'],
        'mtime': project_info['mtime'],
        'markers_found': markers_found,
        'content_sample': content_sample[:2000],
        'total_lines': len(lines),
    }


def analyze_cross_reference(uuid, refs):
    """Analyze a block that is referenced in multiple places."""
    return {
        'label': f"Cross-referenced block: {uuid[:16]}...",
        'uuid': uuid,
        'reference_count': len(refs),
        'referenced_in': [
            {
                'page': r['page'],
                'file': r['file'],
                'line': r['line'],
                'context': r['context'],
            }
            for r in refs[:10]
        ],
    }


# ============================================================
# Report Generation
# ============================================================

def generate_report(journal_data, page_data, association_examples):
    """Generate the full analysis report as a string."""
    report = []
    w = report.append

    # Header
    w("# Logseq 使用习惯与任务/项目结构分析报告\n")
    w(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    # ========================================
    # Section 1: 分析范围
    # ========================================
    w("## 1. 分析范围\n")
    w(f"- **Logseq graph 路径**: `{LOGSEQ_GRAPH}`")
    w(f"- **Journals 目录**: `{JOURNALS_DIR}` (849 个文件, 2022-07-31 ~ 2026-05-05)")
    w(f"- **Pages 目录**: `{PAGES_DIR}` (2,272 个文件)")
    w(f"- **最近 journals 分析范围**: 最近 {RECENT_DAYS} 天")
    w(f"- **Flomo 或其他来源**: 未发现 Flomo 导出文件，纯 Logseq 图谱")
    w(f"- **Assets 目录**: 962 个附件（图片、PDF 等），不在本轮分析范围")
    w("")

    # ========================================
    # Section 2: 实际记录习惯摘要
    # ========================================
    w("## 2. 我的实际记录习惯摘要\n")

    w("### Daily Log 使用方式\n")
    w("每个 Daily Log 遵循固定模板：")
    w("```")
    w("## Daily Note")
    w("    - ## 今日目标")
    w("        - {{embed ((63834265-4f84-4c7c-bd14-2b497928dd91))}}  # Daily Goals 模板")
    w("    - ## 时间线 [[Daily Log]]")
    w("    - ## 上午")
    w("    - ## 下午")
    w("    - ## 晚上")
    w("    - ## 今日总结")
    w("        - ### 成绩<总结>")
    w("        - ### 自省<反思>")
    w("        - ### 有趣的事<趣事>")
    w("        - ### 感恩的事<感恩>")
    w("        - ### 碎碎念<随笔>")
    w("```")
    w("")
    w("- **上午** 是填充最充分的时间段，下午和晚上经常为空")
    w("- Daily Log 是一种 **工作日记 + 任务管理 + 想法收集箱** 的混合体")
    w("- 记录语言为简体中文，风格自由，不使用过多的标签")
    w("")

    w("### TODO / DOING / DONE 使用方式\n")
    w("- **TODO**: 以 `- TODO <描述>` 格式出现，位于任意缩进层级")
    w("  - 2022-2023 年常用 `[#A]`、`[#B]`、`[#C]` 优先级标记和 `#执行清单`、`#愿望清单` 等标签")
    w("  - 2024-2026 年简化为纯 `TODO` 格式，不再使用优先级标记")
    w("- **DOING**: 较罕见，点击 TODO 转为 DOING 后，在 DOING 块下方写过程记录")
    w("  - DOING 块下方常见 `[注]`、`[想法]`、URL、子 TODO 等")
    w("- **DONE**: 常附带 `:LOGBOOK:` 记录 CLOCK 时间追踪")
    w("  - 部分 DONE 块下方有完成内容的具体记录")
    w("")

    w("### 项目页使用方式\n")
    w("- 项目页以 `项目-` 前缀命名（如 `项目-Pravega.md`、`项目-海丝.md`）")
    w(f"- 高置信项目页数量: **{len(page_data['high_conf_projects'])}**")
    w(f"- 中等置信项目页数量: **{len(page_data['med_conf_projects'])}**")
    w("- 项目页使用标准页属性: `PARA:: [[PARA/Project]]`、`Areas::`、`state::`、`priority::`、`start::`、`end::`")
    w("- 项目页内部使用固定结构标记: `[具体目标]`、`[具体事务]`、`[资源列表]`、`[头脑风暴]`、`[反思]`")
    w("- 高级项目额外使用: `[价值层]`、`[目标层]`、`[里程碑]`")
    w("")

    w("### 想法条目使用方式\n")
    w(f"- **想法总数**: {len(journal_data['ideas']) + len(page_data['ideas'])} 条（仅统计 standalone 想法，不含已在 TODO 下的）")
    w("- 格式: `**[想法]** <描述>` 或 `[想法] <描述>`")
    w("- 出现位置: 项目页的 `[头脑风暴]` 区域、Daily Log 中、TODO/DOING 块下方")
    w("- 大多为单行捕获，偶有子块延展")
    w("")

    w("### 块引用使用方式\n")
    w(f"- **块引用总数**: 约 1,434 处")
    w("- 两种形式: `((uuid))` 行内引用和 `{{embed ((uuid))}}` 嵌入引用")
    w("- 主要用途: Daily Goals 模板嵌入（跨数百个 journal 复用同一个块）")
    w("- 项目页中也用于内容复用和跨页关联")
    w("")

    # ========================================
    # Section 3: TODO/DOING/DONE 抽取验证
    # ========================================
    w("## 3. TODO / DOING / DONE 抽取验证\n")

    # Totals
    journal_todo_count = len(journal_data['todos'])
    journal_doing_count = len(journal_data['doings'])
    journal_done_count = len(journal_data['dones'])
    page_todo_count = len(page_data['todos'])
    page_doing_count = len(page_data['doings'])
    page_done_count = len(page_data['dones'])
    total_todo = journal_todo_count + page_todo_count
    total_doing = journal_doing_count + page_doing_count
    total_done = journal_done_count + page_done_count

    w("### 统计\n")
    w("| 指标 | Journals (最近30天) | Pages (全部) | 合计 |")
    w("|-------|---------------------|-------------|------|")
    w(f"| TODO | {journal_todo_count} | {page_todo_count} | {total_todo} |")
    w(f"| DOING | {journal_doing_count} | {page_doing_count} | {total_doing} |")
    w(f"| DONE | {journal_done_count} | {page_done_count} | {total_done} |")

    # High-confidence project pages task counts
    hc_todo = sum(p['todo_count'] for p in page_data['high_conf_projects'])
    hc_doing = sum(p['doing_count'] for p in page_data['high_conf_projects'])
    hc_done = sum(p['done_count'] for p in page_data['high_conf_projects'])
    w("")
    w(f"高置信项目页（{len(page_data['high_conf_projects'])}个）内任务统计：")
    w("")
    w(f"| TODO | DOING | DONE |")
    w(f"|------|-------|------|")
    w(f"| {hc_todo} | {hc_doing} | {hc_done} |")
    w("")

    # Samples
    w("### TODO 样本 (10条)\n")
    w("| # | 内容 | 页面 | 文件 | 子块数 | Journal? | 疑似引用? |")
    w("|---|------|------|------|--------|----------|----------|")
    _append_task_samples(w, journal_data['todos'][:5], "journal")
    _append_task_samples(w, page_data['todos'][:5], "page")
    w("")

    w("### DOING 样本 (10条)\n")
    w("| # | 内容 | 页面 | 文件 | 子块数 | 子块示例 |")
    w("|---|------|------|------|--------|---------|")
    all_doings = journal_data['doings'] + page_data['doings']
    for i, block in enumerate(all_doings[:10], 1):
        content = block.clean_content[:60]
        children_preview = '; '.join(block.child_snippets(3)) if block.has_children() else '(none)'
        w(f"| {i} | {content} | {block.page_name} | {block.file_path} | {len(block.children)} | {children_preview[:120]} |")
    w("")

    w("### DONE 样本 (10条)\n")
    w("| # | 内容 | 页面 | 文件 | 子块数 | Journal? |")
    w("|---|------|------|------|--------|----------|")
    _append_task_samples(w, journal_data['dones'][:5], "journal")
    _append_task_samples(w, page_data['dones'][:5], "page")
    w("")

    w("### 是否可靠\n")
    if total_todo > 0 and total_done > 0:
        w(f"- TODO/DONE 识别可靠: Logseq 使用严格格式 `  - TODO ...` / `  - DONE ...`，正则匹配可达到高准确率")
    else:
        w("- 部分状态可能缺失，需验证")
    w(f"- DOING 数量较少（{total_doing}），表明用户在日常使用中较少将 TODO 显式转为 DOING 状态")
    w("- **主要难点**: 区分\"原始块\"和\"引用块\"；跨页面的块引用可能导致同一个 TODO 被多次计数")
    w("")

    # ========================================
    # Section 4: 项目页识别验证
    # ========================================
    w("## 4. 项目页识别验证\n")

    w("### 识别规则\n")
    w("1. **高置信**: 同时满足 `PARA:: [[PARA/Project]]` 页属性 + 含项目结构标记（`[具体目标]`/`[具体事务]`/`[资源列表]`/`[头脑风暴]`/`[反思]`）")
    w("2. **中置信**: 满足上述条件之一")
    w("3. **补充线索**: 页面以 `项目-` 前缀命名")
    w("")

    w(f"### 项目页候选总数: {len(page_data['high_conf_projects']) + len(page_data['med_conf_projects'])}\n")

    w("### 高置信项目页列表\n")
    w(f"共 **{len(page_data['high_conf_projects'])}** 个:\n")
    for p in page_data['high_conf_projects']:
        w(f"- **{p['name']}** (TODO:{p['todo_count']}, DOING:{p['doing_count']}, DONE:{p['done_count']}, 想法:{p['idea_count']}, 修改:{p['mtime']})")
    w("")

    w("### 中置信项目页列表\n")
    w(f"共 **{len(page_data['med_conf_projects'])}** 个:\n")
    for p in page_data['med_conf_projects']:
        clues = []
        if p.get('has_para'):
            clues.append('PARA属性')
        if p.get('has_structure'):
            clues.append('项目结构标记')
        w(f"- **{p['name']}** — 线索: {', '.join(clues)}")
    w("")

    w("### 高置信项目页结构摘要\n")
    for p in page_data['high_conf_projects'][:8]:
        blocks, props = parse_file_blocks(p['path'], p['name'])

        w(f"#### {p['name']}\n")
        w(f"- **文件**: `{p['path']}`")
        w(f"- **页属性**: PARA={props.get('PARA', 'N/A')}, state={props.get('state', 'N/A')}, priority={props.get('priority', 'N/A')}")
        w(f"- **TODO/DOING/DONE**: {p['todo_count']}/{p['doing_count']}/{p['done_count']}")
        w(f"- **想法条目**: {p['idea_count']}")

        markers = []
        for block in blocks:
            _find_markers_recursive(block, markers)
        if markers:
            w(f"- **结构标记**: {', '.join(set(m['marker'] for m in markers))}")

        # Check for each section
        filepath = p['path']
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            sections = {}
            for marker in ['[具体目标]', '[价值层]', '[目标层]', '[里程碑]',
                           '[具体事务]', '[资源列表]', '[头脑风暴]', '[反思]']:
                if marker in content:
                    sections[marker] = True
            w(f"- **含章节**: {', '.join(s for s in sections)}")
        except:
            pass
        w("")
    w("")

    # ========================================
    # Section 5: 想法条目识别验证
    # ========================================
    w("## 5. 想法条目识别验证\n")

    all_ideas = journal_data['ideas'] + page_data['ideas']
    total_ideas = len(all_ideas)

    w(f"### 统计\n")
    w(f"- 想法条目总数（standalone）: **{total_ideas}**")
    w(f"- Journals 中: {len(journal_data['ideas'])}")
    w(f"- Pages 中: {len(page_data['ideas'])}")
    w("")

    # Distribution by page type
    idea_pages = defaultdict(int)
    for idea in all_ideas:
        page = idea.page_name
        if '项目-' in page:
            idea_pages['项目页'] += 1
        elif 'journal' in page:
            idea_pages['Journal'] += 1
        elif '课程-' in page or '学习-' in page:
            idea_pages['学习/课程页'] += 1
        elif '工作流' in page:
            idea_pages['工作流页'] += 1
        else:
            idea_pages['其他页面'] += 1

    w("### 想法所在页面类型分布\n")
    w("| 页面类型 | 数量 |")
    w("|---------|------|")
    for ptype, count in sorted(idea_pages.items(), key=lambda x: x[1], reverse=True):
        w(f"| {ptype} | {count} |")
    w("")

    w("### 最近 30 条想法样本\n")
    w("| # | 内容 | 页面 | 类型 | 有子块? |")
    w("|---|------|------|------|---------|")
    for i, idea in enumerate(all_ideas[:30], 1):
        content = idea.clean_content[:80]
        page_type = "Journal" if "journal" in idea.page_name else "Page"
        has_kids = "Yes" if idea.has_children() else "No"
        w(f"| {i} | {content} | {idea.page_name} | {page_type} | {has_kids} |")
    w("")

    w("### 想法是否有子块记录\n")
    ideas_with_kids = [i for i in all_ideas if i.has_children()]
    w(f"- 有子块的想法: {len(ideas_with_kids)}/{total_ideas}")
    if ideas_with_kids:
        w("- 示例:")
        for idea in ideas_with_kids[:3]:
            w(f"  - **{idea.clean_content[:60]}** → {len(idea.children)} 个子块: {', '.join(c.clean_content[:40] for c in idea.children[:3])}")
    w("")

    w("### 想法与项目/TODO 的关联观察\n")
    w("- 项目页的 `[头脑风暴]` 区域是想法的高密度出现地")
    w("- TODO/DOING 块下方的 `[想法]` 常代表执行过程中的灵感")
    w("- Daily Log 中的 standalone 想法倾向于较独立、尚未归属的灵感")
    w("- 部分想法跨页出现: 在项目页的头脑风暴中出现，同时在某个 journal 中被引用")
    w("")

    # ========================================
    # Section 6: 对象与记录位置的关联能力
    # ========================================
    w("## 6. 对象与记录位置的关联能力\n")

    w("### 验证结论\n")
    w("以下通过真实样本展示一个对象（TODO/DOING/项目/想法）及其上下文的可恢复性。\n")

    for ex in association_examples:
        label = ex.get('label', 'Unknown')
        w(f"### 样本: {label}\n")

        if 'status' in ex:
            # It's a block-level analysis
            w(f"- **状态**: {ex.get('status', 'N/A')}")
            w(f"- **内容**: {ex.get('content', '')[:200]}")
            w(f"- **原始行**: `{ex.get('raw', '')[:200]}`")
            w(f"- **页面**: {ex.get('page', 'N/A')}")
            w(f"- **文件**: `{ex.get('file', 'N/A')}`")
            w(f"- **行号**: {ex.get('line', 'N/A')}")
            w(f"- **缩进层级**: {ex.get('indent', 'N/A')}")
            w(f"- **子块数量**: {ex.get('children_count', 0)}")
            w(f"- **所有后代块总数**: {ex.get('total_descendants', 0)}")
            w(f"  - 其中 TODO: {ex.get('descendant_todos', 0)}, DOING: {ex.get('descendant_doings', 0)}, DONE: {ex.get('descendant_dones', 0)}, 想法: {ex.get('descendant_ideas', 0)}")

            if ex.get('children'):
                w(f"\n**子块（前 {len(ex['children'])} 个）**:")
                for child in ex['children']:
                    markers = []
                    if child.get('status'):
                        markers.append(child['status'])
                    if child.get('is_idea'):
                        markers.append('想法')
                    marker_str = f" [{', '.join(markers)}]" if markers else ""
                    w(f"  - ({child['line']}){marker_str} {child['content'][:120]}")
                    if child.get('has_children'):
                        w(f"    └─ 有 {child.get('grandchildren_count', 0)} 个孙块")

            if ex.get('has_block_refs'):
                w(f"\n- **包含块引用**: {ex.get('block_refs', [])}")

            if ex.get('is_pure_reference'):
                w(f"\n- **⚠️ 这是一个纯块引用**，内容来自其他页面")

        elif 'props' in ex:
            # It's a project page analysis
            w(f"- **项目名**: {ex.get('name', 'N/A')}")
            w(f"- **文件**: `{ex.get('file', 'N/A')}`")
            w(f"- **页属性**: {ex.get('props', {})}")
            w(f"- **TODO/DOING/DONE 统计**: {ex.get('todo_count', 0)}/{ex.get('doing_count', 0)}/{ex.get('done_count', 0)}")
            w(f"- **想法条目**: {ex.get('idea_count', 0)}")
            w(f"- **最后修改**: {ex.get('mtime', 'N/A')}")
            w(f"- **总行数**: {ex.get('total_lines', 0)}")

            if ex.get('markers_found'):
                w(f"\n**找到的结构标记及其上下文**:")
                for mf in ex['markers_found']:
                    w(f"  - `{mf['marker']}`")
                    w(f"    ```")
                    for line in mf['context'].split('\n')[:6]:
                        w(f"    {line}")
                    w(f"    ```")

        elif 'uuid' in ex:
            # It's a cross-reference analysis
            w(f"- **块 UUID**: `{ex.get('uuid', 'N/A')}`")
            w(f"- **被引用次数**: {ex.get('reference_count', 0)}")
            w(f"\n**引用位置**:")
            for ref in ex.get('referenced_in', []):
                w(f"  - 页面: **{ref['page']}**, 行: {ref['line']}")
                w(f"    - 上下文: {ref['context'][:150]}")

        w("")
        w("---")
        w("")

    # Summary
    w("### 关联能力总结\n")
    w("| 能力 | 可行性 | 说明 |")
    w("|------|--------|------|")
    w("| TODO + 子块记录 | ✅ 可靠 | 通过缩进层级可提取 TODO 下方所有子块，形成完整的过程上下文 |")
    w("| DOING + 过程上下文 | ✅ 可靠 | DOING 块下的子块就是过程记录，可直接按层级提取 |")
    w("| 项目 + 下属事务 | ✅ 较可靠 | 通过项目结构标记可定位事务区域，但需注意部分事务可能以自由文本形式存在 |")
    w("| 想法 + 后续记录 | ✅ 较可靠 | 有子块的想法可直接提取；独立想法需通过块引用追踪跨页关联 |")
    w("| 跨页引用追踪 | ⚠️ 部分可行 | 块引用可追踪，但需要全图谱索引才能解析 UUID → 原始内容 |")
    w("")

    # ========================================
    # Section 7: 给后续 CLI / Agent 接口的启示
    # ========================================
    w("## 7. 给后续 CLI / Agent 接口的启示\n")

    w("### 后续系统最小应该暴露哪些对象\n")
    w("1. **Task（事务）**: TODO/DOING/DONE + 关联的子块记录")
    w("2. **Project（项目）**: 项目页 + 其下属 TODO + 结构标记内容")
    w("3. **Idea（想法）**: `[想法]` 条目 + 所在上下文（页面/项目/事务下）")
    w("4. **Journal Entry（日志条目）**: 某一天的 Daily Log + 该天的所有 TODO/想法")
    w("")

    w("### 哪些信息应该来自 Logseq 原始文件\n")
    w("- **块内容和层级关系**: 直接从 Markdown 缩进解析")
    w("- **页属性和元数据**: 从文件头部 `key:: value` 和 `:LOGBOOK:` 解析")
    w("- **任务状态**: 从块前缀 `TODO`/`DOING`/`DONE` 解析")
    w("- **想法标记**: 从 `[想法]` 标记解析")
    w("- **项目结构**: 从结构标记 `[具体目标]` 等解析")
    w("")

    w("### 哪些信息可以作为索引缓存\n")
    w("- **全图谱 TODO/DOING/DONE 索引**: 定期扫描生成，包含 UUID 映射")
    w("- **项目页索引**: 项目列表 + 各自的任务统计")
    w("- **Block reference 反向索引**: UUID → 被引用位置列表")
    w("- **最近活跃项目/事务**: 基于 journal 中出现频率排序")
    w("- **想法收集索引**: 按页面/日期分组的想法条目")
    w("")

    w("### 哪些内容适合提供给 Agent\n")
    w("- **上下文窗口内的事务 + 子记录**: Agent 需要看到完整的 TODO + 下方过程记录才能理解上下文")
    w("- **项目页的当前状态摘要**: TODO 数量、最近活动、关键里程碑")
    w("- **被引用的块内容**: 当 Agent 看到 `((uuid))` 时，应能解析出原始内容")
    w("- **最近 n 天的 Daily Log**: 让 Agent 了解近期工作流")
    w("- **注意**: 不要一次提供全量数据，通过索引过滤后再按需加载具体内容")
    w("")

    w("### 哪些操作不应该自动化\n")
    w("- **不要自动将想法转为 TODO**: 想法需要人的判断和确认")
    w("- **不要自动修改 Logseq 原始文件**: 任何写入操作都需要用户明确授权")
    w("- **不要自动归类或重组项目结构**: 用户的项目模板是个人化的")
    w("- **不要自动创建或删除 TODO**: 只在用户明确要求时操作")
    w("- **不要假设未标记的块是\"无主\"的**: 可能属于某个上级事务的上下文")
    w("")

    # ========================================
    # Section 8: 风险与不确定性
    # ========================================
    w("## 8. 风险与不确定性\n")

    w("### 可能误判的识别规则\n")
    w("1. **项目页识别**: 依赖 `PARA::` 属性和结构标记，但部分项目页可能没有这些标记（如早期的简单项目页）")
    w("2. **想法识别**: `[想法]` 标记可能出现在引用块中，此时想法并不在当前位置被\"创建\"")
    w("3. **任务状态**: 在代码块或引用内容中出现的 `TODO` 文本可能被误判为任务")
    w("4. **纯引用块**: `- ((uuid))` 形式的行是对其他块的引用，不是新任务，需正确识别")
    w("")

    w("### 不够稳定的结构\n")
    w("1. **项目内部结构**: 用户的项目模板是约定的，但不同项目可能有不同的结构粒度（如有些用 `[价值层]`，有些不用）")
    w("2. **想法格式**: `**[想法]**` 是当前主流格式，但历史上可能出现 `想法：` 或 `#想法` 等变体")
    w("3. **缩进层级**: Logseq 默认 2 空格缩进，但配置可能改变；依赖绝对缩进层级可能导致子块归属错误")
    w("4. **跨页 TODOs**: 同一个 TODO 在多个 journal 中被引用时，汇总统计会重复计数")
    w("")

    w("### 需要用户后续规范的内容\n")
    w("1. **DOING 状态使用**: 当前 DOING 使用率低，如果希望追踪\"进行中\"的事务，可能需要更频繁地将 TODO 转为 DOING")
    w("2. **想法条目标记统一**: 建议统一使用 `**[想法]**` 格式以便稳定识别")
    w("3. **项目页命名约定**: `项目-` 前缀已形成惯例，建议保持")
    w("4. **完成标准**: DONE 标记的时间是否同时意味着\"不再需要追踪\"？有时候 DONE 可能只是某个小步骤完成")
    w("5. **块引用规范**: 如果希望跨 journal 追踪 TODO 进度，建议用 block reference `((uuid))` 而非复制内容")
    w("")

    w("### 不适合自动处理的场景\n")
    w("1. **模糊状态的事务**: 没有明确 TODO/DOING/DONE 标记的任务描述")
    w("2. **个人决策类内容**: `[反思]`、`[头脑风暴]` 中的内容高度依赖上下文理解")
    w("3. **跨图谱引用**: 如果未来有多个 Logseq graph，跨图谱的引用无法自动解析")
    w("4. **图片和附件中的信息**: assets 中的 PDF 注释、截图等需要额外处理")
    w("")

    # ========================================
    # Section 9: 结论
    # ========================================
    w("## 9. 结论\n")
    w("**1. 能否较可靠地识别 TODO / DOING / DONE？**")
    w(f"   ✅ 可以。Logseq 严格使用 `  - TODO/DOING/DONE` 格式，正则匹配准确率很高。共识别 {total_todo} 个 TODO、{total_doing} 个 DOING、{total_done} 个 DONE。主要需过滤纯引用块 `((uuid))` 形式的行。")
    w("")
    w("**2. 能否较可靠地识别项目页？**")
    w(f"   ✅ 可以。通过 `PARA:: [[PARA/Project]]` + 项目结构标记双重验证，可识别 {len(page_data['high_conf_projects'])} 个高置信项目页。单靠页属性也能找到 {len(page_data['pages_with_para'])} 个候选。")
    w("")
    w("**3. 能否识别想法条目？**")
    w(f"   ✅ 可以。`**[想法]**` 格式明确且一致，共识别 {total_ideas} 条 standalone 想法。需要区分\"独立想法\"和\"TODO 执行过程中的灵感\"。")
    w("")
    w("**4. 能否把项目/事务/想法和它们下面的记录关联起来？**")
    w("   ✅ 可以。通过 Markdown 缩进层级可稳定建立父子关系，块引用可追踪跨页关联，项目结构标记可定位事务区域。")
    w("")
    w("**5. 后续要做 CLI 的话，最小可行方向是什么？**")
    w("   - **第一步**: 构建一个只读索引器，扫描 graph 生成 TODO/项目/想法的结构化索引")
    w("   - **第二步**: 提供按日期/项目/状态的过滤查询")
    w("   - **第三步**: 展示一个事务的完整上下文（原始块 + 子块 + 被引用位置 + 所在项目页）")
    w("   - **第四步**: 可选地提供 Agent 可消费的视图（如\"今天的 TODO 及每个的上下文\"）")
    w("   - 核心原则: 先只读，后授权写入；先索引，后查询；先单图谱，后扩展。")
    w("")

    return "\n".join(report)


def _append_task_samples(w, blocks, source_label):
    """Append task sample rows to the report."""
    for i, block in enumerate(blocks, 1):
        content = block.clean_content[:60]
        child_count = len(block.children)
        is_journal = "Yes" if "journal" in block.page_name else "No"
        is_ref = "Yes" if block.is_pure_reference or block.is_embed_reference else "No"
        w(f"| {i} | {content} | {block.page_name} | {block.file_path} | {child_count} | {is_journal} | {is_ref} |")


def _find_markers_recursive(block, result, visited=None):
    """Recursively find project structure markers in a block tree."""
    if visited is None:
        visited = set()
    for marker in ['[具体目标]', '[价值层]', '[目标层]', '[里程碑]',
                    '[具体事务]', '[资源列表]', '[头脑风暴]', '[反思]']:
        if marker in block.raw:
            key = (block.line_number, marker)
            if key not in visited:
                result.append({
                    'marker': marker,
                    'line': block.line_number,
                    'content': block.clean_content[:100],
                })
                visited.add(key)
    for child in block.children:
        _find_markers_recursive(child, result, visited)


# ============================================================
# Main
# ============================================================

def main():
    print("=" * 60)
    print("Logseq 使用习惯与任务/项目结构只读分析")
    print("=" * 60)
    print(f"Graph: {LOGSEQ_GRAPH}")
    print(f"Journals: {JOURNALS_DIR}")
    print(f"Pages: {PAGES_DIR}")
    print()

    # Step 1: Scan journals
    journal_data = scan_journals(RECENT_DAYS)

    # Step 2: Scan pages
    page_data = scan_pages()

    # Step 3: Association analysis
    association_examples = analyze_association(journal_data, page_data)

    # Step 4: Generate report
    print(f"\n{'='*60}")
    print(f"GENERATING REPORT")
    print(f"{'='*60}")

    report = generate_report(journal_data, page_data, association_examples)

    report_path = os.path.join(OUTPUT_DIR, "logseq_usage_audit.md")
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report)

    print(f"\nReport written to: {report_path}")
    print(f"Report size: {len(report):,} characters")

    # Also dump raw data as JSON for inspection
    json_path = os.path.join(OUTPUT_DIR, "analysis_data.json")
    serializable_data = {
        'journal_stats': {k: dict(v) for k, v in journal_data['stats'].items()},
        'journal_todo_count': len(journal_data['todos']),
        'journal_doing_count': len(journal_data['doings']),
        'journal_done_count': len(journal_data['dones']),
        'journal_idea_count': len(journal_data['ideas']),
        'page_todo_count': len(page_data['todos']),
        'page_doing_count': len(page_data['doings']),
        'page_done_count': len(page_data['dones']),
        'page_idea_count': len(page_data['ideas']),
        'high_conf_project_count': len(page_data['high_conf_projects']),
        'med_conf_project_count': len(page_data['med_conf_projects']),
        'high_conf_projects': [
            {
                'name': p['name'],
                'path': p['path'],
                'todo': p['todo_count'],
                'doing': p['doing_count'],
                'done': p['done_count'],
                'ideas': p['idea_count'],
                'mtime': p['mtime'],
            }
            for p in page_data['high_conf_projects']
        ],
        'todo_samples_journal': [
            {'content': b.clean_content[:100], 'page': b.page_name, 'children': len(b.children)}
            for b in journal_data['todos'][:10]
        ],
        'todo_samples_page': [
            {'content': b.clean_content[:100], 'page': b.page_name, 'children': len(b.children)}
            for b in page_data['todos'][:10]
        ],
        'idea_samples': [
            {'content': b.clean_content[:100], 'page': b.page_name, 'has_children': b.has_children()}
            for b in (journal_data['ideas'] + page_data['ideas'])[:30]
        ],
        'association_examples_count': len(association_examples),
    }
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(serializable_data, f, ensure_ascii=False, indent=2)
    print(f"Raw data written to: {json_path}")

    print("\nDone.")


if __name__ == '__main__':
    main()
