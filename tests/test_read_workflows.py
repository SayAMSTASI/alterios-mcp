from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from alterios_mcp import read_workflows as w
from alterios_mcp.client import AlteriosRequestError
from alterios_mcp.scenarios import read_workflows as tools


def test_server_page_cap_is_not_mistaken_for_end():
    calls = []
    def fetch(limit, offset):
        calls.append(offset)
        return [[{"_id": str(n)} for n in range(offset, min(5, offset + 2))], 5]
    result = w.collect_pages(fetch, page_size=200)
    assert result["complete"] and result["loaded"] == 5
    assert calls == [0, 2, 4]


def test_unknown_total_requires_empty_terminal_page():
    pages = [[{"_id": "one"}], []]
    result = w.collect_pages(lambda *_: pages.pop(0))
    assert result["complete"] and result["pages"] == 2 and result["total"] is None


@pytest.mark.parametrize("pages,code", [
    ([[[{"_id": "a"}], 2], [[{"_id": "a"}], 2]], "duplicate_rows"),
    ([[[{"_id": "a"}], 2], [[], 2]], "count_mismatch"),
    ([[[{"_id": "a"}], 2], [[{"_id": "b"}], 3], [[], 3]], "total_changed"),
    ([{"unexpected": []}], "page_read_failed"),
    ([["invalid-row"]], "page_read_failed"),
])
def test_incomplete_scans_are_never_successful(pages, code):
    result = w.collect_pages(lambda *_: pages.pop(0))
    assert not result["complete"]
    assert code in {e["code"] for e in result["errors"]}


def test_page_failure_preserves_previous_rows_without_exposing_error_secrets():
    def fetch(limit, offset):
        if offset:
            raise AlteriosRequestError("token=private")
        return [[{"_id": "one"}], 2]
    result = w.collect_pages(fetch)
    assert result["loaded"] == 1 and not result["complete"]
    assert "private" not in json.dumps(result)


def test_scan_limits_and_empty_dataset():
    result = w.collect_pages(lambda *_: [[{"_id": "a"}], 2], max_rows=1)
    assert not result["complete"]
    assert w.collect_pages(lambda *_: [[], 0])["complete"]
    result = w.collect_pages(lambda *_: [{"_id": "a"}], max_pages=1)
    assert not result["complete"]
    with pytest.raises(ValueError):
        w.collect_pages(lambda *_: [], max_pages=0)


class Client:
    config = SimpleNamespace(profile="primary", project_id="project-one")
    def __init__(self):
        self.calls = []
    def request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        return SimpleNamespace(body=[[{"_id": "item", "name": "sample"}], 1])


def test_snapshot_budget_target_and_offline_search(tmp_path, monkeypatch):
    monkeypatch.setenv("ALTERIOS_MCP_ARTIFACTS_DIR", str(tmp_path))
    client = Client()
    snapshot = w.collect_snapshot(client, kinds=["forms", "contents"], max_rows=1)
    assert not snapshot["complete"]
    assert len(client.calls) == 1
    receipt = w.save_snapshot(snapshot)
    stored = w.load_snapshot(receipt["snapshot_id"], profile="primary", project_id="project-one")
    assert w.find_usages(stored, "sample")["matches"][0]["path"] == "/name"
    assert not w.find_usages(stored, "sample")["complete_within_snapshot"]
    with pytest.raises(ValueError, match="target"):
        w.load_snapshot(receipt["snapshot_id"], profile="primary", project_id="other")
    with pytest.raises(ValueError):
        w.load_snapshot("../private", profile="primary", project_id="project-one")
    with pytest.raises(FileExistsError):
        w.save_snapshot(snapshot)


def test_snapshot_rejects_symlink_escape(tmp_path, monkeypatch):
    monkeypatch.setenv("ALTERIOS_MCP_ARTIFACTS_DIR", str(tmp_path / "inside"))
    root = tmp_path / "inside" / "read-snapshots"
    root.mkdir(parents=True)
    outside = tmp_path / "outside.json"
    outside.write_text("{}")
    try:
        (root / ("scan_" + "a" * 32 + ".json")).symlink_to(outside)
    except OSError:
        pytest.skip("symlinks not available")
    with pytest.raises(ValueError):
        w.load_snapshot("scan_" + "a" * 32, profile="primary", project_id="p")


def test_graph_follows_incoming_edges_and_reports_truncation():
    snapshot = {"snapshot_id": "scan", "finished_at": "today", "complete": True,
        "objects": {"forms": {"rows": [{"_id": "parent", "name": "Parent"},
            {"_id": "child", "parent": "parent", "nested": {"formId": "parent"}}]}}}
    graph = w.relation_graph(snapshot, root_id="parent")
    assert len(graph["nodes"]) == 2 and len(graph["edges"]) == 2
    assert not w.relation_graph(snapshot, max_edges=1)["complete_within_snapshot"]
    assert w.find_usages(snapshot, "parent", max_matches=1)["truncated"]
    with pytest.raises(ValueError):
        w.relation_graph(snapshot, root_id="missing")


