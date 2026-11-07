"""URL rules that do not need a database."""

import pytest

from app.core.urls import normalize_base_url


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://Example.COM/docs/", "https://example.com/docs"),
        ("https://example.com:443", "https://example.com"),
        ("http://example.com:80/a/", "http://example.com/a"),
        ("http://localhost:3000", "http://localhost:3000"),
        ("https://example.com/a/b", "https://example.com/a/b"),
        ("  https://example.com/path  ", "https://example.com/path"),
        ("http://[::1]/status/", "http://[::1]/status"),
    ],
)
def test_normalize_base_url(raw: str, expected: str) -> None:
    assert normalize_base_url(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        "example.com",
        "ftp://example.com",
        "javascript:alert(1)",
        "https://user:secret@example.com",
        "https://example.com/path?q=1",
        "https://example.com/path#section",
        "https://example.com/has space",
        "http://",
    ],
)
def test_normalize_base_url_rejects_non_http_targets(raw: str) -> None:
    with pytest.raises(ValueError):
        normalize_base_url(raw)
