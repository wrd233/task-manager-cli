import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from task_manager_cli.config.settings import PROVIDER_API_KEY_ENV, Settings, load_local_env
from task_manager_cli.core.errors import ConfigError, TaskManagerError


class ProviderError(TaskManagerError):
    pass


class ProviderConfigError(ConfigError):
    pass


class ProviderResponseError(ProviderError):
    pass


ALLOWED_PROVIDER_TYPES = {
    "add_marker",
    "change_task_marker",
    "add_annotation",
    "change_state",
    "add_relation",
    "create_mini_project",
    "add_result_marker",
    "logseq_append_marker",
    "logseq_task_marker",
    "annotation",
    "status_change",
    "relation_change",
    "result_marker",
    "link_to_project",
    "link_to_project_node",
    "link_idea_to_project",
    "link_resource_to_project",
    "promote_to_mini_project",
    "attach_to_mini_project",
    "create_project_node",
    "link_object_to_node",
    "append_block_ref_to_node",
    "convert_idea_to_task",
    "mark_object_as_resource",
    "mark_object_as_result",
    "archive_project_item",
}
ALLOWED_RISKS = {"low", "medium", "high"}
TYPE_MAP = {
    "add_marker": "logseq_append_marker",
    "change_task_marker": "logseq_task_marker",
    "add_annotation": "annotation",
    "change_state": "status_change",
    "add_relation": "relation_change",
    "create_mini_project": "create_mini_project",
    "add_result_marker": "result_marker",
    "link_to_project": "link_to_project",
    "link_to_project_node": "link_to_project_node",
    "link_idea_to_project": "link_idea_to_project",
    "link_resource_to_project": "link_resource_to_project",
    "promote_to_mini_project": "promote_to_mini_project",
    "attach_to_mini_project": "attach_to_mini_project",
    "create_project_node": "create_project_node",
    "link_object_to_node": "link_object_to_node",
    "append_block_ref_to_node": "append_block_ref_to_node",
    "convert_idea_to_task": "convert_idea_to_task",
    "mark_object_as_resource": "mark_object_as_resource",
    "mark_object_as_result": "mark_object_as_result",
    "archive_project_item": "archive_project_item",
}


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
    questions_for_user: List[Dict[str, Any]] = field(default_factory=list)
    raw_summary: Dict[str, Any] = field(default_factory=dict)
    usage: Dict[str, Any] = field(default_factory=dict)
    latency_ms: Optional[int] = None
    response_id: Optional[str] = None


class ProposalProvider:
    def __init__(self, config: ProviderConfig):
        self.config = config

    def preview_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return payload

    def generate(self, payload: Dict[str, Any]) -> ProviderResult:
        raise NotImplementedError


