"""The n8n follow-up file is data, so the test can read it without starting n8n."""

import json
from pathlib import Path


def workflow() -> dict:
    path = Path(__file__).resolve().parents[2] / "n8n" / "workflows" / "failed-check-follow-up.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_follow_up_workflow_only_reads_stored_checks() -> None:
    document = workflow()
    nodes = document["nodes"]
    by_name = {node["name"]: node for node in nodes}
    types = {node["type"] for node in nodes}

    assert document["active"] is False
    assert document["name"] == "Sentinel failed-check follow-up"
    assert "n8n-nodes-base.manualTrigger" in types
    assert "n8n-nodes-base.scheduleTrigger" not in types
    assert "n8n-nodes-base.cron" not in types

    http_nodes = [node for node in nodes if node["type"] == "n8n-nodes-base.httpRequest"]
    assert [node["parameters"]["method"] for node in http_nodes] == ["GET", "GET"]
    assert http_nodes[0]["parameters"]["url"].endswith("/api/websites")
    assert "/api/websites/{{ $json.id }}/checks?limit=1" in http_nodes[1]["parameters"]["url"]
    assert by_name["API address"]["parameters"]["assignments"]["assignments"][0]["value"] == (
        "http://host.docker.internal:8000"
    )

    rendered = json.dumps(document).lower()
    assert "authorized" not in rendered
    assert "openai" not in rendered
    assert "bearer " not in rendered
    assert "postgresql" not in rendered
    assert "password" not in rendered

    assert document["connections"]["Check failed"]["main"][1] == []
    assert document["connections"]["Check failed"]["main"][0][0]["node"] == "Notification draft"
    assert document["settings"]["executionOrder"] == "v1"
