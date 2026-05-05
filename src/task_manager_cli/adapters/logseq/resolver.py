from pathlib import Path
from typing import Dict, Iterable, List, Optional

from task_manager_cli.adapters.logseq.parser import LogseqBlock, parse_logseq_file
from task_manager_cli.adapters.logseq.extractors import page_name_from_path


class LogseqResolver:
    def __init__(self, graph_path: Path):
        self.graph_path = Path(graph_path)
        self.uuid_index: Dict[str, LogseqBlock] = {}
        self.blocks: List[LogseqBlock] = []

    def build(self) -> "LogseqResolver":
        for base in ("pages", "journals"):
            folder = self.graph_path / base
            if not folder.exists():
                continue
            for path in folder.rglob("*.md"):
                parsed = parse_logseq_file(path, page_name_from_path(path))
                for block in parsed.blocks:
                    self.blocks.append(block)
                    if block.uuid:
                        self.uuid_index[block.uuid] = block
        return self

    def get(self, uuid: str) -> Optional[LogseqBlock]:
        return self.uuid_index.get(uuid)

    def references_to(self, uuid: str) -> List[LogseqBlock]:
        refs = []
        for block in self.blocks:
            if uuid in block.block_refs or uuid in block.embeds:
                refs.append(block)
        return refs
