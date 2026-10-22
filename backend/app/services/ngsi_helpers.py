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


def tracker_parcel_urn(tracker: dict) -> str | None:
    """Parcel URN from ``hasAgriParcel`` / ``refAgriParcel`` (Relationship or plain string)."""
    for attr in ("hasAgriParcel", "refAgriParcel"):
        raw = tracker.get(attr)
        if isinstance(raw, dict):
            raw = raw.get("object")
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return None


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
