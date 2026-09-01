"""
Elevation service — terrain height per coordinate via platform-native sources.

Cascade (automatic, no user config needed):
  1. LiDAR DTM GeoTIFF — if the parcel has a processed LiDAR layer (sub-meter)
  2. eu-elevation /api/elevation/point — national DEM sources (CNIG 5m ES, IDENA Navarra)
  3. Copernicus 30m — pan-European fallback (handled internally by eu-elevation)
"""

import logging
from typing import List, Tuple, Optional

import httpx

logger = logging.getLogger(__name__)


class ElevationUnavailableError(Exception):
    """Raised when a DEM source answers without a usable elevation (elevation_m is null)."""


# Internal platform services (cluster-internal, no auth needed beyond tenant header)
ELEVATION_API_URL = "http://elevation-api-service:80/api/elevation/point"
LIDAR_API_URL = "http://nkz-module-lidar-api-service:80/api/lidar"
REQUEST_TIMEOUT = 10.0


class ElevationService:
    """Queries terrain elevation using platform-native DEM sources, with in-memory cache."""

    def __init__(self, tenant_id: str = ""):
        self._tenant_id = tenant_id
        self._cache: dict = {}  # "lat,lon" → elevation_m

    @staticmethod
    def _cache_key(lat: float, lon: float) -> str:
        return f"{lat:.5f},{lon:.5f}"

    # ── public API ──────────────────────────────────────────────────────────

    async def get_elevations(
        self, positions: List[Tuple[float, float]], parcel_id: str = ""
    ) -> List[float]:
        """
        Returns elevation in meters for each (lon, lat) position.

        If parcel_id is provided and has LiDAR DTM coverage, uses that (sub-meter).
        Otherwise falls back to eu-elevation national DEM (5m) → Copernicus (30m).
        Falls back to 0.0 on transient errors.
        """
        if not positions:
            return []

        # Try LiDAR DTM first if parcel_id is available
        if parcel_id:
            elevations = await self._try_lidar_dtm(positions, parcel_id)
            if elevations is not None:
                return elevations

        # Fall back to eu-elevation point API
        return await self._query_eu_elevation(positions)

    # ── LiDAR DTM (sub-meter) ──────────────────────────────────────────────

    async def _try_lidar_dtm(
        self, positions: List[Tuple[float, float]], parcel_id: str
    ) -> Optional[List[float]]:
        """Try to get elevations from LiDAR DTM. Returns None if unavailable."""
        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
                # Check if parcel has LiDAR layers
                layers_resp = await client.get(
                    f"{LIDAR_API_URL}/layers",
                    params={"parcel_id": parcel_id},
                    headers={"X-Tenant-ID": self._tenant_id},
                )
                layers_resp.raise_for_status()
                layers = layers_resp.json().get("layers", [])

                # Find a layer with DTM product available
                dtm_layer_id = None
                for layer in layers:
                    products = layer.get("products", [])
                    if "dtm" in products or "DTM" in products:
                        dtm_layer_id = layer.get("id")
                        break

                if not dtm_layer_id:
                    return None

                # Download the DTM GeoTIFF
                dtm_resp = await client.get(
                    f"{LIDAR_API_URL}/export/{dtm_layer_id}/dtm",
                    headers={"X-Tenant-ID": self._tenant_id},
                )
                dtm_resp.raise_for_status()

                # Read elevations from GeoTIFF
                return self._read_geotiff_points(dtm_resp.content, positions)

        except Exception as exc:
            logger.debug("LiDAR DTM unavailable for parcel %s: %s", parcel_id, exc)
            return None

    @staticmethod
    def _read_geotiff_points(
        tiff_bytes: bytes, positions: List[Tuple[float, float]]
    ) -> List[float]:
        """Read elevation at each (lon, lat) from an in-memory GeoTIFF."""
        try:
            import rasterio
            from rasterio.transform import rowcol
        except ImportError:
            logger.warning("rasterio not installed, cannot read LiDAR DTM")
            return [0.0] * len(positions)

        import io
        with rasterio.open(io.BytesIO(tiff_bytes)) as src:
            elevations = []
            for lon, lat in positions:
                try:
                    r, c = rowcol(src.transform, lon, lat)
                    # Clamp to raster bounds
                    r = max(0, min(r, src.height - 1))
                    c = max(0, min(c, src.width - 1))
                    val = float(src.read(1, window=((r, r + 1), (c, c + 1)))[0, 0])
                    # Some DTMs use nodata for invalid pixels
                    if val == src.nodata or val < -999:
                        val = 0.0
                    elevations.append(val)
                except Exception:
                    elevations.append(0.0)
        return elevations

    # ── eu-elevation (5m national / 30m Copernicus) ────────────────────────

    async def _query_eu_elevation(
        self, positions: List[Tuple[float, float]]
    ) -> List[float]:
        """Query the eu-elevation module's point API for each position."""
        # Deduplicate
        unique: List[Tuple[float, float]] = []
        seen: set = set()
        index_map: List[int] = []  # input_idx → unique_idx
        for i, (lon, lat) in enumerate(positions):
            key = self._cache_key(lat, lon)
            if key not in seen:
                unique.append((lon, lat))
                seen.add(key)
            # cache_key matches first occurrence
            index_map.append(
                next(j for j, (ulon, ulat) in enumerate(unique) if (ulon, ulat) == (lon, lat))
            )

        # Query each unique position (internal service with Redis cache → fast)
        elevation_by_idx: dict = {}
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            tasks = []
            for lon, lat in unique:
                tasks.append(self._query_single(client, lat, lon))

            results = await asyncio_gather(*tasks, return_exceptions=True)

        for idx, result in enumerate(results):
            if isinstance(result, ElevationUnavailableError):
                logger.debug(
                    "elevation unavailable for idx %d: %s", idx, result
                )
                elevation_by_idx[idx] = 0.0
            elif isinstance(result, Exception):
                logger.debug("elevation query failed for idx %d: %s", idx, result)
                elevation_by_idx[idx] = 0.0
            else:
                elevation_by_idx[idx] = result
                # Populate cache
                lon, lat = unique[idx]
                self._cache[self._cache_key(lat, lon)] = result

        return [elevation_by_idx.get(index_map[i], 0.0) for i in range(len(positions))]

    async def _query_single(
        self, client: httpx.AsyncClient, lat: float, lon: float
    ) -> float:
        """Query a single elevation point from eu-elevation. Raises on error."""
        resp = await client.get(
            ELEVATION_API_URL,
            params={"lat": lat, "lon": lon},
            headers={"X-Tenant-ID": self._tenant_id},
        )
        resp.raise_for_status()
        data = resp.json()
        elev = data.get("elevation_m")
        if elev is None:
            raise ElevationUnavailableError(
                f"elevation unavailable at lat={lat} lon={lon}"
            )
        return float(elev)


# ── compat shim for Python < 3.11 ──────────────────────────────────────────

async def asyncio_gather(*coros, return_exceptions: bool = False):
    """Backport of asyncio.TaskGroup-like all-settled behaviour."""
    import asyncio
    return await asyncio.gather(*coros, return_exceptions=return_exceptions)
