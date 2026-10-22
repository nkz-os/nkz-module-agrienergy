"""Contract: the Orion-LD notification endpoint must answer 204 with no body.

Orion-LD validates a notification response by looking for the literal string
``Content-Length:`` with a **case-sensitive** ``strstr`` and only skips that check
when the status is exactly 204::

    char* contentLenP = strstr(headers, "Content-Length:");
    if (contentLenP == NULL) { if (httpStatus != 204) -> notificationFailure(...) }

uvicorn/h11 emits response headers lower-cased (``content-length:``) — legal per
RFC 7230, invisible to that ``strstr``. So a 200 + body is counted as a failed
notification, and Orion deactivates the subscription after 3 consecutive failures.

This endpoint previously answered ``200 {"status": "accepted", ...}``, which meant
every notification Orion sent it was recorded as a failure.
"""

from tests.conftest import API, TENANT, make_notification

NOTIFY = f"{API}/notify"

EMPTY_NOTIFICATION_ENTITIES: list[dict] = []


def test_notification_endpoint_answers_204_without_body(anon_client, orion_world):
    response = anon_client.post(
        NOTIFY,
        json=make_notification(EMPTY_NOTIFICATION_ENTITIES),
        headers={"NGSILD-Tenant": TENANT},
    )

    assert response.status_code == 204, (
        f"/notify answered {response.status_code}; Orion-LD counts anything other than "
        "204 as a notification failure unless the response carries a capitalised "
        "'Content-Length:' header, which uvicorn never emits. Three consecutive "
        "failures deactivate the subscription."
    )
    assert response.content == b"", (
        f"/notify returned a body with 204: {response.content!r}. "
        "A body forces a content-length header and defeats the purpose."
    )


def test_missing_tenant_still_fails_loudly(anon_client, orion_world):
    """204 is for success only — a request Orion cannot have sent must still 4xx."""
    response = anon_client.post(NOTIFY, json=make_notification([]))

    assert response.status_code == 400, (
        f"a tenant-less notification answered {response.status_code}; it must be a 4xx "
        "so the failure is visible instead of being silently acknowledged."
    )
