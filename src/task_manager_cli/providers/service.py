import hashlib
import json
import time
from typing import Any, Dict, Optional

from task_manager_cli.config.settings import Settings
from task_manager_cli.providers.base import (
    DryRunProvider,
    ProviderConfigError,
    ProviderError,
    ProviderResponseError,
    config_from_settings,
    provider_from_settings,
)


class ProviderService:
    def __init__(self, settings: Settings):
        self.settings = settings

    def doctor(self, provider_name: Optional[str] = None, no_call: bool = False) -> Dict[str, Any]:
        provider = provider_from_settings(self.settings, override_name=provider_name)
        config = config_from_settings(self.settings, override_name=provider_name)
        data: Dict[str, Any] = {
            "provider": config.masked(),
            "config_ok": bool(config.name) and (isinstance(provider, DryRunProvider) or config.name in {"mock", "rule_based", "rule-based"} or bool(config.base_url and config.model and config.api_key)),
            "checks": {
                "base_url_present": bool(config.base_url),
                "model_present": bool(config.model),
                "api_key_present": bool(config.api_key),
                "no_call": no_call,
            },
            "smoke": None,
        }
        if no_call:
            return data
        payload = {
            "prompt_version": config.prompt_version,
            "doctor": True,
            "item": {"id": "doctor", "type": "task", "title": "Provider smoke test", "status": "todo"},
            "answers": [{"question_id": "doctor", "answer": "Smoke test only. Return proposal_candidates as an empty array."}],
            "constraints": ["No real Logseq content is included.", "Return JSON only."],
        }
        started = time.monotonic()
        try:
            result = provider.generate(payload)
            data["smoke"] = {
                "ok": True,
                "latency_ms": result.latency_ms if result.latency_ms is not None else int((time.monotonic() - started) * 1000),
                "response_id": result.response_id,
                "usage": result.usage,
                "proposal_count": len(result.proposal_candidates),
                "summary": result.summary,
            }
        except (ProviderConfigError, ProviderError, ProviderResponseError) as exc:
            data["smoke"] = {
                "ok": False,
                "error_type": exc.__class__.__name__,
                "error": str(exc),
                "latency_ms": int((time.monotonic() - started) * 1000),
            }
        data["smoke"]["payload_hash"] = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:16]
        return data