class MockProvider(ProposalProvider):
    def generate(self, payload: Dict[str, Any]) -> ProviderResult:
        if payload.get("clarify_mode") == "ai_questions":
            title = payload.get("item", {}).get("title", "这个条目")
            return ProviderResult(
                summary="Mock provider generated questions for user.",
                proposal_candidates=[],
                confidence=0.0,
                reasoning_summary="mock provider questions only",
                questions_for_user=[
                    {"question": f"这个条目「{title}」下一步最小动作是什么？", "why": "identify_next_action"},
                    {"question": "它是否依赖外部人或条件？", "why": "waiting_boundary"},
                ],
                raw_summary={"questions_for_user_count": 2},
            )
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
            project_context = payload.get("short_context", {}).get("project_context") or {}
            project_id = (project_context.get("project") or {}).get("id")
            if project_id and ("项目" in answer or "project" in answer.lower() or "纳管" in answer):
                candidates.append(
                    {
                        "proposal_type": "link_to_project",
                        "title": "Link item to project",
                        "risk": "low",
                        "payload": {
                            "relation_type": "belongs_to",
                            "target_project_id": project_id,
                            "target_project_title": (project_context.get("project") or {}).get("title"),
                            "confidence": 0.78,
                            "source_evidence": ["clarify_project_context"],
                            "writeback_suggested": False,
                        },
                        "confidence": 0.78,
                        "reasoning_summary": "用户回答和项目上下文显示该条目适合纳管到项目。",
                    }
                )
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
        started = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise ProviderError(f"Provider HTTP error: {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise ProviderError(f"Provider request failed: {exc.reason}") from exc
        latency_ms = int((time.monotonic() - started) * 1000)
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        result = parse_provider_response(content)
        result.latency_ms = latency_ms
        result.usage = data.get("usage") or {}
        result.response_id = data.get("id")
        return result


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
    content = extract_json_object(content)
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
    for index, item in enumerate(candidates):
        normalized.append(normalize_candidate(item, index=index))
    classification = data.get("item_classification") or {}
    if classification and not isinstance(classification, dict):
        raise ProviderResponseError("item_classification must be an object.")
    questions = data.get("questions_for_user") or []
    if not isinstance(questions, list):
        raise ProviderResponseError("questions_for_user must be a list.")
    warnings = data.get("warnings") or []
    if not isinstance(warnings, list):
        raise ProviderResponseError("warnings must be a list.")
    return ProviderResult(
        summary=str(data.get("summary") or "Provider returned proposals."),
        proposal_candidates=normalized,
        classification_suggestion=data.get("classification_suggestion") or classification.get("primary_state"),
        gtd_state_suggestion=data.get("gtd_state_suggestion"),
        project_suggestion=data.get("project_suggestion"),
        marker_suggestion=data.get("marker_suggestion"),
        annotation_suggestion=data.get("annotation_suggestion"),
        confidence=_float_or_none(data.get("confidence") if data.get("confidence") is not None else classification.get("confidence")),
        reasoning_summary=data.get("reasoning_summary") or classification.get("reason"),
        needs_user_confirmation=bool(data.get("needs_user_confirmation", True)),
        raw_summary={
            "summary": data.get("summary"),
            "candidate_count": len(normalized),
            "has_reasoning_summary": bool(data.get("reasoning_summary")),
            "schema": "clarify_v1_zh",
            "questions_for_user_count": len(questions),
            "questions_for_user": questions[:3],
            "warnings": warnings[:5],
            "item_classification": {
                "primary_state": classification.get("primary_state"),
                "confidence": classification.get("confidence"),
                "semantic_tags": classification.get("semantic_tags", [])[:8] if isinstance(classification.get("semantic_tags", []), list) else [],
            },
        },
        questions_for_user=questions[:3],
    )


def system_prompt(prompt_version: str) -> str:
    return (
        "你是个人行动系统 task-manager-cli 的 Clarify proposal 生成器。你不是任务管理器，"
        "不能直接修改事实，不能直接写 Logseq，只能输出可审核的 Proposal candidates。"
        "请保守、短、准：不要过度分类，不要把 reference 当 action，不要把 idea 强行转 task，"
        "不要生成过多 AI 注，不要建议删除/合并/大规模重排。只输出 JSON object，禁止输出 markdown，"
        "禁止输出 chain-of-thought，只允许简短 reason。"
        "JSON schema: {summary,item_classification:{primary_state,semantic_tags,confidence,reason},"
        "proposal_candidates:[{type,risk,target,content,confidence,reason,needs_user_confirmation}],"
        "questions_for_user:[{question,why}],warnings:[]}。"
        "primary_state must be one of inbox,next,waiting,someday,reference,idea,done,dropped,unknown. "
        "proposal type must be one of add_marker,change_task_marker,add_annotation,change_state,add_relation,"
        "create_mini_project,add_result_marker,link_to_project,link_to_project_node,link_idea_to_project,"
        "link_resource_to_project,promote_to_mini_project,attach_to_mini_project. risk must be low,medium,high. "
        "For this implementation, add_marker, change_task_marker, add_annotation, and add_result_marker are the most usable. "
        "For Round 3 project membership, prefer low-risk link_to_project/link_to_project_node proposals when evidence is explicit; "
        "use promote_to_mini_project only when an item clearly needs multiple action items. "
        "Never propose moving, deleting, merging, or rewriting project tree blocks. "
        "Avoid change_state unless the user explicitly asks for an internal-only state proposal. "
        "If the user asks to leave an AI note, use add_marker with content and risk medium. "
        "target must always be a JSON object; use {} if unsure, never use string/null/array. "
        "For smoke tests or insufficient context, return proposal_candidates: []. "
        f"Prompt version: {prompt_version}."
    )


def normalize_candidate(item: Any, index: int = 0) -> Dict[str, Any]:
    if not isinstance(item, dict):
        raise ProviderResponseError(f"proposal candidate #{index} must be an object.")
    raw_type = item.get("type") or item.get("proposal_type")
    if raw_type not in ALLOWED_PROVIDER_TYPES:
        raise ProviderResponseError(f"Unsupported proposal candidate type: {raw_type}")
    risk = item.get("risk") or "medium"
    if risk not in ALLOWED_RISKS:
        raise ProviderResponseError(f"Unsupported proposal candidate risk: {risk}")
    target = item.get("target") or {}
    if target is not None and not isinstance(target, dict):
        raise ProviderResponseError("proposal candidate target must be an object.")
    proposal_type = TYPE_MAP.get(raw_type, raw_type)
    payload = item.get("payload")
    if payload is not None and not isinstance(payload, dict):
        raise ProviderResponseError("proposal candidate payload must be an object.")
    if payload is None:
        payload = payload_from_schema_candidate(raw_type, item)
    return {
        "proposal_type": proposal_type,
        "title": item.get("title") or title_for_candidate(raw_type, item.get("content")),
        "risk": risk,
        "target": target or {},
        "payload": payload,
        "confidence": _float_or_none(item.get("confidence")),
        "reasoning_summary": item.get("reason") or item.get("reasoning_summary"),
        "needs_user_confirmation": bool(item.get("needs_user_confirmation", True)),
    }


def payload_from_schema_candidate(raw_type: str, item: Dict[str, Any]) -> Dict[str, Any]:
    content = str(item.get("content") or "").strip()
    if raw_type == "add_marker":
        marker = item.get("marker") or "**[AI注]**"
        return {"marker": marker, "content": content}
    if raw_type == "add_result_marker":
        marker = item.get("marker") or "**[成果]**"
        return {"marker": marker, "content": content}
    if raw_type == "change_task_marker":
        marker = (item.get("new_marker") or content or "WAITING").upper()
        return {"new_marker": marker}
    if raw_type == "add_annotation":
        return {"content": content, "author": "provider", "annotation_type": "comment"}
    if raw_type == "change_state":
        return {"status": content or item.get("status")}
    if raw_type == "add_relation":
        return {"relation_type": item.get("relation_type"), "target": item.get("target")}
    if raw_type == "create_mini_project":
        return {"content": content}
    if raw_type in {"link_to_project", "link_idea_to_project", "link_resource_to_project", "link_to_project_node", "attach_to_mini_project"}:
        target = item.get("target") or {}
        return {
            "relation_type": item.get("relation_type") or "belongs_to",
            "target_project_id": target.get("project_id") or target.get("target_project_id") or item.get("target_project_id"),
            "target_project_title": target.get("project_title") or item.get("target_project_title"),
            "target_project_node_id": target.get("project_node_id") or target.get("target_project_node_id") or item.get("target_project_node_id"),
            "confidence": _float_or_none(item.get("confidence")),
            "source_evidence": item.get("source_evidence") or ([item.get("reason")] if item.get("reason") else []),
            "writeback_suggested": bool(item.get("writeback_suggested", False)),
        }
    if raw_type == "promote_to_mini_project":
        return {
            "suggested_mini_project_title": content or item.get("title"),
            "source_object_id": (item.get("target") or {}).get("object_id"),
            "writeback_suggested": bool(item.get("writeback_suggested", False)),
        }
    return dict(item.get("payload") or {})


def title_for_candidate(raw_type: str, content: Optional[str]) -> str:
    names = {
        "add_marker": "Add Logseq marker",
        "change_task_marker": "Change task marker",
        "add_annotation": "Add internal annotation",
        "change_state": "Change state",
        "add_relation": "Add relation",
        "create_mini_project": "Create mini project",
        "add_result_marker": "Add result marker",
        "link_to_project": "Link to project",
        "link_to_project_node": "Link to project node",
        "link_idea_to_project": "Link idea to project",
        "link_resource_to_project": "Link resource to project",
        "promote_to_mini_project": "Promote to mini project",
        "attach_to_mini_project": "Attach to mini project",
    }
    base = names.get(raw_type, "Provider proposal")
    return f"{base}: {str(content)[:40]}" if content else base


def mask_secret(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    if len(value) <= 8:
        return "***"
    return f"{value[:3]}...{value[-4:]}"


def extract_json_object(content: str) -> str:
    text = (content or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text).strip()
    if text.startswith("{") and text.endswith("}"):
        return text
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return text[start : end + 1]
    return text


def _float_or_none(value: Any) -> Optional[float]:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None
