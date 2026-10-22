"""Prometheus metrics for AgriEnergy closed-loop orchestration."""

from __future__ import annotations

import os
import time
from contextlib import contextmanager

try:
    from prometheus_client import Gauge, Histogram

    PROMETHEUS_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised when dep missing
    PROMETHEUS_AVAILABLE = False

    class _NoopMetric:
        def inc(self, *_args, **_kwargs):
            pass

        def dec(self, *_args, **_kwargs):
            pass

        def observe(self, *_args, **_kwargs):
            pass

    class Gauge(_NoopMetric):  # type: ignore[no-redef]
        def __init__(self, *_args, **_kwargs):
            pass

    class Histogram(_NoopMetric):  # type: ignore[no-redef]
        def __init__(self, *_args, **_kwargs):
            pass


METRICS_ENABLED = os.getenv("METRICS_ENABLED", "true").lower() == "true"

# SOTA backlog: queue depth + tracker eval latency (p99 via PromQL on histogram).
NOTIFY_QUEUE_DEPTH = Gauge(
    "agrienergy_notify_queue_depth",
    "Orion /notify background batches awaiting or running processing",
)

TRACKER_EVAL_LATENCY = Histogram(
    "agrienergy_tracker_eval_latency_seconds",
    "Wall time for evaluate_and_actuate_tracker per tracker",
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)


def enqueue_notify_batch() -> None:
    if METRICS_ENABLED and PROMETHEUS_AVAILABLE:
        NOTIFY_QUEUE_DEPTH.inc()


def dequeue_notify_batch() -> None:
    if METRICS_ENABLED and PROMETHEUS_AVAILABLE:
        NOTIFY_QUEUE_DEPTH.dec()


@contextmanager
def observe_tracker_eval():
    if not METRICS_ENABLED or not PROMETHEUS_AVAILABLE:
        yield
        return
    start = time.perf_counter()
    try:
        yield
    finally:
        TRACKER_EVAL_LATENCY.observe(time.perf_counter() - start)
