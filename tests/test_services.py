from __future__ import annotations

import json

from alterios_mcp.services import SERVICES, get_service, list_services, service_to_dict


ALLOWED_RISK_LEVELS = {
    "read",
    "write",
    "destructive",
    "workflow_side_effect",
    "external_side_effect",
    "audit_side_effect",
}


def test_read_only_catalog_excludes_mutating_services() -> None:
    read_only = list_services(read_only=True)

    assert {service.name for service in read_only} == {"getContents", "getDependentContents", "getTasks", "getViewData"}
    assert all(not service.mutates for service in read_only)
    assert all(service.safe_to_probe for service in read_only)


def test_service_metadata_exports_contract_fields() -> None:
    payload = service_to_dict(get_service("getViewData"))

    assert payload["name"] == "getViewData"
    assert payload["category"] == "views"
    assert payload["risk_level"] == "read"
    assert payload["safe_to_probe"] is True
    assert payload["example_args"] == {"query": {"viewId": "<view-id>", "limit": 20, "offset": 0}}
    assert payload["arguments"][0]["name"] == "query"
    assert payload["arguments"][0]["required"] is True
    assert "dataId should be an array" in payload["notes"][0]


def test_destructive_service_is_classified_as_mutating_and_not_probe_safe() -> None:
    payload = service_to_dict(get_service("deleteManyContents"))

    assert payload["mutates"] is True
    assert payload["risk_level"] == "destructive"
    assert payload["safe_to_probe"] is False
    assert "dry-run" in payload["notes"][0]


def test_service_catalog_is_json_serializable() -> None:
    payload = [service_to_dict(service) for service in list_services()]

    assert json.loads(json.dumps(payload, sort_keys=True)) == payload


def test_argument_names_match_legacy_args() -> None:
    for service in SERVICES.values():
        assert tuple(argument.name for argument in service.arguments) == service.args


def test_catalog_has_risk_taxonomy_and_safeguard_notes() -> None:
    for service in SERVICES.values():
        assert service.risk_level in ALLOWED_RISK_LEVELS
        assert service.result_shape
        assert service.example_args is not None
        if service.mutates:
            assert service.notes
            assert not service.safe_to_probe
