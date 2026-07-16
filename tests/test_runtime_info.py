from __future__ import annotations

from pathlib import Path

from alterios_mcp.runtime_info import build_runtime_fingerprint


def test_runtime_fingerprint_is_stable_and_secret_free(tmp_path: Path) -> None:
    package = tmp_path / "src" / "alterios_mcp"
    package.mkdir(parents=True)
    for name, value in {
        "server.py": "TOOLS = 1\n",
        "form_surface.py": "FORM = 1\n",
        "write_control.py": "WRITE = 1\n",
        "ux_contract.py": "UX = 1\n",
    }.items():
        (package / name).write_text(value, encoding="utf-8")
    skill = tmp_path / "skills" / "sample" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("sample", encoding="utf-8")

    first = build_runtime_fingerprint(package_root=package, tool_count=101)
    second = build_runtime_fingerprint(package_root=package, tool_count=101)

    assert first["fingerprint"] == second["fingerprint"]
    assert first["tool_count"] == 101
    assert set(first["source_hashes"]) == {
        "server.py",
        "form_surface.py",
        "write_control.py",
        "ux_contract.py",
    }
    assert first["skills_hash"]
    assert "token" not in str(first).lower()
