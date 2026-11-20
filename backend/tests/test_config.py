"""Configuration rules that the rest of the API relies on."""

import pytest
from pydantic import ValidationError

from app.core.config import (
    DEFAULT_TOGETHER_MODEL,
    TOGETHER_API_HOST,
    get_settings,
)


def test_database_url_rejects_a_sync_driver(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://sentinel:sentinel@localhost:5432/sentinel",
    )
    get_settings.cache_clear()
    try:
        with pytest.raises(ValidationError):
            get_settings()
    finally:
        get_settings.cache_clear()


def test_together_api_key_maps_when_openai_key_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("TOGETHER_API_KEY", "together-alias-key-not-real")
    monkeypatch.setenv("ANALYSIS_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.together.ai/v1")
    monkeypatch.setenv("OPENAI_MODEL", "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo")
    get_settings.cache_clear()
    try:
        settings = get_settings()
        assert settings.openai_api_key == "together-alias-key-not-real"
        assert settings.analysis_base_host == TOGETHER_API_HOST
        assert settings.is_together_endpoint is True
        assert settings.effective_analysis_provider == "openai"
        assert settings.effective_analysis_model == "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo"
    finally:
        get_settings.cache_clear()


def test_openai_api_key_wins_over_together_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "openai-primary-key-not-real")
    monkeypatch.setenv("TOGETHER_API_KEY", "together-alias-key-not-real")
    monkeypatch.setenv("ANALYSIS_PROVIDER", "openai")
    get_settings.cache_clear()
    try:
        settings = get_settings()
        assert settings.openai_api_key == "openai-primary-key-not-real"
    finally:
        get_settings.cache_clear()


def test_together_base_url_substitutes_default_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANALYSIS_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "together-test-key-not-real")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.together.ai/v1")
    # Explicit stock OpenAI default (also covers a local .env that sets gpt-4o-mini).
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o-mini")
    get_settings.cache_clear()
    try:
        settings = get_settings()
        assert settings.openai_model == DEFAULT_TOGETHER_MODEL
        assert settings.analysis_base_host == "api.together.ai"
        assert settings.effective_analysis_model == DEFAULT_TOGETHER_MODEL
    finally:
        get_settings.cache_clear()


def test_explicit_together_model_is_preserved(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANALYSIS_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "together-test-key-not-real")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.together.ai/v1")
    monkeypatch.setenv("OPENAI_MODEL", "Qwen/Qwen2.5-7B-Instruct-Turbo")
    get_settings.cache_clear()
    try:
        settings = get_settings()
        assert settings.openai_model == "Qwen/Qwen2.5-7B-Instruct-Turbo"
    finally:
        get_settings.cache_clear()


def test_blank_openai_base_url_becomes_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_BASE_URL", "   ")
    get_settings.cache_clear()
    try:
        settings = get_settings()
        assert settings.openai_base_url is None
        assert settings.analysis_base_host is None
    finally:
        get_settings.cache_clear()
