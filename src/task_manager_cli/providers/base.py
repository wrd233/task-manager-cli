import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from task_manager_cli.config.settings import PROVIDER_API_KEY_ENV, Settings, load_local_env
from task_manager_cli.core.errors import ConfigError, TaskManagerError


class ProviderError(TaskManagerError):
    pass


class ProviderConfigError(ConfigError):
    pass


class ProviderResponseError(ProviderError):
    pass


@dataclass
class ProviderConfig:
    name: str = "mock"
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = None
    timeout: int = 30
    max_tokens: int = 1200
    prompt_version: str = "clarify-v1"

    def masked(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "base_url": self.base_url,
            "api_key_present": bool(self.api_key),
            "api_key": mask_secret(self.api_key),
            "model": self.model,
            "timeout": self.timeout,
            "max_tokens": self.max_tokens,
            "prompt_version": self.prompt_version,
        }


@dataclass
class ProviderResult:
    summary: str
    proposal_candidates: List[Dict[str, Any]] = field(default_factory=list)
    classification_suggestion: Optional[str] = None
    gtd_state_suggestion: Optional[str] = None
    project_suggestion: Optional[str] = None
    marker_suggestion: Optional[str] = None
    annotation_suggestion: Optional[str] = None
    confidence: Optional[float] = None
    reasoning_summary: Optional[str] = None
    needs_user_confirmation: bool = True
    raw_summary: Dict[str, Any] = field(default_factory=dict)


class ProposalProvider:
    def __init__(self, config: ProviderConfig):
        self.config = config

    def preview_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return payload

    def generate(self, payload: Dict[str, Any]) -> ProviderResult:
        raise NotImplementedError


class MockProvider(ProposalProvider):
    def generate(self, payload: Dict[str, Any]) -> ProviderResult:
        answer = " ".join(str(item.get("answer", "")) for item in payload.get("answers", []))
        title = payload.get("item", {}).get("title", "item")
        candidates: List[Dict[str, Any]] = []
        if "等待" in answer or "waiting" in answer.lower():
            candidates.append(
                {
                    "proposal_type": "logseq_task_marker",
                    "title": "Mark task as WAITING",
                    "risk": "medium",
                    "payload": {"new_marker": "WAITING"},
                    "confidence": 0.82,
                    "reasoning_summary": "用户回答显示该事项依赖外部条件。",
                }
            )
        else:
            candidates.append(
                {
                    "proposal_type": "logseq_append_marker",
                    "title": "Append AI clarification note",
                    "risk": "medium",
                    "payload": {"marker": "**[AI注]**", "content": f"Clarify: {answer[:120] or title}"},
                    "confidence": 0.78,
                    "reasoning_summary": "将本次澄清结果沉淀为 AI 注。",
                }
            )
        if "成果" in answer:
            candidates.append(
                {
                    "proposal_type": "result_marker",
                    "title": "Add result marker after completion",
                    "risk": "medium",
                    "payload": {"marker": "**[成果]**", "content": "完成后补充成果沉淀。"},
                    "confidence": 0.7,
                    "reasoning_summary": "用户提到需要成果标注。",
                }
            )
        return ProviderResult(
            summary="Mock provider generated proposal candidates.",
            proposal_candidates=candidates,
            classification_suggestion="action",
            confidence=max(candidate.get("confidence", 0.0) for candidate in candidates),
            reasoning_summary="mock provider rule-based summary",
        )


class DryRunProvider(ProposalProvider):
    def preview_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return {"dry_run": True, "provider_config": self.config.masked(), "payload": payload}

    def generate(self, payload: Dict[str, Any]) -> ProviderResult:
        return ProviderResult(
            summary="Dry-run only; no remote request was sent.",
            proposal_candidates=[],
            confidence=0.0,
            reasoning_summary="payload preview only",
            raw_summary={"dry_run": True, "provider_config": self.config.masked(), "payload_keys": sorted(payload.keys())},
        )


class InvalidJsonProvider(ProposalProvider):
    def generate(self, payload: Dict[str, Any]) -> ProviderResult:
        return parse_provider_response("this is not json")


