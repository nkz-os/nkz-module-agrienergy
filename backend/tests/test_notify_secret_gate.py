"""ReceiverInfo auth: the /notify gate and the subscription creator header.

The receiver is flag-gated: NOTIFY_REQUIRE_INTERNAL_SECRET (default off) keeps the
current behavior until subscription creators have converged to send the header, then
flips on with no code deploy. The creator only sends receiverInfo when the env var is
set, so a 204 must never be withheld before the flag is on.
"""

from tests.conftest import API, TENANT, make_notification

NOTIFY = f"{API}/notify"
SECRET = "s3cret"


def _post(anon_client, secret=None):
    headers = {"NGSILD-Tenant": TENANT}
    if secret is not None:
        headers["X-Internal-Service-Secret"] = secret
    return anon_client.post(NOTIFY, json=make_notification([]), headers=headers)


def test_gate_off_by_default(anon_client, monkeypatch):
    monkeypatch.delenv("NOTIFY_REQUIRE_INTERNAL_SECRET", raising=False)
    monkeypatch.delenv("INTERNAL_SERVICE_SECRET", raising=False)
    assert _post(anon_client).status_code == 204


def test_gate_on_rejects_missing_secret(anon_client, monkeypatch):
    monkeypatch.setenv("NOTIFY_REQUIRE_INTERNAL_SECRET", "1")
    monkeypatch.setenv("INTERNAL_SERVICE_SECRET", SECRET)
    assert _post(anon_client).status_code == 401


def test_gate_on_rejects_wrong_secret(anon_client, monkeypatch):
    monkeypatch.setenv("NOTIFY_REQUIRE_INTERNAL_SECRET", "true")
    monkeypatch.setenv("INTERNAL_SERVICE_SECRET", SECRET)
    assert _post(anon_client, "wrong").status_code == 401


def test_gate_on_accepts_correct_secret(anon_client, monkeypatch):
    monkeypatch.setenv("NOTIFY_REQUIRE_INTERNAL_SECRET", "on")
    monkeypatch.setenv("INTERNAL_SERVICE_SECRET", SECRET)
    assert _post(anon_client, SECRET).status_code == 204


def test_creator_sends_receiver_info_when_secret_set(monkeypatch):
    monkeypatch.setenv("INTERNAL_SERVICE_SECRET", SECRET)
    from app.services.subscriptions import _build_registrar
    registrar = _build_registrar()
    assert registrar.notification_headers == {"X-Internal-Service-Secret": SECRET}


def test_creator_omits_receiver_info_without_secret(monkeypatch):
    monkeypatch.delenv("INTERNAL_SERVICE_SECRET", raising=False)
    from app.services.subscriptions import _build_registrar
    registrar = _build_registrar()
    assert registrar.notification_headers == {}
