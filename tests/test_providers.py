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
    with pytest.raises(ProviderResponseError):
        parse_provider_response("not json")
