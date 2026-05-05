from pathlib import Path


def expand_path(path: str) -> Path:
    return Path(path).expanduser().resolve()
