"""Trapezoidal integration of power (W) time series → energy (Wh)."""

from __future__ import annotations

from datetime import datetime, timezone


def parse_iso_ts(value: str) -> datetime:
    """Parse ISO-8601 timestamp to UTC-aware datetime."""
    text = value.replace("Z", "+00:00")
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def trapezoidal_wh(points: list[dict]) -> float:
    """Integrate power samples (W) over time → watt-hours (Wh).

    Points must be sorted oldest-first with keys ``ts`` (ISO-8601) and ``value`` (W).
    Negative power is clamped to zero (export-only generation accounting).
    """
    if len(points) < 2:
        return 0.0

    total_wh = 0.0
    for i in range(1, len(points)):
        t0 = parse_iso_ts(points[i - 1]["ts"])
        t1 = parse_iso_ts(points[i]["ts"])
        dt_hours = (t1 - t0).total_seconds() / 3600.0
        if dt_hours <= 0:
            continue
        p0 = max(0.0, float(points[i - 1]["value"]))
        p1 = max(0.0, float(points[i]["value"]))
        total_wh += (p0 + p1) / 2.0 * dt_hours
    return round(total_wh, 4)
