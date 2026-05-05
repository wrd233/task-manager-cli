import os
from abc import ABC, abstractmethod
from typing import Any, Dict, List


class ProposalProvider(ABC):
    """Boundary for future API-backed proposal generation."""

    @abstractmethod
    def generate_proposals(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        raise NotImplementedError


class RuleBasedProvider(ProposalProvider):
    def generate_proposals(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        proposals: List[Dict[str, Any]] = []
        for item in context.get("items", []):
            text = item.get("text", "")
            if "?" in text or "？" in text:
                proposals.append(
                    {
                        "proposal_type": "needs_clarification",
                        "title": "Mark item as needing clarification",
                        "risk": "low",
                        "payload": {"marker": "**[待澄清]**", "content": "需要补充上下文。"},
                    }
                )
        return proposals


def provider_from_env() -> ProposalProvider:
    provider = os.environ.get("TM_PROVIDER", "rule_based").lower()
    if provider in {"rule_based", "mock"}:
        return RuleBasedProvider()
    raise ValueError("Only the rule_based provider is available in this round.")
