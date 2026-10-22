"""Tests for biologyCache push-read."""

from datetime import datetime, timedelta, timezone

from app.services.biology_cache import (
    is_biology_cache_fresh,
    read_biology_cache,
)


def test_read_biology_cache_scalars():
    tracker = {
        "biologyCache": {
            "value": {
                "updatedAt": "2026-06-27T10:00:00Z",
                "scalars": {"stress_index": 0.42, "fruit_count_pred": 12.0},
            }
        }
    }
    assert read_biology_cache(tracker) == {
        "stress_index": 0.42,
        "fruit_count_pred": 12.0,
    }


def test_read_biology_cache_flat():
    tracker = {
        "biologyCache": {
            "value": {
                "updatedAt": "2026-06-27T10:00:00Z",
                "stress_index": 0.1,
            }
        }
    }
    assert read_biology_cache(tracker)["stress_index"] == 0.1


def test_cache_freshness():
    recent = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    tracker = {"biologyCache": {"value": {"updatedAt": recent, "stress_index": 0.2}}}
    assert is_biology_cache_fresh(tracker, max_age_s=300) is True

    old = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    stale = {"biologyCache": {"value": {"updatedAt": old, "stress_index": 0.2}}}
    assert is_biology_cache_fresh(stale, max_age_s=300) is False
