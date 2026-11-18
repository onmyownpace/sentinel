"""ENG-1: CI workflow exists, runs free checks, and avoids secret dumping."""

from pathlib import Path


def workflow_text() -> str:
    path = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml"
    return path.read_text(encoding="utf-8")


def test_ci_workflow_runs_pytest_and_frontend_build() -> None:
    text = workflow_text()
    lowered = text.lower()

    assert "name: CI" in text
    assert "on:" in text
    assert "push:" in text
    assert "pull_request:" in text
    assert "postgres:16-alpine" in text
    assert "python -m pytest" in text
    assert "npm run typecheck" in text
    assert "npm run build" in text
    assert "analysis_provider: simulated" in lowered
    assert 'openai_api_key: ""' in lowered or "openai_api_key: ''" in lowered

    # Keep secrets out of logs — no env dumps or secret echoes.
    for banned in (
        "printenv",
        "env | sort",
        "env|sort",
        "echo ${{ secrets",
        "${{ secrets.",
        "secrets.openai",
        "actions_step_debug",
        "actions_runner_debug",
    ):
        assert banned.lower() not in lowered
