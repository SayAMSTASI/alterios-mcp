"""Offline reproducible workload comparisons. No credentials or live server needed."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import statistics
import tempfile
import time
from types import SimpleNamespace
from unittest.mock import patch

from alterios_mcp import read_workflows as w, snapshot_index as indexes, project_health
from alterios_mcp.performance import json_bytes
from alterios_mcp.response_output import present
from alterios_mcp.scoped_health import run_scoped_health


def timing(function, repeats):
    samples = []
    for _ in range(repeats):
        started = time.perf_counter()
        function()
        samples.append((time.perf_counter() - started) * 1000)
    ordered = sorted(samples)
    return {"median_ms": round(statistics.median(samples), 3), "max_ms": round(ordered[-1], 3),
            "samples": repeats}


class DetailClient:
    config = SimpleNamespace(profile="benchmark", project_id="fixture-project")
    def __init__(self, delay):
        self.delay, self.calls = delay, []
    def request(self, *_args, **_kwargs):
        self.calls.append("list")
        return SimpleNamespace(body=[[{"_id": f"report-{i}"} for i in range(32)], 32])
    def report_by_id(self, identity):
        self.calls.append(identity)
        time.sleep(self.delay)
        return SimpleNamespace(body={"_id": identity, "template": "fixture"})


class ScopeClient:
    config = SimpleNamespace(profile="benchmark", project_id="fixture-project")
    def __init__(self): self.calls = 0
    def response(self, body):
        self.calls += 1
        return SimpleNamespace(body=body)
    def field_by_id(self, identity): return self.response({"_id": identity, "contentTypeId": "type-one"})
    def content_type_by_id(self, identity): return self.response({"_id": identity})
    def list_forms(self, **_): return self.response([[], 0])
    def list_scripts(self, **_): return self.response([[], 0])
    def list_diagrams(self, **_): return self.response([[{"_id": f"diagram-{i}"} for i in range(20)], 20])
    def list_groups(self, **_): return self.response([])
    def list_views(self, **_): return self.response([[], 0])
    def list_reports(self, **_): return self.response([[], 0])
    def list_processes(self, **_): return self.response([[], 0])
    def list_tasks(self, **_): return self.response([[], 0])


def benchmark(repeats=5, delay=0.005):
    with tempfile.TemporaryDirectory(prefix="alterios-bench-") as directory, patch.dict(os.environ, {"ALTERIOS_MCP_ARTIFACTS_DIR": directory}):
        indexes.clear_cache()
        rows = [{"_id": f"form-{i}", "name": f"Форма {i}", "formId": f"form-{i+1}",
                 "description": "Описание обработки данных. " * 30,
                 "nested": {"arguments": [f"value-{i}", "common-value"]}} for i in range(1999)]
        rows.append({"_id": "form-1999", "name": "Последняя форма"})
        source = {"snapshot_id": "scan_" + "b" * 32, "finished_at": "2026-01-01", "complete": True,
                  "target": {"profile": "benchmark", "project_id": "fixture-project"},
                  "objects": {"forms": {"rows": rows}}}
        w.save_snapshot(source)
        target = {"profile": "benchmark", "project_id": "fixture-project"}
        def uncached_find():
            return w.find_usages(w.load_snapshot(source["snapshot_id"], **target), "unmatched-query")
        def cached_find():
            idx, _ = indexes.get_index(source["snapshot_id"], **target)
            return idx.find("unmatched-query")
        baseline_search = timing(uncached_find, repeats)
        cold_search = timing(cached_find, 1)
        warm_search = timing(cached_find, repeats)
        assert uncached_find()["matches"] == cached_find()["matches"]
        def uncached_graph():
            return w.relation_graph(w.load_snapshot(source["snapshot_id"], **target), root_id="form-1999")
        def cached_graph():
            idx, _ = indexes.get_index(source["snapshot_id"], **target)
            return idx.graph(root_id="form-1999")
        baseline_graph = timing(uncached_graph, repeats)
        cold_graph = timing(cached_graph, 1)
        warm_graph = timing(cached_graph, repeats)
        assert uncached_graph()["edges"] == cached_graph()["edges"]
        payload = {"rows": rows, "loaded": len(rows), "complete": True}
        compact = present(payload)
        response = {"source_bytes": len(json_bytes(payload)), "compact_bytes": len(json_bytes(compact)),
                    "preview_rows": len(compact.get("rows", [])),
                    "compact_including_artifact_write": timing(lambda: present(payload), repeats)}
        hydrate = {}
        for workers in (1, 4):
            client = DetailClient(delay)
            def collect():
                return w.collect_snapshot(client, kinds=["reports"], include_details=True, detail_workers=workers)
            stats = timing(collect, repeats)
            stats["requests_per_run"] = len(client.calls) // repeats
            hydrate[str(workers)] = stats
        broad, scoped = ScopeClient(), ScopeClient()
        fake_config = SimpleNamespace(with_project_id=lambda _: broad.config)
        with patch.object(project_health.AlteriosConfig, "from_env", return_value=fake_config), patch.object(project_health, "AlteriosClient", return_value=broad):
            project_health.collect_live_health_inventory(profile="benchmark", project_id="fixture-project")
        health = run_scoped_health(**target, objects=[{"kind": "fields", "id": "field-one"}], client=scoped)
        assert health["summary"]["ok"]
        return {"environment": "offline synthetic fixture; not a live SLA or production speedup",
                "workload": {"rows": len(rows), "detail_objects": 32, "simulated_request_delay_ms": delay * 1000},
                "response": response, "search": {"baseline": baseline_search, "cold": cold_search, "warm": warm_search},
                "graph": {"baseline": baseline_graph, "cold": cold_graph, "warm": warm_graph},
                "hydration_workers": hydrate,
                "preflight_requests": {"full_inventory": broad.calls, "scoped_field_and_type": scoped.calls,
                    "scope_note": "Different coverage by design; scoped checks do not certify full project health."}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args()
    if not 1 <= args.repeats <= 20:
        parser.error("repeats must be 1..20")
    text = json.dumps(benchmark(args.repeats), ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
