import json

import pytest

from task_manager_cli.config.settings import Settings
from task_manager_cli.core.errors import ConfigError
from task_manager_cli.providers.base import (
    DryRunProvider,
    OpenAICompatibleProvider,
    ProviderConfig,
    ProviderResponseError,
    parse_provider_response,
    provider_from_settings,
)
from task_manager_cli.providers.service import ProviderService


def test_mock_and_dry_run_provider_boundaries(tmp_path):
    settings = Settings(app_dir=tmp_path / "app", database_path=tmp_path / "tm.sqlite3", provider_name="mock")
    provider = provider_from_settings(settings)
    result = provider.generate({"item": {"title": "任务"}, "answers": [{"answer": "需要等待别人"}]})
    assert result.proposal_candidates[0]["proposal_type"] == "logseq_task_marker"

    dry = provider_from_settings(settings, override_name="dry-run")
    assert isinstance(dry, DryRunProvider)
    preview = dry.preview_payload({"x": "y"})
    assert preview["dry_run"] is True


def test_remote_provider_missing_config_has_clear_error():
    provider = OpenAICompatibleProvider(ProviderConfig(name="remote"))
    with pytest.raises(ConfigError, match="base URL"):
        provider.generate({"item": {"title": "x"}})
    provider = OpenAICompatibleProvider(ProviderConfig(name="remote", base_url="https://api.example.invalid/v1", model="m"))
    with pytest.raises(ConfigError, match="API key"):
        provider.generate({"item": {"title": "x"}})


def test_provider_response_schema_and_invalid_json():
    content = json.dumps(
        {
            "summary": "ok",
            "proposal_candidates": [
                {
                    "proposal_type": "logseq_append_marker",
                    "title": "Add AI note",
                    "payload": {"marker": "**[AI注]**", "content": "note"},
                    "risk": "medium",
                }
            ],
            "confidence": 0.8,
            "reasoning_summary": "short",
        }
    )
    parsed = parse_provider_response(content)
    assert parsed.proposal_candidates[0]["title"] == "Add AI note"
    fenced = parse_provider_response("```json\n" + content + "\n```")
    assert fenced.proposal_candidates[0]["title"] == "Add AI note"
    with pytest.raises(ProviderResponseError):
        parse_provider_response("not json")


def test_provider_response_new_schema_and_whitelist_validation():
    content = json.dumps(
        {
            "summary": "ok",
            "item_classification": {"primary_state": "waiting", "semantic_tags": ["needs_clarify"], "confidence": 0.7, "reason": "short"},
            "proposal_candidates": [
                {
                    "type": "change_task_marker",
                    "risk": "medium",
                    "target": {"object_id": "1"},
                    "content": "WAITING",
                    "confidence": 0.76,
                    "reason": "depends on someone else",
                    "needs_user_confirmation": True,
                }
            ],
            "questions_for_user": [{"question": "who blocks it?", "why": "waiting"}],
            "warnings": [],
        }
    )
    parsed = parse_provider_response(content)
    assert parsed.classification_suggestion == "waiting"
    assert parsed.proposal_candidates[0]["proposal_type"] == "logseq_task_marker"
    assert parsed.proposal_candidates[0]["payload"]["new_marker"] == "WAITING"
    assert parsed.raw_summary["questions_for_user_count"] == 1
    with pytest.raises(ProviderResponseError, match="Unsupported proposal candidate type"):
        parse_provider_response(json.dumps({"proposal_candidates": [{"type": "delete_everything", "risk": "high", "target": {}, "content": "x"}]}))
    with pytest.raises(ProviderResponseError, match="risk"):
        parse_provider_response(json.dumps({"proposal_candidates": [{"type": "add_marker", "risk": "danger", "target": {}, "content": "x"}]}))
    with pytest.raises(ProviderResponseError, match="target"):
        parse_provider_response(json.dumps({"proposal_candidates": [{"type": "add_marker", "risk": "low", "target": "bad", "content": "x"}]}))


def test_provider_response_round3_project_membership_types():
    content = json.dumps(
        {
            "summary": "project membership",
            "proposal_candidates": [
                {
                    "type": "link_to_project_node",
                    "risk": "low",
                    "target": {"object_id": "7", "project_id": 2, "project_node_id": "block:node"},
                    "content": "挂到项目工作流",
                    "confidence": 0.81,
                    "reason": "明确引用项目和节点",
                    "needs_user_confirmation": True,
                },
                {
                    "type": "promote_to_mini_project",
                    "risk": "medium",
                    "target": {"object_id": "7"},
                    "content": "整理签证材料",
                    "confidence": 0.68,
                    "reason": "需要多个行动项",
                },
            ],
        }
    )
    parsed = parse_provider_response(content)
    first = parsed.proposal_candidates[0]
    assert first["proposal_type"] == "link_to_project_node"
    assert first["payload"]["target_project_id"] == 2
    assert first["payload"]["target_project_node_id"] == "block:node"
    assert parsed.proposal_candidates[1]["proposal_type"] == "promote_to_mini_project"


def test_provider_doctor_no_call_and_env_local_config(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env.local").write_text(
        "TM_PROVIDER=deepseek\n"
        "TM_PROVIDER_BASE_URL=https://api.example.invalid/v1\n"
        "TM_PROVIDER_MODEL=model-placeholder\n"
        "TM_PROVIDER_API_KEY=sk-test-placeholder\n",
        encoding="utf-8",
    )
    settings = Settings.load(tmp_path / "missing-config.json")
    data = ProviderService(settings).doctor(no_call=True)
    assert data["provider"]["name"] == "deepseek"
    assert data["provider"]["api_key_present"] is True
    assert data["provider"]["api_key"] != "sk-test-placeholder"
    assert data["checks"]["no_call"] is True
