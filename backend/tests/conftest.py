"""Shared fixtures for the API tests."""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client():
    """HTTP client wrapped around a fresh app. Entering the context runs startup."""
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client
