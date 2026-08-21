"""Trackers must resolve their device through hasDevice as well as refDevice.

`refDevice` is the deprecated ref<Type> pattern; the platform standard is the SDM
relationship `hasDevice`. Agrienergy only ever reads this attribute — it is written
by whatever provisions the tracker entity — so the migration starts by widening the
read (the Expand half of Expand and Contract). Dropping refDevice before every
writer has moved would break existing trackers.

Shapes differ: a Relationship carries `object`, a Property carries `value`.
"""

import pytest
from app.services.orion import resolve_device_ref

DEV = "urn:ngsi-ld:Device:inverter-1"


class TestHasDevice:
    def test_relationship_object(self):
        assert resolve_device_ref({"hasDevice": {"type": "Relationship", "object": DEV}}) == DEV

    def test_plain_string(self):
        assert resolve_device_ref({"hasDevice": DEV}) == DEV

    def test_keyvalues_form(self):
        """options=keyValues flattens a Relationship to its target string."""
        assert resolve_device_ref({"hasDevice": {"object": DEV}}) == DEV


class TestRefDeviceStillWorks:
    def test_property_value(self):
        assert resolve_device_ref({"refDevice": {"type": "Property", "value": DEV}}) == DEV

    def test_plain_string(self):
        assert resolve_device_ref({"refDevice": DEV}) == DEV


class TestPrecedenceAndAbsence:
    def test_has_device_wins(self):
        tracker = {
            "hasDevice": {"type": "Relationship", "object": DEV},
            "refDevice": {"type": "Property", "value": "urn:ngsi-ld:Device:stale"},
        }
        assert resolve_device_ref(tracker) == DEV

    def test_missing_returns_none(self):
        assert resolve_device_ref({}) is None

    @pytest.mark.parametrize("empty", ["", "   ", None])
    def test_blank_returns_none(self, empty):
        assert resolve_device_ref({"hasDevice": empty}) is None
        assert resolve_device_ref({"refDevice": empty}) is None

    def test_non_string_returns_none(self):
        assert resolve_device_ref({"hasDevice": {"object": 42}}) is None

    def test_value_is_stripped(self):
        assert resolve_device_ref({"hasDevice": f"  {DEV}  "}) == DEV


class TestCallSitesUseTheHelper:
    def test_tracker_evaluator(self):
        from app.services import tracker_evaluator

        assert "resolve_device_ref" in tracker_evaluator.__dict__ or hasattr(
            tracker_evaluator, "resolve_device_ref"
        )

    def test_daily_aggregation_resolves_has_device(self):
        from app.services.daily_aggregation import _ref_device_id

        assert _ref_device_id({"hasDevice": {"type": "Relationship", "object": DEV}}) == DEV
