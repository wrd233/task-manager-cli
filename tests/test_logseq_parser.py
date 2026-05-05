from pathlib import Path

from task_manager_cli.adapters.logseq.parser import parse_logseq_file


FIXTURE = Path(__file__).parent / "fixtures" / "logseq_graph"


def test_parser_recovers_block_tree_and_page_properties():
    parsed = parse_logseq_file(FIXTURE / "pages" / "项目-Alpha.md")
    assert parsed.page_properties["PARA"] == "[[PARA/Project]]"
    task = next(block for block in parsed.blocks if block.uuid == "11111111-1111-1111-1111-111111111111")
    assert task.task[0] == "TODO"
    assert any(child.text.startswith("[注]") for child in task.children)


def test_parser_skips_todo_inside_code_block():
    parsed = parse_logseq_file(FIXTURE / "pages" / "项目-Alpha.md")
    assert all("this is code" not in block.raw for block in parsed.blocks)
