from __future__ import annotations

import io
import json
from types import SimpleNamespace

import pytest

from alterios_mcp import file_export as f
from alterios_mcp.client import AlteriosRequestError


def client():
    config = SimpleNamespace(profile="primary", project_id="project-one", base_url="https://example.test",
                             timeout_seconds=2, missing_for_project_call=lambda: [])
    return SimpleNamespace(config=config, _headers=lambda: {"Authorization": "Bearer test"})


def test_manifest_matches_bytes_and_untrusted_id_never_becomes_path(tmp_path, monkeypatch):
    monkeypatch.setenv("ALTERIOS_MCP_ARTIFACTS_DIR", str(tmp_path))
    monkeypatch.setattr(f, "download_bounded", lambda *args: (b"example", "application/pdf"))
    result = f.export_files(client(), ["../../outside"])
    assert result["complete"] and result["bytes"] == 7
    from pathlib import Path
    directory = Path(result["directory"])
    assert directory.is_relative_to(tmp_path)
    assert (directory / "0001.bin").read_bytes() == b"example"
    assert json.loads((directory / "manifest.json").read_text())["files"][0]["verified"]


def test_download_rejects_redirects_and_oversize_payload(monkeypatch):
    with pytest.raises(AlteriosRequestError, match="redirect"):
        f.NoRedirect().redirect_request(None, None, 302, "", {}, "https://other.test")
    class Response(io.BytesIO):
        headers = {"Content-Type": "application/octet-stream"}
    monkeypatch.setattr(f, "build_opener", lambda *_: SimpleNamespace(open=lambda *a, **k: Response(b"long data")))
    with pytest.raises(AlteriosRequestError, match="byte limit"):
        f.download_bounded(client(), "file", 4)


@pytest.mark.parametrize("headers,expected", [
    ({"Content-Type": "text/html"}, "HTML"),
    ({"Content-Length": "8"}, "length mismatch"),
])
def test_login_or_truncated_file_is_not_saved(monkeypatch, headers, expected):
    class Response(io.BytesIO):
        pass
    def open_response(*args, **kwargs):
        response = Response(b"abc")
        response.headers = headers
        return response
    monkeypatch.setattr(f, "build_opener", lambda *_: SimpleNamespace(open=open_response))
    with pytest.raises(AlteriosRequestError, match=expected):
        f.download_bounded(client(), "file", 100)


def test_total_budget_is_enforced_and_partial_manifest_saved(tmp_path, monkeypatch):
    monkeypatch.setenv("ALTERIOS_MCP_ARTIFACTS_DIR", str(tmp_path))
    calls = []
    def read(c, file_id, limit):
        calls.append(limit)
        return b"abc", "application/octet-stream"
    monkeypatch.setattr(f, "download_bounded", read)
    result = f.export_files(client(), ["one", "two"], max_total_bytes=3)
    assert not result["complete"] and calls == [3]
    assert result["files"][0]["verified"] and not result["files"][1]["verified"]
