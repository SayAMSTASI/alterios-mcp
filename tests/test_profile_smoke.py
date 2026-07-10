from __future__ import annotations

import json

from alterios_mcp import profile_smoke


def test_profile_smoke_counts_projects_and_omits_names_by_default(monkeypatch) -> None:
    monkeypatch.setattr(
        profile_smoke,
        "configured_profiles",
        lambda selected_profile=None: {
            "selected_profile": selected_profile,
            "profile_count": 1,
            "profiles": [
                {
                    "profile": "artx",
                    "profile_argument": "artx",
                    "selected": True,
                    "config": {
                        "profile": "artx",
                        "base_url": "https://lims.example/path",
                        "api_token": "<set>",
                        "project_id": "project-1",
                        "endpoint_template": "https://lims.example/api/scripts/execute-manual",
                        "body_style": "manual_script",
                        "auth_header": "x-api-key",
                        "auth_scheme": "",
                        "timeout_seconds": 20,
                    },
                    "missing_for_instance_call": [],
                    "missing_for_project_call": [],
                    "has_project_default": True,
                }
            ],
        },
    )
    monkeypatch.setattr(profile_smoke.AlteriosConfig, "from_env", staticmethod(lambda profile=None: object()))
    monkeypatch.setattr(profile_smoke, "AlteriosClient", lambda config: object())
    monkeypatch.setattr(
        profile_smoke,
        "list_projects",
        lambda client, limit, offset: {
            "status_code": 200,
            "content_type": "application/json",
            "body": [[{"_id": "project-1", "name": "Sensitive project"}], 1],
        },
    )
    monkeypatch.setattr(
        profile_smoke,
        "discover_readonly",
        lambda client: {
            "routes": [
                {"name": "projects", "method": "GET", "path": "/api/projects/listandcount", "ok": True, "status_code": 200},
                {"name": "forms", "method": "GET", "path": "/api/forms/listandcount", "ok": True, "status_code": 200},
            ]
        },
    )

    matrix = profile_smoke.run_profile_smoke(selected_profile="artx")

    assert matrix["summary"]["project_count_total"] == 1
    assert matrix["summary"]["default_project_discovery_ok"] == 1
    assert matrix["profiles"][0]["config"]["base_url"] == "<set>"
    assert matrix["profiles"][0]["config"]["endpoint_template"] == "<set>"
    assert matrix["profiles"][0]["config"]["project_id"] == "<set>"
    assert matrix["profiles"][0]["instance_project_list"]["sample_projects"] == []
    dumped = json.dumps(matrix, ensure_ascii=False)
    assert "secret" not in dumped
    assert "Sensitive project" not in dumped


def test_profile_smoke_skips_project_discovery_without_default_project(monkeypatch) -> None:
    monkeypatch.setattr(
        profile_smoke,
        "configured_profiles",
        lambda selected_profile=None: {
            "selected_profile": None,
            "profile_count": 1,
            "profiles": [
                {
                    "profile": "demo",
                    "profile_argument": "demo",
                    "selected": False,
                    "config": {"profile": "demo", "base_url": "https://demo.example", "api_token": "<set>"},
                    "missing_for_instance_call": [],
                    "missing_for_project_call": ["ALTERIOS_DEMO_PROJECT_ID"],
                    "has_project_default": False,
                }
            ],
        },
    )
    monkeypatch.setattr(profile_smoke.AlteriosConfig, "from_env", staticmethod(lambda profile=None: object()))
    monkeypatch.setattr(profile_smoke, "AlteriosClient", lambda config: object())
    monkeypatch.setattr(
        profile_smoke,
        "list_projects",
        lambda client, limit, offset: {
            "status_code": 200,
            "content_type": "application/json",
            "body": [[{"_id": "project-1"}], 1],
        },
    )

    matrix = profile_smoke.run_profile_smoke()

    discovery = matrix["profiles"][0]["default_project_discovery"]
    assert discovery["skipped"] is True
    assert discovery["reason"] == "missing default project configuration"
    assert matrix["summary"]["all_default_project_discovery_ok_or_skipped"] is True


def test_render_markdown_reports_failures() -> None:
    markdown = profile_smoke.render_markdown(
        {
            "generated_at": "2026-07-10T00:00:00+00:00",
            "readonly": True,
            "write_gate_enabled": False,
            "include_project_names": False,
            "summary": {
                "profiles_total": 1,
                "instance_project_list_ok": 0,
                "default_project_discovery_ok": 0,
                "default_project_discovery_skipped": 1,
                "project_count_total": 0,
            },
            "profiles": [
                {
                    "profile": "demo",
                    "config": {"api_token": "<missing>", "base_url": "<missing>", "project_id": ""},
                    "instance_project_list": {"ok": False, "reason": "missing instance configuration"},
                    "default_project_discovery": {"ok": False, "skipped": True, "reason": "missing instance configuration"},
                }
            ],
        }
    )

    assert "# Profile Smoke Matrix" in markdown
    assert "`demo`: project list - missing instance configuration" in markdown
