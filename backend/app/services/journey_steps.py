"""Validate and normalize declarative BROW-2 journey steps.

Portfolio-simple: navigate, fill, click, and a few asserts. Not a Selenium IDE.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import urlsplit

from app.core.urls import normalize_base_url

JourneyOp = Literal[
    "navigate",
    "fill",
    "click",
    "assert_text",
    "assert_url_contains",
    "assert_visible",
]

_ALLOWED_OPS = {
    "navigate",
    "fill",
    "click",
    "assert_text",
    "assert_url_contains",
    "assert_visible",
}
_MAX_STEPS = 8
_MAX_SELECTOR = 200
_MAX_VALUE = 500
_MAX_NAME = 120


@dataclass(frozen=True)
class JourneyStep:
    op: JourneyOp
    url: str | None = None
    selector: str | None = None
    value: str | None = None

    def to_dict(self) -> dict[str, str]:
        data: dict[str, str] = {"op": self.op}
        if self.url is not None:
            data["url"] = self.url
        if self.selector is not None:
            data["selector"] = self.selector
        if self.value is not None:
            data["value"] = self.value
        return data


def validate_journey_name(name: str) -> str:
    cleaned = name.strip()
    if not cleaned:
        raise ValueError("Name is required.")
    if len(cleaned) > _MAX_NAME:
        raise ValueError(f"Name must be {_MAX_NAME} characters or fewer.")
    return cleaned


def validate_and_normalize_steps(
    raw_steps: list[Any],
    *,
    website_base_url: str,
) -> list[JourneyStep]:
    """Parse steps and resolve relative navigate URLs against the website base."""
    if not isinstance(raw_steps, list) or not raw_steps:
        raise ValueError("Provide at least one step.")
    if len(raw_steps) > _MAX_STEPS:
        raise ValueError(f"A journey may have at most {_MAX_STEPS} steps.")

    base = normalize_base_url(website_base_url)
    steps: list[JourneyStep] = []
    for index, item in enumerate(raw_steps):
        if not isinstance(item, dict):
            raise ValueError(f"Step {index + 1} must be an object.")
        op = str(item.get("op", "")).strip().lower()
        if op not in _ALLOWED_OPS:
            raise ValueError(
                f"Step {index + 1} has unknown op. Allowed: {', '.join(sorted(_ALLOWED_OPS))}."
            )
        if index == 0 and op != "navigate":
            raise ValueError("The first step must be navigate.")

        if op == "navigate":
            url = _require_text(item.get("url"), "url", index)
            absolute = _resolve_navigate_url(url, base)
            steps.append(JourneyStep(op="navigate", url=absolute))
            continue

        if op == "fill":
            selector = _require_selector(item.get("selector"), index)
            value = _require_text(item.get("value"), "value", index)
            steps.append(JourneyStep(op="fill", selector=selector, value=value))
            continue

        if op == "click":
            selector = _require_selector(item.get("selector"), index)
            steps.append(JourneyStep(op="click", selector=selector))
            continue

        if op == "assert_text":
            selector = _require_selector(item.get("selector"), index)
            value = _require_text(item.get("value"), "value", index)
            steps.append(JourneyStep(op="assert_text", selector=selector, value=value))
            continue

        if op == "assert_url_contains":
            value = _require_text(item.get("value"), "value", index)
            steps.append(JourneyStep(op="assert_url_contains", value=value))
            continue

        if op == "assert_visible":
            selector = _require_selector(item.get("selector"), index)
            steps.append(JourneyStep(op="assert_visible", selector=selector))
            continue

    return steps


def steps_as_json(steps: list[JourneyStep]) -> list[dict[str, str]]:
    return [step.to_dict() for step in steps]


def _require_selector(value: object, index: int) -> str:
    text = _require_text(value, "selector", index)
    if len(text) > _MAX_SELECTOR:
        raise ValueError(f"Step {index + 1} selector is too long.")
    return text


def _require_text(value: object, field: str, index: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Step {index + 1} requires {field}.")
    cleaned = value.strip()
    if len(cleaned) > _MAX_VALUE:
        raise ValueError(f"Step {index + 1} {field} is too long.")
    return cleaned


def _resolve_navigate_url(url: str, website_base_url: str) -> str:
    if url.startswith("/"):
        # Keep the registered base path prefix (portfolio-simple join).
        return website_base_url.rstrip("/") + url
    try:
        parsed = urlsplit(url)
    except ValueError as exc:
        raise ValueError("Navigate URL must be an absolute HTTP(S) URL or a path.") from exc
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Navigate URL must be an absolute HTTP(S) URL or a path starting with /.")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("Navigate URL must not include a username or password.")
    host = parsed.hostname.lower().rstrip(".")
    if ":" in host:
        host = f"[{host}]"
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Navigate URL has an invalid port.") from exc
    if port is not None and not (
        (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    ):
        host = f"{host}:{port}"
    path = parsed.path or ""
    query = f"?{parsed.query}" if parsed.query else ""
    rebuilt = f"{scheme}://{host}{path}{query}"
    if len(rebuilt) > 2048:
        raise ValueError("Navigate URL is too long.")
    return rebuilt
