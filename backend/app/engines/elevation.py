"""
Elevation service — queries real terrain height via OpenTopoData (SRTM 30m).
Free, no API key, suitable for agricultural terrain with sub-30m resolution.
"""

import asyncio
import logging
from typing import List, Tuple, Optional

import httpx

logger = logging.getLogger(__name__)

OPENTOPODATA_URL = "https://api.opentopodata.org/v1/srtm30m"
REQUEST_TIMEOUT = 10.0  # seconds — external API


class ElevationService:
    """Queries terrain elevation for given coordinates, with in-memory cache."""

    def __init__(self):
        self._cache: dict = {}  # (lat, lon) rounded to 5 decimals → elevation_m

    @staticmethod
    def _cache_key(lat: float, lon: float) -> str:
        return f"{lat:.5f},{lon:.5f}"

    async def get_elevations(
        self, positions: List[Tuple[float, float]]
    ) -> List[float]:
        """
        Returns elevation in meters for each (lon, lat) position.
        Falls back to 0.0 on transient errors.
        """
        if not positions:
            return []

        # Build deduplicated list for the API call
        unique_positions: List[Tuple[float, float]] = []
        seen: set = set()
        for lon, lat in positions:
            key = self._cache_key(lat, lon)
            if key not in seen:
                unique_positions.append((lon, lat))
                seen.add(key)

        # Build query string: "lat1,lon1|lat2,lon2|..."
        locations = "|".join(f"{lat},{lon}" for lon, lat in unique_positions)

        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
                resp = await client.get(
                    OPENTOPODATA_URL, params={"locations": locations}
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            logger.warning("Elevation API unavailable, using 0.0 fallback: %s", exc)
            return [0.0] * len(positions)

        # Map API results back: API returns in same order
        results = data.get("results", [])
        elevation_by_key: dict = {}
        for (lon, lat), r in zip(unique_positions, results):
            elevation_by_key[self._cache_key(lat, lon)] = float(
                r.get("elevation", 0.0)
            )

        # Build final list matching input positions
        return [
            elevation_by_key.get(self._cache_key(lat, lon), 0.0)
            for lon, lat in positions
        ]

    def get_cached(self, positions: List[Tuple[float, float]]) -> Optional[List[float]]:
        """Synchronous cache-only lookup. Returns None if any position is missing."""
        result: List[float] = []
        for lon, lat in positions:
            val = self._cache.get(self._cache_key(lat, lon))
            if val is None:
                return None
            result.append(val)
        return result

    def cache(self, positions: List[Tuple[float, float]], elevations: List[float]) -> None:
        """Pre-populate cache from an external source (e.g. DEM upload)."""
        for (lon, lat), elev in zip(positions, elevations):
            self._cache[self._cache_key(lat, lon)] = elev
