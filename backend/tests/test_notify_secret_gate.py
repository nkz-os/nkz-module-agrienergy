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


def test_creator_passes_secret_to_registrar_not_headers(monkeypatch):
    """The registrar owns the receiver auth header; derived tokens follow the env flag."""
    monkeypatch.setenv("INTERNAL_SERVICE_SECRET", SECRET)
    monkeypatch.delenv("NKZ_NOTIFY_DERIVED_TOKENS", raising=False)
    from app.services.subscriptions import _build_registrar
    registrar = _build_registrar()
    assert registrar.internal_secret == SECRET
    assert registrar.derived_tokens is False
    assert registrar.notification_headers == {}

    monkeypatch.setenv("NKZ_NOTIFY_DERIVED_TOKENS", "true")
    assert _build_registrar().derived_tokens is True


def test_creator_omits_receiver_info_without_secret(monkeypatch):
    monkeypatch.delenv("INTERNAL_SERVICE_SECRET", raising=False)
    from app.services.subscriptions import _build_registrar
    registrar = _build_registrar()
    assert registrar.notification_headers == {}


def test_derived_token_accepted_once_master_is_refused(anon_client, monkeypatch):
    """The token bound to this tenant and host passes after the master is contracted;
    the master and a token of another tenant do not."""
    from nkz_platform_sdk.notify_auth import TOKEN_HEADER, notification_token

    monkeypatch.setenv("NOTIFY_REQUIRE_INTERNAL_SECRET", "true")
    monkeypatch.setenv("NKZ_NOTIFY_ACCEPT_MASTER", "false")
    monkeypatch.setenv("INTERNAL_SERVICE_SECRET", SECRET)
    # Starlette's TestClient sends Host: testserver; the token binds to that host.
    token = notification_token(SECRET, TENANT, "testserver")
    body = make_notification([])

    ok = anon_client.post(NOTIFY, json=body, headers={"NGSILD-Tenant": TENANT, TOKEN_HEADER: token})
    assert ok.status_code == 204
    other = anon_client.post(NOTIFY, json=body, headers={"NGSILD-Tenant": "tenant-b", TOKEN_HEADER: token})
    assert other.status_code == 401
    assert _post(anon_client, SECRET).status_code == 401
