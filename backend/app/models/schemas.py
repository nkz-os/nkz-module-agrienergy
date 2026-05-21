"""Pydantic schemas for simulation and NGSI-LD payloads."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class AgriParcelSpec(BaseModel):
    id: str
    slope: float = Field(default=0.0, description="Pendiente media en grados")
    aspect: float = Field(default=180.0, description="Orientación en grados (180=Sur)")


class PanelSpec(BaseModel):
    """Position of a single panel within an array."""
    lat: float
    lon: float


class PanelArraySpec(BaseModel):
    """Spec for a full array of panels (multi-panel installation)."""
    positions: List[PanelSpec]
    panel_width: float = 2.0
    panel_length: float = 4.0
    clearance_height: float = 2.0


class TrackerSpec(BaseModel):
    """Legacy single-panel tracker spec — kept for backward compatibility."""
    id: str
    panel_width: float
    panel_length: float
    capacity_w: float
    min_tilt: float = -60.0
    max_tilt: float = 60.0
    lat: float
    lon: float
    parent_parcel_id: str


class TelemetryInput(BaseModel):
    timestamp: str
    ghi: float
    dni: float
    dhi: float
    actual_tilt: float
    actual_azimuth: float


class SimulationRequest(BaseModel):
    tracker: Optional[TrackerSpec] = None          # legacy single-panel
    panel_array: Optional[PanelArraySpec] = None   # multi-panel array
    parcel: AgriParcelSpec
    telemetry: TelemetryInput
    target_tilt: float


class SimulationResponse(BaseModel):
    expected_power_w: float
    shadow_area_m2: float
    shadow_polygon_2d: List[tuple]


# -----------------------------------------------------------------------------
# Instant values panel (GET /status)
# -----------------------------------------------------------------------------


class OrientationStatus(BaseModel):
    tilt: float
    azimuth: float


class PowerStatus(BaseModel):
    measured_w: Optional[float] = None
    expected_w: Optional[float] = None


class StorageStatus(BaseModel):
    soc: Optional[float] = None


class SignalMappingItem(BaseModel):
    contextKey: str
    entityId: str
    attribute: str = "value"


class TrackerStatusResponse(BaseModel):
    """Response for GET /status: instant values for frontend panel and Cesium."""
    tracker_id: str
    orientation: OrientationStatus
    power: PowerStatus
    storage: Optional[StorageStatus] = None
    sensors: Dict[str, float] = Field(default_factory=dict)
    signal_mapping: Optional[List[SignalMappingItem]] = None  # current mapping for UI prefill
    active_algorithm_id: Optional[str] = None  # preset id when activeAlgorithm is {"id": "..."}
    timestamp: str


# -----------------------------------------------------------------------------
# Signal sources (GET /signal-sources)
# -----------------------------------------------------------------------------


class SignalSourceAttribute(BaseModel):
    name: str
    last_value: Optional[float] = None


class SignalSource(BaseModel):
    entity_id: str
    entity_name: str
    type: str
    attributes: List[SignalSourceAttribute] = Field(default_factory=list)


class SignalSourcesResponse(BaseModel):
    sources: List[SignalSource] = Field(default_factory=list)


class SignalMappingUpdate(BaseModel):
    signalMapping: List[SignalMappingItem] = Field(default_factory=list)


class AlgorithmUpdate(BaseModel):
    """Body for PATCH trackers/{id}/algorithm. activeAlgorithm: full JSON Logic or { \"id\": \"default:maximize\" }."""
    activeAlgorithm: Dict[str, Any] = Field(..., description="JSON Logic rule or { id: preset_id }")


# -----------------------------------------------------------------------------
# Solar parks (AgriSolarPark entity, Option B)
# -----------------------------------------------------------------------------


class ParkSummary(BaseModel):
    """One solar park (AgriSolarPark entity)."""
    park_id: str
    name: str
    ref_agri_parcel: str  # URN of the parcel
    parcel_name: Optional[str] = None
    tracker_count: int = 0
    tracker_ids: List[str] = Field(default_factory=list)


class ParksResponse(BaseModel):
    parks: List[ParkSummary] = Field(default_factory=list)


class CreateParkRequest(BaseModel):
    name: str
    ref_agri_parcel: str  # URN of AgriParcel (e.g. urn:ngsi-ld:AgriParcel:...)


class ParkTrackerItem(BaseModel):
    tracker_id: str
    name: Optional[str] = None


class ParcelItem(BaseModel):
    """Parcel for dropdown (create park)."""
    id: str
    name: str


class ParcelsResponse(BaseModel):
    parcels: List[ParcelItem] = Field(default_factory=list)
