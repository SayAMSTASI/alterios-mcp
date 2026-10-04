import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Lock
from types import SimpleNamespace

import pytest

from alterios_mcp import read_workflows as w, snapshot_index as index
from alterios_mcp.response_output import present
from alterios_mcp.performance import measured, track_http, json_bytes
from alterios_mcp.scoped_health import run_scoped_health
from alterios_mcp.scenarios import read_workflows as tools


@pytest.fixture(autouse=True)
def private_artifacts(tmp_path, monkeypatch):
    monkeypatch.setenv("ALTERIOS_MCP_ARTIFACTS_DIR", str(tmp_path))
    index.clear_cache()
    yield
    index.clear_cache()


def snapshot():
    return {"snapshot_id": "scan_" + "a" * 32, "finished_at": "2026-01-01", "complete": True,
            "target": {"profile": "test", "project_id": "project-one"},
            "objects": {"forms": {"rows": [{"_id": "a", "name": "Форма", "viewId": "b"},
                                          {"_id": "b", "name": "Источник"}]}}}


def test_compact_response_has_exact_budget_and_full_redacted_artifact():
    original = {"rows": [{"_id": str(i), "name": "Название" * 500, "body": "data" * 1000,
                          "password": "secret-value"} for i in range(200)], "complete": False,
                "errors": [{"code": "row_limit"}]}
    result = measured(lambda: present(original, fields=["_id", "name"], max_response_bytes=4096))()
    assert len(json_bytes(result)) <= 4096
    assert result["metrics"]["response_bytes"] == len(json_bytes(result))
    assert result["complete"] is False and result["presentation"]["truncated"]
    receipt = result["presentation"]["artifact"]
    raw = Path(receipt["path"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == receipt["sha256"]
    assert b"secret-value" not in raw
    restored = json.loads(raw)
    assert len(restored["rows"]) == 200 and restored["errors"][0]["code"] == "row_limit"


def test_field_projection_does_not_project_saved_artifact():
    result = present({"rows": [{"_id": "one", "name": "Name", "value": 42}], "complete": True}, fields=["value"])
    assert result["rows"] == [{"value": 42}]
    saved = json.loads(Path(result["presentation"]["artifact"]["path"]).read_text())
    assert saved["rows"][0]["_id"] == "one"
    assert result["complete"] and result["presentation"]["truncated"]


@pytest.mark.parametrize("text", [
    'const text = \'password="hidden-value"\';',
    'const apiKey = "hidden-value";',
    'const prefix_access_token_suffix = "hidden-value";',
    'Authorization: "Bearer hidden-value"',
])
def test_fast_redaction_keeps_nested_credential_protection(text):
    assert "hidden-value" not in w.safe_payload(text)


def test_full_still_has_hard_budget_and_artifact_mode_omits_rows():
    assert present({"rows": [{"x": 1}]}, response_mode="full")["presentation"]["truncated"] is False
    result = present({"rows": [{"x": "a" * 10000}]}, response_mode="full", max_response_bytes=4096)
    assert len(json_bytes(result)) < 4096 and result["presentation"]["artifact"]
    assert present({"rows": [{"x": 1}]}, response_mode="artifact")["rows"] == []


@pytest.mark.parametrize("kwargs", [{"response_mode": "anything"}, {"max_response_bytes": 100},
                                     {"preview_rows": 101}, {"fields": ["a"] * 33}])
def test_invalid_output_options_fail_before_http(monkeypatch, kwargs):
    monkeypatch.setattr(tools, "_client", lambda *_: pytest.fail("Should not contact server"))
    with pytest.raises(ValueError):
        tools.alterios_read_all_objects("test", "p", "forms", **kwargs)


def test_cached_queries_equal_original_and_invalidate_when_file_changes():
    source = snapshot()
    receipt = w.save_snapshot(source)
    idx, first = index.get_index(source["snapshot_id"], profile="test", project_id="project-one")
    assert not first["hit"] and first["stored"]
    assert idx.find("форма") == w.find_usages(source, "форма")
    assert idx.graph()["edges"] == w.relation_graph(source)["edges"]
    # Mutating a returned graph cannot poison the cached graph.
    idx.graph()["nodes"][0]["name"] = "corrupt"
    same, hit = index.get_index(source["snapshot_id"], profile="test", project_id="project-one")
    assert hit["hit"] and same.graph()["nodes"][0]["name"] == "Форма"
    source["objects"]["forms"]["rows"][0]["name"] = "Изменённая форма"
    Path(receipt["path"]).write_text(json.dumps(source, ensure_ascii=False), encoding="utf-8")
    changed, hit = index.get_index(source["snapshot_id"], profile="test", project_id="project-one")
    assert not hit["hit"] and changed.find("Изменённая")["matches"]


def test_cache_isolated_by_target_and_root_and_refresh(monkeypatch, tmp_path):
    source = snapshot()
    w.save_snapshot(source)
    index.get_index(source["snapshot_id"], profile="test", project_id="project-one")
    with pytest.raises(ValueError, match="target"):
        index.get_index(source["snapshot_id"], profile="test", project_id="other")
    _, info = index.get_index(source["snapshot_id"], profile="test", project_id="project-one", refresh=True)
    assert not info["hit"]
    monkeypatch.setenv("ALTERIOS_MCP_ARTIFACTS_DIR", str(tmp_path / "other-root"))
    source["objects"]["forms"]["rows"][0]["name"] = "Other"
    w.save_snapshot(source)
    idx, info = index.get_index(source["snapshot_id"], profile="test", project_id="project-one")
    assert not info["hit"] and idx.find("Other")["matches"]


def test_cache_ttl_eviction_and_budget_fallback(monkeypatch):
    source = snapshot()
    w.save_snapshot(source)
    index.get_index(source["snapshot_id"], profile="test", project_id="project-one")
    monkeypatch.setattr(index, "TTL_SECONDS", 0)
    _, info = index.get_index(source["snapshot_id"], profile="test", project_id="project-one")
    assert not info["hit"]
    monkeypatch.setattr(index, "MAX_CACHE_BYTES", 1)
    idx, info = index.get_index(source["snapshot_id"], profile="test", project_id="project-one", refresh=True)
    assert not info["stored"] and not info["indexed"]
    assert idx.find("форма") == w.find_usages(source, "форма")


def test_lru_entry_bound_evicts_old_snapshot(monkeypatch):
    monkeypatch.setattr(index, "MAX_ENTRIES", 1)
    first = snapshot()
    w.save_snapshot(first)
    index.get_index(first["snapshot_id"], profile="test", project_id="project-one")
    second = snapshot()
    second["snapshot_id"] = "scan_" + "b" * 32
    w.save_snapshot(second)
    index.get_index(second["snapshot_id"], profile="test", project_id="project-one")
    _, result = index.get_index(first["snapshot_id"], profile="test", project_id="project-one")
    assert not result["hit"] and len(index._cache) == 1


def test_cached_snapshot_symlink_escape_is_blocked(tmp_path):
    source = snapshot()
    receipt = w.save_snapshot(source)
    index.get_index(source["snapshot_id"], profile="test", project_id="project-one")
    path = Path(receipt["path"])
    outside = tmp_path / "outside.json"
    outside.write_text(json.dumps(source))
    path.unlink()
    try:
        path.symlink_to(outside)
    except OSError:
        pytest.skip("Symlink privileges unavailable")
    with pytest.raises(ValueError, match="path"):
        index.get_index(source["snapshot_id"], profile="test", project_id="project-one")


def test_parallel_hydration_bounded_ordered_and_counts_actual_requests():
    class Client:
        config = SimpleNamespace(profile="test", project_id="project-one")
        active = 0
        peak = 0
        lock = Lock()
        @track_http
        def request(self, *_args, **_kwargs):
            return SimpleNamespace(body=[[{"_id": str(i)} for i in range(8)], 8])
        @track_http
        def report_by_id(self, identity):
            with self.lock:
                self.active += 1
                self.peak = max(self.peak, self.active)
            time.sleep(0.01)
            with self.lock:
                self.active -= 1
            if identity == "2":
                raise w.AlteriosRequestError("token=private")
            return SimpleNamespace(body={"value": identity})
    client = Client()
    result = measured(lambda: w.collect_snapshot(client, kinds=["reports"], include_details=True,
                                                max_detail_objects=5, detail_workers=3))()
    assert 1 < client.peak <= 3
    assert result["metrics"]["http_requests"] == 6 and result["metrics"]["http_errors"] == 1
    assert result["detail_objects_read"] == 5 and not result["complete"]
    rows = result["objects"]["reports"]["rows"]
    assert [r["_id"] for r in rows] == list(map(str, range(8)))
    assert "private" not in json.dumps(result)
    assert {e["code"] for e in result["objects"]["reports"]["errors"]} == {"detail_limit", "detail_read_failed"}


def test_simultaneous_queries_share_immutable_index():
    source = snapshot()
    w.save_snapshot(source)
    def read(_):
        idx, _ = index.get_index(source["snapshot_id"], profile="test", project_id="project-one")
        return idx.graph(root_id="a")
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(read, range(12)))
    assert all(r == results[0] for r in results)


class ScopeClient:
    config = SimpleNamespace(profile="test", project_id="project-one")
    def __init__(self): self.calls = []
    @track_http
    def field_by_id(self, identity):
        self.calls.append(("fields", identity))
        return SimpleNamespace(body={"_id": identity, "contentTypeId": "type-one", "projectId": "project-one"})
    @track_http
    def content_type_by_id(self, identity):
        self.calls.append(("content_types", identity))
        return SimpleNamespace(body={"_id": identity})


def test_scoped_checks_fetch_only_exact_objects_and_known_dependencies():
    client = ScopeClient()
    result = run_scoped_health(profile="test", project_id="project-one", objects=[{"kind": "fields", "id": "field-one"}], client=client)
    assert result["summary"]["ok"] and not result["full_project_verified"]
    assert client.calls == [("fields", "field-one"), ("content_types", "type-one")]
    assert result["metrics"]["http_requests"] == 2


@pytest.mark.parametrize("kwargs", [{"max_depth": 0}, {"max_objects": 1}])
def test_scope_limit_is_incomplete_not_successful(kwargs):
    result = run_scoped_health(profile="test", project_id="project-one", objects=[{"kind": "fields", "id": "field-one"}], client=ScopeClient(), **kwargs)
    assert not result["summary"]["ok"] and not result["complete_within_supported_scope"]


@pytest.mark.parametrize("body", [{"_id": "other"}, {"_id": "field-one", "projectId": "other"}])
def test_scope_rejects_ignored_filters_and_wrong_project(body):
    client = ScopeClient()
    client.field_by_id = lambda _: SimpleNamespace(body=body)
    result = run_scoped_health(profile="test", project_id="project-one", objects=[{"kind": "fields", "id": "field-one"}], client=client)
    assert not result["summary"]["ok"]


def test_scope_blocks_invalid_form_contract():
    client = ScopeClient()
    client.form_full = lambda _: SimpleNamespace(body={"_id": "form-one", "tabs": []})
    result = run_scoped_health(profile="test", project_id="project-one", objects=[{"kind": "forms", "id": "form-one"}], client=client)
    assert not result["summary"]["ok"]


@pytest.mark.parametrize("scenario", ["alterios_fast_live_bulk_delete", "alterios_create_material_module", None])
def test_scoped_preflight_cannot_replace_broad_scenario_health(scenario):
    from alterios_mcp.live_task_preflight import run_live_task_preflight
    with pytest.raises(ValueError, match="typed_write"):
        run_live_task_preflight(profile="test", project_id="p", scenario_tool=scenario,
                               health_scope=[{"kind": "fields", "id": "field-one"}])
