"""The n8n follow-up file is data, so the test can read it without starting n8n."""

import json
from pathlib import Path


def workflow() -> dict:
    path = Path(__file__).resolve().parents[2] / "n8n" / "workflows" / "failed-check-follow-up.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_follow_up_workflow_reads_checks_and_gates_delivery() -> None:
    document = workflow()
    nodes = document["nodes"]
    by_name = {node["name"]: node for node in nodes}
    types = {node["type"] for node in nodes}

    assert document["active"] is False
    assert document["name"] == "Sentinel failed-check follow-up"
    assert "n8n-nodes-base.manualTrigger" in types
    assert "n8n-nodes-base.scheduleTrigger" not in types
    assert "n8n-nodes-base.cron" not in types

    assignments = {
        item["name"]: item["value"]
        for item in by_name["API address"]["parameters"]["assignments"]["assignments"]
    }
    assert assignments["apiBase"] == "http://host.docker.internal:8000"
    assert assignments["webhookUrl"] == ""
    assert assignments["automationToken"] == "change-me-automation-token"

    http_nodes = [node for node in nodes if node["type"] == "n8n-nodes-base.httpRequest"]
    assert [node["parameters"]["method"] for node in http_nodes] == ["GET", "GET", "POST"]
    assert http_nodes[0]["parameters"]["url"].endswith("/api/websites")
    assert "/api/websites/{{ $json.id }}/checks?limit=1" in http_nodes[1]["parameters"]["url"]
    for get_node in http_nodes[:2]:
        headers = get_node["parameters"]["headerParameters"]["parameters"]
        assert any(item["name"] == "X-Automation-Token" for item in headers)
    deliver = by_name["Deliver draft"]
    assert deliver["parameters"]["method"] == "POST"
    assert "webhookUrl" in deliver["parameters"]["url"]
    assert deliver.get("onError") == "continueRegularOutput"

    assert document["connections"]["Check failed"]["main"][1] == []
    assert document["connections"]["Check failed"]["main"][0][0]["node"] == "Notification draft"
    assert document["connections"]["Notification draft"]["main"][0][0]["node"] == "Webhook configured"
    assert document["connections"]["Webhook configured"]["main"][0][0]["node"] == "Deliver draft"
    assert document["connections"]["Webhook configured"]["main"][1] == []
    assert document["settings"]["executionOrder"] == "v1"

    draft_names = {
        item["name"]
        for item in by_name["Notification draft"]["parameters"]["assignments"]["assignments"]
    }
    assert "text" in draft_names

    rendered = json.dumps(document).lower()
    assert "authorized" not in rendered
    assert "openai.com" not in rendered
    assert "bearer " not in rendered
    assert "postgresql" not in rendered
    assert "password" not in rendered
    assert "gmail" not in rendered
    assert "sendemail" not in rendered
    assert "n8n-nodes-base.emailsend" not in types
