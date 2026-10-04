"""Per-call counters; no URLs, credentials or payloads are collected."""
from __future__ import annotations

import json
import time
from contextvars import ContextVar
from functools import wraps
from threading import Lock
from typing import Any


class Metrics:
    def __init__(self):
        self.started = time.perf_counter()
        self.http_requests = 0
        self.http_errors = 0
        self.http_ms = 0.0
        self.lock = Lock()

    def http(self, elapsed, failed=False):
        with self.lock:
            self.http_requests += 1
            self.http_errors += int(failed)
            self.http_ms += elapsed * 1000

    def result(self):
        return {"duration_ms": round((time.perf_counter() - self.started) * 1000, 3),
                "http_requests": self.http_requests, "http_errors": self.http_errors,
                "http_elapsed_ms": round(self.http_ms, 3)}


current_metrics: ContextVar[Metrics | None] = ContextVar("alterios_metrics", default=None)


def json_bytes(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def track_http(function):
    @wraps(function)
    def call(*args, **kwargs):
        started = time.perf_counter()
        failed = False
        try:
            return function(*args, **kwargs)
        except Exception:
            failed = True
            raise
        finally:
            metrics = current_metrics.get()
            if metrics:
                metrics.http(time.perf_counter() - started, failed)
    return call


def measured(function):
    @wraps(function)
    def call(*args, **kwargs):
        if current_metrics.get() is not None:
            return function(*args, **kwargs)
        metrics = Metrics()
        token = current_metrics.set(metrics)
        try:
            result = function(*args, **kwargs)
            result["metrics"] = metrics.result()
            # Measure the final JSON representation, including the metric itself.
            for _ in range(4):
                result["metrics"]["response_bytes"] = len(json_bytes(result))
            return result
        finally:
            current_metrics.reset(token)
    return call
