from __future__ import annotations

import json

import pytest

from alterios_mcp.static_scan import scan_directory


def test_scan_directory_finds_api_paths_and_services(tmp_path) -> None:
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "app.ts").write_text(
        "\n".join(
            [
                'fetch("/api/tasks/listandcount");',
                "client.request('GET', '/api/forms/listandcount');",
                'const knownService = "getTasks";',
                'const likelyService = "getCustomReport";',
                "createContent({ name: 'demo' });",
            ]
        ),
        encoding="utf-8",
    )

    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "notes.md").write_text(
        "Manual script endpoint: `/api/scripts/execute-manual`; then call notify.",
        encoding="utf-8",
    )

    payload = scan_directory(tmp_path)

    assert payload["files_scanned"] == ["docs/notes.md", "src/app.ts"]
    assert [item["value"] for item in payload["api_paths"]] == [
        "/api/forms/listandcount",
        "/api/scripts/execute-manual",
        "/api/tasks/listandcount",
    ]
    assert [item["name"] for item in payload["services"]] == [
        "createContent",
        "getCustomReport",
        "getTasks",
        "notify",
    ]
    assert {item["name"]: item["known"] for item in payload["services"]} == {
        "createContent": True,
        "getCustomReport": False,
        "getTasks": True,
        "notify": True,
    }


def test_scan_directory_ignores_common_generated_directories(tmp_path) -> None:
    for ignored_dir in [".git", ".venv", "__pycache__", "node_modules", "artifacts", "data", "outputs", "site", "work"]:
        path = tmp_path / ignored_dir
        path.mkdir()
        (path / "ignored.py").write_text(
            'fetch("/api/ignored");\nconst service = "deleteManyContents";',
            encoding="utf-8",
        )

    (tmp_path / "kept.py").write_text('fetch("/api/kept");', encoding="utf-8")

    payload = scan_directory(tmp_path)

    assert payload["files_scanned"] == ["kept.py"]
    assert [item["value"] for item in payload["api_paths"]] == ["/api/kept"]
    assert payload["services"] == []


def test_scan_directory_keeps_likely_false_positives_unknown(tmp_path) -> None:
    (tmp_path / "workflow.py").write_text(
        "\n".join(
            [
                '"createNew"',
                '"createOnStart"',
                '"listDirectionTasks"',
                '"startPayload"',
                '"uploadResponse"',
                "services.getContents({})",
                "services.createDependentContent({})",
            ]
        ),
        encoding="utf-8",
    )

    payload = scan_directory(tmp_path)
    by_name = {item["name"]: item["known"] for item in payload["services"]}

    assert by_name["getContents"] is True
    assert by_name["createDependentContent"] is True
    for name in ["createNew", "createOnStart", "listDirectionTasks", "startPayload", "uploadResponse"]:
        assert by_name[name] is False


def test_scan_directory_can_include_generated_directories(tmp_path) -> None:
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    (artifacts / "kept_when_requested.py").write_text('fetch("/api/generated");', encoding="utf-8")

    payload = scan_directory(tmp_path, include_generated=True)

    assert payload["files_scanned"] == ["artifacts/kept_when_requested.py"]
    assert [item["value"] for item in payload["api_paths"]] == ["/api/generated"]


def test_scan_directory_is_json_serializable_and_deterministic(tmp_path) -> None:
    (tmp_path / "b.py").write_text('"getTasks"\n"/api/b"', encoding="utf-8")
    (tmp_path / "a.py").write_text('"createContent"\n"/api/a"', encoding="utf-8")

    first = scan_directory(tmp_path)
    second = scan_directory(tmp_path)

    assert first == second
    assert json.loads(json.dumps(first, sort_keys=True)) == first


def test_scan_directory_rejects_non_directory_targets(tmp_path) -> None:
    target = tmp_path / "file.py"
    target.write_text('"/api/tasks"', encoding="utf-8")

    with pytest.raises(NotADirectoryError):
        scan_directory(target)
