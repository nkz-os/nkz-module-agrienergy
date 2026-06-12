"""Ground-truth tests for ShadowEngine (2.5D vector geometry)."""

import numpy as np
import pytest

from app.engines.shadow_engine import ShadowEngine

E = ShadowEngine()
W, L = 2.0, 4.0
AREA = W * L


def shadow(**kw):
    base = dict(
        panel_width=W, panel_length=L, panel_tilt=0.0, panel_azimuth=180.0,
        solar_elevation=90.0, solar_azimuth=180.0, clearance_height=2.0,
        terrain_slope=0.0, terrain_aspect=180.0,
    )
    base.update(kw)
    return E.calculate_shadow_polygon(**base)


class TestSinglePanel:
    def test_zenith_flat_panel_shadow_equals_panel_area(self):
        res = shadow(solar_elevation=90.0, panel_tilt=0.0)
        assert res["area_m2"] == pytest.approx(AREA, rel=0.01)

    def test_sun_below_horizon_no_shadow(self):
        assert shadow(solar_elevation=0.0)["area_m2"] == 0.0
        assert shadow(solar_elevation=-10.0)["area_m2"] == 0.0

    def test_vertical_panel_at_zenith_minimal_shadow(self):
        res = shadow(solar_elevation=90.0, panel_tilt=90.0)
        assert res["area_m2"] < AREA * 0.05

    def test_low_sun_elongates_shadow(self):
        high = shadow(solar_elevation=60.0)["area_m2"]
        low = shadow(solar_elevation=15.0)["area_m2"]
        assert low > high

    def test_low_sun_shadow_opposite_to_solar_azimuth(self):
        # Sun in the south (az=180), low elevation -> shadow extends north (+y)
        res = shadow(solar_elevation=20.0, solar_azimuth=180.0)
        ys = [p[1] for p in res["polygon"]]
        assert max(ys) > 0

    def test_sun_east_casts_shadow_west(self):
        # Sun in the east (az=90), low elevation -> shadow extends west (-x)
        res = shadow(solar_elevation=20.0, solar_azimuth=90.0)
        xs = [p[0] for p in res["polygon"]]
        assert min(xs) < 0
        # centroid clearly west of the panel
        assert sum(xs) / len(xs) < -1.0

    def test_tilt_reduces_horizontal_footprint_at_zenith(self):
        flat = shadow(panel_tilt=0.0)["area_m2"]
        tilted = shadow(panel_tilt=45.0)["area_m2"]
        assert tilted < flat

    def test_polygon_is_closed_ring_when_present(self):
        res = shadow(solar_elevation=45.0)
        assert len(res["polygon"]) >= 4
        assert res["polygon"][0] == res["polygon"][-1]


class TestArrayShadow:
    POS = [(-2.0, 43.3), (-2.0001, 43.3), (-2.0002, 43.3)]  # ~8m spacing E-W

    def arr(self, **kw):
        base = dict(
            panel_positions=self.POS, panel_width=W, panel_length=L,
            panel_tilt=0.0, panel_azimuth=180.0,
            solar_elevation=90.0, solar_azimuth=180.0,
        )
        base.update(kw)
        return E.calculate_array_shadow(**base)

    def test_empty_positions(self):
        res = E.calculate_array_shadow(
            panel_positions=[], panel_width=W, panel_length=L,
            panel_tilt=0, panel_azimuth=180, solar_elevation=90, solar_azimuth=180,
        )
        assert res["area_m2"] == 0.0 and res["individual_polygons"] == []

    def test_disjoint_panels_area_sums(self):
        res = self.arr()
        assert res["area_m2"] == pytest.approx(3 * AREA, rel=0.05)
        assert len(res["individual_polygons"]) == 3

    def test_sun_below_horizon_array(self):
        res = self.arr(solar_elevation=-5.0)
        assert res["area_m2"] == 0.0
        assert res["self_shading"]["shaded_indices"] == []

    def test_self_shading_keys_present(self):
        res = self.arr()
        ss = res["self_shading"]
        assert set(ss.keys()) == {"shaded_indices", "occlusion_fraction",
                                  "total_occluded_area_m2"}
        assert len(ss["occlusion_fraction"]) == len(self.POS)


class TestLocalTerrain:
    def test_isolated_panel_falls_back(self):
        slope, aspect = ShadowEngine._local_terrain(
            0, [(-2.0, 43.3)], [100.0], 81000.0, 111320.0,
            fallback_slope=7.0, fallback_aspect=90.0,
        )
        assert (slope, aspect) == (7.0, 90.0)

    def test_two_panels_slope_from_elevation_delta(self):
        # neighbor 100m east, 10m higher -> slope atan(10/100) ~ 5.7 deg
        positions = [(-2.0, 43.3), (-2.0 + 100.0 / 81000.0, 43.3)]
        slope, aspect = ShadowEngine._local_terrain(
            0, positions, [0.0, 10.0], 81000.0, 111320.0,
        )
        assert slope == pytest.approx(5.71, abs=0.3)
        # neighbor is higher -> downhill faces the neighbor bearing (east, 90)
        assert aspect == pytest.approx(90.0, abs=5.0)

    def test_flat_neighbors_zero_slope(self):
        positions = [(-2.0, 43.3), (-2.001, 43.3)]
        slope, _ = ShadowEngine._local_terrain(
            0, positions, [50.0, 50.0], 81000.0, 111320.0,
        )
        assert slope == pytest.approx(0.0, abs=0.01)


class TestSelfShading:
    def test_low_sun_row_shades_next_row(self):
        # Two panels 5m apart north-south, sun very low in the south:
        # the southern panel shades the northern one.
        positions = [(-2.0, 43.3), (-2.0, 43.3 + 5.0 / 111320.0)]
        ss = E.compute_self_shading(
            panel_positions=positions, panel_width=W, panel_length=L,
            panel_tilt=30.0, panel_azimuth=180.0,
            solar_elevation=10.0, solar_azimuth=180.0, clearance_height=2.0,
        )
        assert 1 in ss["shaded_indices"]
        assert 0.0 < ss["occlusion_fraction"][1] <= 1.0
        assert ss["total_occluded_area_m2"] > 0.0

    def test_high_sun_no_self_shading(self):
        positions = [(-2.0, 43.3), (-2.0, 43.3 + 5.0 / 111320.0)]
        ss = E.compute_self_shading(
            panel_positions=positions, panel_width=W, panel_length=L,
            panel_tilt=30.0, panel_azimuth=180.0,
            solar_elevation=85.0, solar_azimuth=180.0, clearance_height=2.0,
        )
        assert ss["shaded_indices"] == []

    def test_single_panel_never_self_shades(self):
        ss = E.compute_self_shading(
            panel_positions=[(-2.0, 43.3)], panel_width=W, panel_length=L,
            panel_tilt=30.0, panel_azimuth=180.0,
            solar_elevation=10.0, solar_azimuth=180.0,
        )
        assert ss == {"shaded_indices": [], "occlusion_fraction": [0.0],
                      "total_occluded_area_m2": 0.0}
