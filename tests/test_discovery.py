from __future__ import annotations

import json

from alterios_mcp.client import encode_filter
from alterios_mcp.discovery import OBJECT_ROUTES, main, response_shape


def test_common_object_routes_are_registered() -> None:
    for kind in (
        "content_types",
        "views",
        "forms",
        "scripts",
        "diagrams",
        "fields",
        "reports",
        "contents",
        "tasks",
        "processes",
        "user_groups",
        "users",
        "groups",
        "helps",
    ):
        assert kind in OBJECT_ROUTES


def test_response_shape_omits_payload_values() -> None:
    assert response_shape({"token": "secret", "name": "demo"}) == {"type": "dict", "keys": ["name", "token"]}
    assert response_shape([[{"_id": "1"}]]) == {
        "type": "list",
        "length": 1,
        "first": {"type": "list", "length": 1, "first": {"type": "dict", "keys": ["_id"]}},
    }


def test_encode_filter_is_stable_url_encoded_json() -> None:
    assert encode_filter({}) == "%7B%7D"


def test_discovery_cli_lists_profiles_without_network(monkeypatch, capsys) -> None:
    monkeypatch.setenv("ALTERIOS_PROFILE", "primary")
    monkeypatch.setenv("ALTERIOS_PROFILES", "primary, secondary")
    monkeypatch.setenv("ALTERIOS_PRIMARY_BASE_URL", "https://primary.example")
    monkeypatch.setenv("ALTERIOS_PRIMARY_API_TOKEN", "primary-token")
    monkeypatch.setenv("ALTERIOS_SECONDARY_BASE_URL", "http://secondary.local")
    monkeypatch.setenv("ALTERIOS_SECONDARY_API_TOKEN", "secondary-token")

    assert main(["--profiles", "--profile", "secondary", "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["selected_profile"] == "secondary"
    assert [item["profile"] for item in payload["profiles"]] == ["secondary", "primary"]
    assert payload["profiles"][0]["selected"] is True
    assert payload["profiles"][0]["config"]["api_token"] == "<set>"
