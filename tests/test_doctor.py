from __future__ import annotations

import json

from alterios_mcp import doctor


def test_doctor_reports_ready_installation_without_network(monkeypatch) -> None:
    monkeypatch.setenv("ALTERIOS_MCP_TOOL_PROFILE", "live")
    monkeypatch.setattr(doctor, "_console_script_path", lambda name: f"C:/venv/Scripts/{name}.exe")
    monkeypatch.setattr(
        doctor,
        "configured_profiles",
        lambda **_: {
            "selected_profile": "primary",
            "profiles": [
                {
                    "profile": "primary",
                    "selected": True,
                    "missing_for_instance_call": [],
                    "missing_for_project_call": ["project_id"],
                    "has_project_default": False,
                }
            ],
        },
    )
    monkeypatch.setattr(doctor, "build_runtime_fingerprint", lambda: {"fingerprint": "fp-1", "stale": False})

    result = doctor.run_doctor(
        require_console_scripts=True,
        measure_startup=False,
    )

    assert result["summary"]["ok"] is True
    assert result["summary"]["status"] == "warning"
    checks = {item["name"]: item for item in result["checks"]}
    assert checks["profiles"]["status"] == "pass"
    assert checks["tool_profile"]["profile"] == "live"
    assert checks["startup_import"]["status"] == "skip"
    assert "token" not in json.dumps(result, ensure_ascii=False).lower()


def test_doctor_requires_config_when_requested(monkeypatch) -> None:
    monkeypatch.delenv("ALTERIOS_DOTENV_PATH", raising=False)
    monkeypatch.setattr(doctor, "_console_script_path", lambda name: f"/venv/bin/{name}")
    monkeypatch.setattr(doctor, "configured_profiles", lambda **_: {"selected_profile": None, "profiles": []})
    monkeypatch.setattr(doctor, "build_runtime_fingerprint", lambda: {"fingerprint": "fp-1", "stale": False})

    result = doctor.run_doctor(require_config=True, measure_startup=False)

    assert result["summary"]["ok"] is False
    assert {item["name"] for item in result["checks"] if item["status"] == "fail"} == {"dotenv", "profiles"}


def test_startup_check_can_warn_or_fail_on_budget(monkeypatch) -> None:
    class Completed:
        returncode = 0
        stderr = ""

    monkeypatch.setattr(doctor.subprocess, "run", lambda *args, **kwargs: Completed())
    times = iter((10.0, 12.5, 20.0, 22.5))
    monkeypatch.setattr(doctor.time, "perf_counter", lambda: next(times))

    warning = doctor._startup_check(budget_seconds=2.0, strict=False)
    failure = doctor._startup_check(budget_seconds=2.0, strict=True)

    assert warning["status"] == "warn"
    assert failure["status"] == "fail"
