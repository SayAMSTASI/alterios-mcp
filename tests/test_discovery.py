from __future__ import annotations

from alterios_mcp.client import encode_filter
from alterios_mcp.discovery import OBJECT_ROUTES, response_shape


def test_common_object_routes_are_registered() -> None:
    for kind in ("content_types", "views", "forms", "scripts", "diagrams", "reports", "contents", "tasks"):
        assert kind in OBJECT_ROUTES


def test_response_shape_omits_payload_values() -> None:
    assert response_shape({"token": "secret", "name": "demo"}) == {"type": "dict", "keys": ["name", "token"]}
    assert response_shape([[{"_id": "1"}]]) == {
        "type": "list",
        "length": 1,
        "first": {"type": "list", "length": 1, "first": {"type": "dict", "keys": ["_id"]}},
    }


def test_encode_filter_is_stable_base64_json() -> None:
    assert encode_filter({}) == "%7B%7D"
