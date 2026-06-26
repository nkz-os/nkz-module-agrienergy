"""NGSI-LD entity attribute helpers shared by API routes and tracker evaluator."""


def get_float_attr(entity: dict, key: str, default: float = 0.0) -> float:
    """Extract float from NGSI-LD entity attribute (Property with value)."""
    attr = entity.get(key)
    if attr is None:
        return default
    if isinstance(attr, dict) and "value" in attr:
        try:
            return float(attr["value"])
        except (TypeError, ValueError):
            return default
    try:
        return float(attr)
    except (TypeError, ValueError):
        return default


def get_control_status_from_tracker(tracker: dict) -> str:
    raw = tracker.get("controlStatus", {}).get("value") or tracker.get("controlStatus")
    return raw if raw in ("ok", "degraded") else "ok"


def build_telemetry_for_intelligence(context: dict) -> dict:
    """Map nested algorithm context to Intelligence evaluate_status telemetry keys."""
    telemetry: dict = {}
    sensors = context.get("sensors") or {}
    weather = context.get("weather") or {}
    for key, val in [
        ("soil_moisture", sensors.get("soil_moisture") or weather.get("soil_moisture")),
        ("leaf_temperature", sensors.get("leaf_temperature")),
        ("dendrometer_value", sensors.get("dendrometer_value") or sensors.get("dendrometer_shrinkage")),
        ("par_under_panel", sensors.get("par_under_panel")),
    ]:
        if val is not None and isinstance(val, (int, float)):
            telemetry[key] = float(val)
    return telemetry


def numeric_attributes_from_entity(entity: dict) -> list[tuple[str, float | None]]:
    """Return (attribute_name, last_value) for attributes with numeric value."""
    skip = {"id", "type", "@context", "location"}
    out: list[tuple[str, float | None]] = []
    for key, prop in entity.items():
        if key in skip or not isinstance(prop, dict):
            continue
        val = prop.get("value")
        if val is None:
            continue
        try:
            out.append((key, float(val)))
        except (TypeError, ValueError):
            continue
    return out


def entity_name(entity: dict) -> str:
    """Extract display name from NGSI-LD entity."""
    name = entity.get("name")
    if isinstance(name, dict) and "value" in name:
        return str(name["value"])
    if isinstance(name, str):
        return name
    return entity.get("id", "")


def ref_agri_parcel_from_entity(entity: dict) -> str | None:
    """Extract parcel URN from hasAgriParcel relationship."""
    ref = entity.get("hasAgriParcel") or {}
    if isinstance(ref, dict):
        return ref.get("object") or ref.get("value")
    return str(ref) if ref else None
