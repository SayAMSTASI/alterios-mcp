from __future__ import annotations

from pathlib import Path

from alterios_mcp import runtime_info
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


def test_collect_alterios_mcp_processes_filters_runtime_info_and_redacts(monkeypatch) -> None:
    monkeypatch.setattr(
        runtime_info,
        "_process_rows",
        lambda: [
            {
                "pid": 101,
                "parent_pid": 100,
                "name": "python.exe",
                "created_at": "2026-07-16T10:00:00",
                "command_line": r'"C:\venv\python.exe" "C:\repo\alterios-mcp\.venv\Scripts\alterios-mcp.exe" token=secret',
            },
            {
                "pid": 102,
                "parent_pid": 100,
                "name": "python.exe",
                "created_at": "2026-07-16T10:01:00",
                "command_line": r'"C:\venv\python.exe" -m alterios_mcp.runtime_info --processes',
            },
            {
                "pid": 103,
                "parent_pid": 100,
                "name": "python.exe",
                "created_at": "2026-07-16T10:02:00",
                "command_line": r'"C:\venv\python.exe" -c "import alterios_mcp.server"',
            },
        ],
    )

    processes = runtime_info.collect_alterios_mcp_processes()

    assert [item["pid"] for item in processes] == [101]
    assert "token=<redacted>" in processes[0]["command"]
    assert "secret" not in processes[0]["command"]


def test_collect_alterios_mcp_instances_groups_windows_console_launcher(monkeypatch) -> None:
    monkeypatch.setattr(
        runtime_info,
        "_process_rows",
        lambda: [
            {
                "pid": 301,
                "parent_pid": 900,
                "name": "alterios-mcp.exe",
                "created_at": "2026-07-16T10:00:00",
                "command_line": r'"C:\repo\alterios-mcp\.venv\Scripts\alterios-mcp.exe"',
            },
            {
                "pid": 302,
                "parent_pid": 301,
                "name": "python.exe",
                "created_at": "2026-07-16T10:00:01",
                "command_line": r'"C:\repo\alterios-mcp\.venv\Scripts\python.exe" "C:\repo\alterios-mcp\.venv\Scripts\alterios-mcp.exe"',
            },
        ],
    )

    processes = runtime_info.collect_alterios_mcp_processes()
    instances = runtime_info.collect_alterios_mcp_instances(processes)

    assert len(processes) == 2
    assert len(instances) == 1
    assert instances[0]["root_pid"] == 301
    assert instances[0]["process_count"] == 2


def test_cleanup_alterios_mcp_processes_is_dry_run_by_default(monkeypatch) -> None:
    stopped: list[int] = []
    monkeypatch.setattr(
        runtime_info,
        "_process_rows",
        lambda: [
            {
                "pid": 201,
                "parent_pid": 900,
                "name": "python.exe",
                "created_at": "2026-07-16T10:02:00",
                "command_line": r'"C:\venv\python.exe" "C:\repo\alterios-mcp\.venv\Scripts\alterios-mcp.exe"',
            },
            {
                "pid": 202,
                "parent_pid": 901,
                "name": "python.exe",
                "created_at": "2026-07-16T10:01:00",
                "command_line": r'"C:\venv\python.exe" "C:\repo\alterios-mcp\.venv\Scripts\alterios-mcp.exe"',
            },
            {
                "pid": 203,
                "parent_pid": 902,
                "name": "python.exe",
                "created_at": "2026-07-16T10:00:00",
                "command_line": r'"C:\venv\python.exe" "C:\repo\alterios-mcp\.venv\Scripts\alterios-mcp.exe"',
            },
        ],
    )
    monkeypatch.setattr(runtime_info, "_terminate_process", lambda pid: stopped.append(pid))

    dry_run = runtime_info.cleanup_alterios_mcp_processes(keep_newest=1)
    applied = runtime_info.cleanup_alterios_mcp_processes(keep_newest=1, dry_run=False)

    assert dry_run["dry_run"] is True
    assert [item["root_pid"] for item in dry_run["kept"]] == [201]
    assert [item["root_pid"] for item in dry_run["planned_stop"]] == [202, 203]
    assert stopped == [202, 203]
    assert [item["root_pid"] for item in applied["stopped"]] == [202, 203]
