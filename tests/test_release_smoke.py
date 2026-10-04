from __future__ import annotations

from alterios_mcp import release_smoke


def test_release_smoke_checks_profiles_doctor_and_replay(monkeypatch) -> None:
    monkeypatch.setattr(
        release_smoke,
        "run_doctor",
        lambda **_: {"summary": {"ok": True, "status": "ready"}},
    )
    monkeypatch.setattr(
        release_smoke,
        "run_replay_smoke",
        lambda **_: {"summary": {"ok": True, "status": "ready"}},
    )

    result = release_smoke.run_release_smoke(
        require_console_scripts=False,
        measure_startup=False,
    )

    assert result["summary"]["ok"] is True
    profile_check = next(item for item in result["checks"] if item["name"] == "tool_profiles")
    assert profile_check["tool_count"] == 118
    assert profile_check["profile_counts"] == {"full": 118, "live": 91, "discovery": 65, "admin": 116}
