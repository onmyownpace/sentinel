"""BROW-1 screenshot storage and check API (fake runner, no Chromium)."""

from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.services.results import CheckObservation
from app.services.screenshots import clamp_png_bytes, write_screenshot

# 1x1 transparent PNG
_TINY_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
)


class ScriptedRunner:
    def __init__(self, observations: list[CheckObservation]) -> None:
        self.observations = list(observations)

    async def run(self, url: str) -> CheckObservation:
        if not self.observations:
            raise AssertionError("runner called more times than scripted")
        return self.observations.pop(0)


def _observation(**overrides) -> CheckObservation:
    values: dict = {
        "outcome": "success",
        "http_status": 200,
        "page_title": "Shot",
        "final_url": "http://8.8.8.8/shot",
        "duration_ms": 90,
        "console_errors": (),
        "failed_requests": (),
        "error_message": None,
        "screenshot_png": None,
    }
    values.update(overrides)
    return CheckObservation(**values)


def test_clamp_rejects_oversized_and_non_png() -> None:
    assert clamp_png_bytes(_TINY_PNG, max_bytes=len(_TINY_PNG)) == _TINY_PNG
    assert clamp_png_bytes(b"not-a-png", max_bytes=1000) is None
    assert clamp_png_bytes(_TINY_PNG + b"x" * 1000, max_bytes=len(_TINY_PNG)) is None


def test_write_screenshot_round_trip(tmp_path: Path) -> None:
    check_id = uuid4()
    name = write_screenshot(tmp_path, check_id, _TINY_PNG, max_bytes=10_000)
    assert name == f"{check_id}.png"
    assert (tmp_path / name).read_bytes() == _TINY_PNG


def test_check_stores_and_serves_screenshot(registry_client: TestClient, tmp_path: Path, monkeypatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "screenshot_dir", str(tmp_path))
    # Clear cached settings consumers that read screenshot_root via property — property uses screenshot_dir.
    runner = ScriptedRunner([_observation(screenshot_png=_TINY_PNG)])
    registry_client.app.state.check_runner = runner
    created = registry_client.post(
        "/api/websites",
        json={"name": "Shot site", "base_url": f"http://8.8.8.8/{uuid4().hex}"},
    )
    assert created.status_code == 201
    website_id = created.json()["id"]
    try:
        check = registry_client.post(
            f"/api/websites/{website_id}/checks",
            json={"authorized": True},
        )
        assert check.status_code == 201
        body = check.json()
        assert body["has_screenshot"] is True
        check_id = body["id"]

        image = registry_client.get(f"/api/checks/{check_id}/screenshot")
        assert image.status_code == 200
        assert image.headers["content-type"].startswith("image/png")
        assert image.content.startswith(b"\x89PNG")

        fetched = registry_client.get(f"/api/checks/{check_id}")
        assert fetched.status_code == 200
        assert fetched.json()["has_screenshot"] is True
    finally:
        registry_client.delete(f"/api/websites/{website_id}")


def test_check_without_screenshot_returns_404_image(registry_client: TestClient) -> None:
    runner = ScriptedRunner([_observation(screenshot_png=None)])
    registry_client.app.state.check_runner = runner
    created = registry_client.post(
        "/api/websites",
        json={"name": "No shot", "base_url": f"http://8.8.8.8/{uuid4().hex}"},
    )
    assert created.status_code == 201
    website_id = created.json()["id"]
    try:
        check = registry_client.post(
            f"/api/websites/{website_id}/checks",
            json={"authorized": True},
        )
        assert check.status_code == 201
        assert check.json()["has_screenshot"] is False
        missing = registry_client.get(f"/api/checks/{check.json()['id']}/screenshot")
        assert missing.status_code == 404
    finally:
        registry_client.delete(f"/api/websites/{website_id}")
