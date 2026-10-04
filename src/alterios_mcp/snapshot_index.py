"""Bounded process-local LRU of parsed, target-isolated snapshot indexes."""
from __future__ import annotations

import json
import re
import time
from collections import OrderedDict, deque
from threading import RLock

from . import read_workflows as w
from .write_plan import artifact_root

MAX_CACHE_BYTES = 64 * 1024 * 1024  # conservative index weight, not an RSS promise
MAX_ENTRIES = 4
TTL_SECONDS = 300
_cache = OrderedDict()
_lock = RLock()


class SnapshotIndex:
    def __init__(self, snapshot, raw_bytes):
        self.snapshot = snapshot
        self.values = []
        self.nodes = []
        self.by_id = {}
        self.keys = {}
        self.edges = None
        self.adjacency = None
        self.lock = RLock()
        self.weight = raw_bytes
        self.indexed = True
        for kind, identity, row in w.snapshot_records(snapshot):
            key = kind + ":" + identity
            self.by_id.setdefault(identity, []).append(key)
            self.keys[(kind, identity)] = key
            self.nodes.append({"key": key, "kind": kind, "id": identity,
                               "name": row.get("name"), "mname": row.get("mname")})
            self.weight += 512
            for path, value in w.walk(row):
                if isinstance(value, str):
                    self.weight += 256 + 4 * (len(path) + len(value))
                    if self.weight > MAX_CACHE_BYTES:
                        self.indexed = False
                        self.values.clear()
                        self.nodes.clear()
                        self.by_id.clear()
                        self.keys.clear()
                        return
                    self.values.append((kind, identity, row.get("name"), path, value, value.casefold()))

    def find(self, query, max_matches=200):
        if not query.strip() or len(query) > 256 or not 1 <= max_matches <= 5000:
            raise ValueError("Query or max_matches outside bounds")
        if not self.indexed:
            return w.find_usages(self.snapshot, query, max_matches=max_matches)
        matches = []
        needle = query.casefold()
        for kind, identity, name, path, _, folded in self.values:
            if needle in folded:
                matches.append({"kind": kind, "object_id": identity, "name": name,
                                "path": path, "match_type": "literal"})
                if len(matches) > max_matches:
                    break
        truncated = len(matches) > max_matches
        return {"snapshot_id": self.snapshot["snapshot_id"], "source_time": self.snapshot["finished_at"],
                "matches": matches[:max_matches], "truncated": truncated,
                "complete_within_snapshot": bool(self.snapshot["complete"]) and not truncated,
                "limitations": [*self.snapshot.get("limitations", []),
                                "Literal search; computed references and omitted payloads remain unverified."]}

    def graph(self, root_id=None, max_edges=5000):
        if not 1 <= max_edges <= 20000:
            raise ValueError("max_edges outside bounds")
        if not self.indexed:
            return w.relation_graph(self.snapshot, root_id=root_id, max_edges=max_edges)
        with self.lock:
            if self.edges is None:
                edges, adjacency = [], {}
                for kind, identity, _, path, value, _ in self.values:
                    if path in {"/_id", "/id"}:
                        continue
                    for target in self.by_id.get(value, []):
                        # Keep graph caches bounded even for repeated IDs.
                        if len(edges) >= 20000:
                            return w.relation_graph(self.snapshot, root_id=root_id, max_edges=max_edges)
                        source = self.keys[(kind, identity)]
                        edges.append({"source": source, "target": target, "path": path,
                                      "evidence": "exact scalar ID match"})
                        adjacency.setdefault(source, set()).add(target)
                        adjacency.setdefault(target, set()).add(source)
                self.edges, self.adjacency = edges, adjacency
            nodes, edges = self.nodes, self.edges
            if root_id:
                selected = set(self.by_id.get(root_id, []))
                if not selected:
                    raise ValueError("Root not present in snapshot")
                queue = deque(selected)
                while queue:
                    for neighbor in self.adjacency.get(queue.popleft(), ()):
                        if neighbor not in selected:
                            selected.add(neighbor)
                            queue.append(neighbor)
                nodes = [node for node in nodes if node["key"] in selected]
                edges = [edge for edge in edges if edge["source"] in selected]
            truncated = len(edges) > max_edges
            return {"nodes": [dict(n) for n in nodes], "edges": [dict(e) for e in edges[:max_edges]],
                    "truncated": truncated, "complete_within_snapshot": bool(self.snapshot["complete"]) and not truncated,
                    "limitations": ["Static ID links only; no proof of dynamic script dependencies.",
                                     *self.snapshot.get("limitations", [])]}


def clear_cache():
    with _lock:
        _cache.clear()


def get_index(snapshot_id, *, profile, project_id, refresh=False):
    if not profile.strip() or not project_id.strip() or not re.fullmatch(r"scan_[0-9a-f]{32}", snapshot_id):
        raise ValueError("Explicit target and valid snapshot ID are required")
    root = (artifact_root() / "read-snapshots").resolve()
    path = (root / (snapshot_id + ".json")).resolve()
    if not path.is_relative_to(root):
        raise ValueError("Invalid snapshot path")
    stat = path.stat()
    if stat.st_size > 100 * 1024 * 1024:
        raise ValueError("Snapshot exceeds read budget")
    key = (str(path), profile, project_id)
    signature = (stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size, stat.st_ino)
    now = time.monotonic()
    with _lock:
        for old in list(_cache):
            if now - _cache[old][0] >= TTL_SECONDS:
                del _cache[old]
        cached = _cache.get(key)
        if cached and cached[1] == signature and not refresh:
            _cache.move_to_end(key)
            return cached[2], {"hit": True, "index_hit": True, "age_seconds": round(now - cached[0], 3)}
        _cache.pop(key, None)
        raw = path.read_bytes()
        if len(raw) > 100 * 1024 * 1024 or path.stat().st_mtime_ns != stat.st_mtime_ns:
            raise ValueError("Snapshot changed during read or exceeded budget")
        snapshot = json.loads(raw)
        if snapshot.get("target") != {"profile": profile, "project_id": project_id}:
            raise ValueError("Snapshot target does not match explicit profile/project")
        index = SnapshotIndex(snapshot, len(raw))
        # Reserve graph memory as well as flattened-value index storage.
        weight = index.weight + 20000 * 1024
        if index.indexed and weight <= MAX_CACHE_BYTES:
            while _cache and (len(_cache) >= MAX_ENTRIES or sum(v[3] for v in _cache.values()) + weight > MAX_CACHE_BYTES):
                _cache.popitem(last=False)
            _cache[key] = (now, signature, index, weight)
        return index, {"hit": False, "index_hit": False, "stored": key in _cache,
                       "indexed": index.indexed, "age_seconds": 0}
