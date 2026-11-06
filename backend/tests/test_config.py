"""Configuration rules that the rest of the API relies on."""

import pytest
from pydantic import ValidationError

from app.core.config import get_settings


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
