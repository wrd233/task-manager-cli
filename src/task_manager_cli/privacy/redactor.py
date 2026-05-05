import re
from dataclasses import dataclass
from typing import Iterable, List, Tuple


DEFAULT_PATTERNS = [
    r"(?i)(api[_-]?key|token|secret|password|passwd|pwd)\s*[:=]\s*['\"]?[^'\"\s]+",
    r"(?i)(密码|口令|密钥|令牌)\s*[:：=]\s*\S+",
    r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
    r"\b[A-Za-z0-9_\-]{24,}\.[A-Za-z0-9_\-]{6,}\.[A-Za-z0-9_\-]{6,}\b",
]


@dataclass
class RedactionResult:
    text: str
    redacted: bool
    reasons: List[str]


class Redactor:
    def __init__(self, patterns: Iterable[str] = ()):
        self.patterns: List[Tuple[str, re.Pattern]] = []
        for pattern in list(DEFAULT_PATTERNS) + list(patterns):
            self.patterns.append((pattern, re.compile(pattern)))

    def redact(self, text: str, private: bool = False) -> RedactionResult:
        if private:
            return RedactionResult("[REDACTED: private record]", True, ["private_marker"])
        reasons: List[str] = []
        redacted = text
        for pattern, compiled in self.patterns:
            if compiled.search(redacted):
                redacted = compiled.sub("[REDACTED]", redacted)
                reasons.append(pattern)
        return RedactionResult(redacted, bool(reasons), reasons)
