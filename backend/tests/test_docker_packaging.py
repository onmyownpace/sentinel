"""ENG-4: Dockerfiles and compose app profile stay free of a job queue."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_api_and_web_dockerfiles_exist() -> None:
    api = (ROOT / "backend" / "Dockerfile").read_text(encoding="utf-8")
    web = (ROOT / "frontend" / "Dockerfile").read_text(encoding="utf-8")
    assert "uvicorn" in api.lower()
    assert "alembic upgrade head" in (ROOT / "backend" / "docker" / "entrypoint.sh").read_text(
        encoding="utf-8"
    )
    assert "npm run build" in web
    assert '"start"' in web
    assert "image: redis" not in api.lower()
    assert "celery" not in api.lower()


def test_compose_app_profile_preserves_volumes() -> None:
    text = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert 'profiles: ["app"]' in text
    assert "sentinel_postgres_data" in text
    assert "sentinel_n8n_data" in text
    assert "sentinel_api_screenshots" in text
    assert "build:" in text
    assert "./backend" in text
    assert "./frontend" in text
    # Default stack comment still warns against wiping volumes.
    assert "-v" in text
    assert "image: redis" not in text.lower()
    assert "image: celery" not in text.lower()
    assert "  api:" in text
    assert "  web:" in text
