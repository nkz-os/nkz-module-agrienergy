"""
Subscription registrar placeholder — implemented in Task 10.
Stub exists so conftest.py can monkeypatch get_orion without ImportError.
"""
from app.services.orion import get_orion  # noqa: F401 — re-export for monkeypatching