def test_nested_and_log_string_redaction():
    value = {"args": json.dumps({"password": "private", "_id": "item"}),
             "source": 'const apiKey = "private"; fetch(x, {Authorization: "Bearer abc123"});',
             "nested": {"access_token": "private"}, "text": "mail@example.test"}
    result = json.dumps(w.safe_payload(value))
    assert "private" not in result and "abc123" not in result and "mail@example.test" not in result
    assert "item" in result


def test_filters_are_bounded_and_only_read_routes_called():
    client = Client()
    w.read_kind(client, "contents", filters={"contentTypeId": "type-one"})
    assert client.calls[0][0] == "GET"
    assert client.calls[0][2]["params"]["contentTypeId"] == "type-one"
    for filters in ({"limit": 999}, {"projectId": "other"}, {"_id": {"$where": "x"}}):
        with pytest.raises(ValueError):
            w.read_kind(client, "contents", filters=filters)


def test_view_diagnostic_compares_context_and_keeps_failure_evidence():
    class ViewClient(Client):
        def view_full(self, _): return SimpleNamespace(body={"_id": "v"})
        def view_entities(self, _): return SimpleNamespace(body=[])
        def view_fields_populated(self, _): return SimpleNamespace(body=[])
        def view_data(self, _, **kwargs):
            return SimpleNamespace(body=[[{"_id": "scoped" if kwargs.get("data_id") else "unscoped"}], 1])
        def request(self, *_, **kwargs):
            raise AlteriosRequestError("column missing")
    result = w.diagnose_view(ViewClient(), "view", content_id="record")
    assert len(result["checks"]) == 7
    assert len(result["findings"]) == 2
    assert not next(x for x in result["checks"] if x["name"] == "simplified")["ok"]


def test_audit_reads_instance_scope_and_matches_parsed_ids(monkeypatch):
    client = Client()
    def request(method, path, **kwargs):
        assert method == "GET" and path == "/api/log" and not kwargs["requires_project"]
        return SimpleNamespace(body=[[{"_id": "event", "date": "2026-01-01", "path": "UsersController",
                                      "body": json.dumps({"_id": "user-one", "password": "private"})}], 1])
    client.request = request
    monkeypatch.setattr(tools, "_client", lambda *_: client)
    result = tools.alterios_audit_log("primary", "project-one", object_id="user-one")
    assert len(result["rows"]) == 1 and result["complete"]
    assert not result["retention_start_verified"] and "private" not in json.dumps(result)


def test_notifications_never_claim_delivery_or_write(monkeypatch):
    client = Client()
    monkeypatch.setattr(tools, "_client", lambda *_: client)
    result = tools.alterios_list_notifications("primary", "project-one")
    assert not result["delivery_verified"]
    assert all(method == "GET" for method, _, _ in client.calls)
    with pytest.raises(ValueError):
        tools.alterios_list_notifications("", "project-one")


def test_detail_hydration_finds_report_marker_and_failure_marks_incomplete():
    class DetailClient(Client):
        def report_by_id(self, _):
            return SimpleNamespace(body={"template": "@ExampleMarker"})
        def form_full(self, _):
            raise AlteriosRequestError("missing")
    snapshot = w.collect_snapshot(DetailClient(), kinds=["reports", "forms"], include_details=True)
    result = w.find_usages(snapshot, "@ExampleMarker")
    assert result["matches"][0]["path"] == "/_snapshot_detail/template"
    assert not snapshot["complete"]
    limited = w.collect_snapshot(DetailClient(), kinds=["reports", "forms"], include_details=True, max_detail_objects=1)
    assert limited["objects"]["forms"]["errors"][0]["code"] == "detail_limit"


def test_fields_plain_array_uses_one_read_even_when_server_ignores_limits():
    client = Client()
    calls = []
    def request(*args, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(body=[{"_id": "a"}, {"_id": "b"}, {"_id": "c"}])
    client.request = request
    result = w.read_kind(client, "fields", page_size=1, max_rows=10)
    assert result["complete"] and result["loaded"] == 3 and len(calls) == 1
    limited = w.read_kind(client, "fields", max_rows=2)
    assert not limited["complete"] and len(limited["rows"]) == 2


def test_failed_unpaginated_route_does_not_discard_other_sections():
    class FailingFields(Client):
        def request(self, method, path, **kwargs):
            if path == "/api/fields":
                raise AlteriosRequestError("offline")
            return super().request(method, path, **kwargs)
    snapshot = w.collect_snapshot(FailingFields(), kinds=["fields", "forms"])
    assert not snapshot["complete"]
    assert snapshot["objects"]["fields"]["errors"]
    assert snapshot["objects"]["forms"]["loaded"] == 1
