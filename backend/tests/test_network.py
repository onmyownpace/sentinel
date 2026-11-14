"""Address rules for browser checks. These tests never open a socket."""

import ipaddress

import pytest

from app.services.network import (
    BLOCKED_REQUEST,
    UNSAFE_TARGET,
    UNRESOLVED_HOST,
    TargetNotAllowed,
    classify_browser_url,
    ensure_public_http_url,
)


async def _public(_host: str, _port: int):
    return [ipaddress.ip_address("8.8.8.8")]


async def _private(_host: str, _port: int):
    return [ipaddress.ip_address("192.168.0.8")]


async def _mixed(_host: str, _port: int):
    return [ipaddress.ip_address("8.8.8.8"), ipaddress.ip_address("10.0.0.4")]


async def _unresolved(_host: str, _port: int):
    raise OSError("resolver internals")


async def _unused(_host: str, _port: int):
    raise AssertionError("a literal address must not be resolved")


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/",
        "http://127.0.0.1:3000/admin",
        "http://localhost/",
        "http://localhost./",
        "http://app.localhost/",
        "http://printer.local/",
        "http://db.internal/",
        "http://metadata.google.internal/computeMetadata/v1/",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.1.2.3/",
        "http://192.168.1.20/",
        "http://172.16.0.4/",
        "http://100.64.0.5/",
        "http://[::1]/",
        "http://[::ffff:127.0.0.1]/",
        "http://224.0.0.1/",
        "http://203.0.113.5/",
        "http://2130706433/",
        "http://0177.0.0.1/",
        "http://0x7f.0.0.1/",
        "ftp://8.8.8.8/",
        "file:///etc/passwd",
        "javascript:alert(1)",
        "http://user:secret@8.8.8.8/",
    ],
)
async def test_restricted_targets_are_rejected(url: str) -> None:
    with pytest.raises(TargetNotAllowed, match=UNSAFE_TARGET):
        await ensure_public_http_url(url, resolve=_unused)


async def test_a_public_literal_is_allowed_without_dns() -> None:
    await ensure_public_http_url("https://8.8.8.8/status", resolve=_unused)


async def test_a_hostname_is_allowed_only_when_every_address_is_public() -> None:
    await ensure_public_http_url("https://allowed.invalid/status", resolve=_public)

    with pytest.raises(TargetNotAllowed, match=UNSAFE_TARGET):
        await ensure_public_http_url("https://rebind.invalid/", resolve=_private)

    with pytest.raises(TargetNotAllowed, match=UNSAFE_TARGET):
        await ensure_public_http_url("https://split.invalid/", resolve=_mixed)


async def test_an_unresolved_host_does_not_include_the_resolver_error() -> None:
    with pytest.raises(TargetNotAllowed, match=UNRESOLVED_HOST) as caught:
        await ensure_public_http_url("https://missing.invalid/", resolve=_unresolved)

    assert "resolver internals" not in str(caught.value)


@pytest.mark.parametrize(
    ("url", "decision"),
    [
        ("data:text/plain,hello", "skip"),
        ("blob:https://allowed.invalid/id", "skip"),
        ("https://8.8.8.8/page", "allow"),
        ("http://10.0.0.9/page", "block"),
        ("file:///C:/secret.txt", "block"),
        ("javascript:alert(1)", "block"),
    ],
)
async def test_browser_urls_are_classified_before_a_request_is_sent(url: str, decision: str) -> None:
    assert await classify_browser_url(url, resolve=_unused) == decision


def test_blocked_request_summary_does_not_mention_headers() -> None:
    assert "header" not in BLOCKED_REQUEST.lower()
    assert "cookie" not in BLOCKED_REQUEST.lower()