class OpenAICompatibleProvider(ProposalProvider):
    def generate(self, payload: Dict[str, Any]) -> ProviderResult:
        if not self.config.base_url:
            raise ProviderConfigError("Provider base URL is required for remote provider.")
        if not self.config.api_key:
            raise ProviderConfigError(f"Provider API key is required. Set {PROVIDER_API_KEY_ENV} or .env.local.")
        if not self.config.model:
            raise ProviderConfigError("Provider model is required for remote provider.")
        url = self.config.base_url.rstrip("/")
        if not url.endswith("/chat/completions"):
            url = f"{url}/chat/completions"
        body = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system_prompt(self.config.prompt_version)},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            "temperature": 0.2,
            "max_tokens": self.config.max_tokens,
            "response_format": {"type": "json_object"},
        }
        request = urllib.request.Request(
            url,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.config.api_key}"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise ProviderError(f"Provider HTTP error: {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise ProviderError(f"Provider request failed: {exc.reason}") from exc
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        return parse_provider_response(content)


def config_from_settings(settings: Settings, override_name: Optional[str] = None) -> ProviderConfig:
    local_env = load_local_env()
    api_key = os.environ.get(PROVIDER_API_KEY_ENV) or local_env.get(PROVIDER_API_KEY_ENV) or settings.provider_api_key
    return ProviderConfig(
        name=override_name or settings.provider_name,
        base_url=settings.provider_base_url,
        api_key=api_key,
        model=settings.provider_model,
        timeout=settings.provider_timeout,
        max_tokens=settings.provider_max_tokens,
        prompt_version=settings.provider_prompt_version,
    )


def provider_from_settings(settings: Settings, override_name: Optional[str] = None) -> ProposalProvider:
    config = config_from_settings(settings, override_name=override_name)
    name = (config.name or "mock").lower()
    if name in {"mock", "rule_based", "rule-based"}:
        return MockProvider(config)
    if name in {"dry-run", "dry_run", "dryrun"}:
        return DryRunProvider(config)
    if name in {"invalid-json", "invalid_json"}:
        return InvalidJsonProvider(config)
    if name in {"openai", "openai-compatible", "deepseek", "remote"}:
        return OpenAICompatibleProvider(config)
    raise ProviderConfigError(f"Unsupported provider: {config.name}")


def parse_provider_response(content: str) -> ProviderResult:
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ProviderResponseError("Provider response was not valid JSON.") from exc
    if not isinstance(data, dict):
        raise ProviderResponseError("Provider response must be a JSON object.")
    candidates = data.get("proposal_candidates", [])
    if candidates is None:
        candidates = []
    if not isinstance(candidates, list):
        raise ProviderResponseError("provider proposal_candidates must be a list.")
    normalized: List[Dict[str, Any]] = []
    for item in candidates:
        if isinstance(item, dict) and item.get("proposal_type") and isinstance(item.get("payload", {}), dict):
            normalized.append(item)
    return ProviderResult(
        summary=str(data.get("summary") or "Provider returned proposals."),
        proposal_candidates=normalized,
        classification_suggestion=data.get("classification_suggestion"),
        gtd_state_suggestion=data.get("gtd_state_suggestion"),
        project_suggestion=data.get("project_suggestion"),
        marker_suggestion=data.get("marker_suggestion"),
        annotation_suggestion=data.get("annotation_suggestion"),
        confidence=_float_or_none(data.get("confidence")),
        reasoning_summary=data.get("reasoning_summary"),
        needs_user_confirmation=bool(data.get("needs_user_confirmation", True)),
        raw_summary={
            "summary": data.get("summary"),
            "candidate_count": len(normalized),
            "has_reasoning_summary": bool(data.get("reasoning_summary")),
        },
    )


def system_prompt(prompt_version: str) -> str:
    return (
        "You generate structured proposal candidates for a personal action system. "
        "Return JSON only. Do not modify facts. Do not write Logseq. "
        "Use concise reasoning_summary, never hidden chain-of-thought. "
        f"Prompt version: {prompt_version}."
    )


def mask_secret(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    if len(value) <= 8:
        return "***"
    return f"{value[:3]}...{value[-4:]}"


def _float_or_none(value: Any) -> Optional[float]:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None
