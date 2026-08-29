"""NotionHttpClient against respx. Never the network."""

from __future__ import annotations

import httpx
import pytest
import respx

from app.adapters.notion.http import (
    BASE_URL,
    NOTION_VERSION,
    NotionApiError,
    NotionHttpClient,
    TokenBucket,
)


class FakeTime:
    """Injected clock and sleep, so a rate-limit test does not actually sleep.

    A test suite that waits on a real token bucket is a test suite that gets
    deleted.
    """

    def __init__(self) -> None:
        self.now = 0.0
        self.slept: list[float] = []

    def __call__(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


@pytest.fixture
def fake_time():
    return FakeTime()


@pytest.fixture
def client(fake_time):
    return NotionHttpClient(
        token="ntn_test",
        client=httpx.AsyncClient(base_url=BASE_URL),
        bucket=TokenBucket(clock=fake_time, sleep=fake_time.sleep),
        sleep=fake_time.sleep,
    )


@respx.mock
async def test_every_request_carries_the_notion_version_header(client):
    route = respx.get(f"{BASE_URL}/databases/abc").mock(
        return_value=httpx.Response(200, json={"id": "abc"})
    )
    await client.get("/databases/abc")
    assert route.calls.last.request.headers["Notion-Version"] == NOTION_VERSION


@respx.mock
async def test_every_request_carries_the_bearer_token(client):
    route = respx.get(f"{BASE_URL}/databases/abc").mock(
        return_value=httpx.Response(200, json={"id": "abc"})
    )
    await client.get("/databases/abc")
    assert route.calls.last.request.headers["Authorization"] == "Bearer ntn_test"


@respx.mock
async def test_429_is_retried_after_the_retry_after_delay(client, fake_time):
    respx.get(f"{BASE_URL}/x").mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "2.5"}, json={}),
            httpx.Response(200, json={"ok": True}),
        ]
    )
    assert await client.get("/x") == {"ok": True}
    assert fake_time.slept == [2.5]


@respx.mock
async def test_429_without_retry_after_uses_exponential_backoff(client, fake_time):
    respx.get(f"{BASE_URL}/x").mock(
        side_effect=[
            httpx.Response(429, json={}),
            httpx.Response(429, json={}),
            httpx.Response(200, json={"ok": True}),
        ]
    )
    await client.get("/x")
    assert fake_time.slept == [1.0, 2.0]


@respx.mock
async def test_retries_give_up_after_three_attempts(client):
    route = respx.get(f"{BASE_URL}/x").mock(
        return_value=httpx.Response(429, json={"code": "rate_limited", "message": "slow down"})
    )
    with pytest.raises(NotionApiError) as caught:
        await client.get("/x")
    assert route.call_count == 3
    assert caught.value.status == 429


@respx.mock
async def test_500_is_retried(client):
    route = respx.get(f"{BASE_URL}/x").mock(
        side_effect=[httpx.Response(500, json={}), httpx.Response(200, json={"ok": True})]
    )
    await client.get("/x")
    assert route.call_count == 2


@respx.mock
async def test_400_is_not_retried(client):
    """Retrying a 400 just delays the error."""
    route = respx.get(f"{BASE_URL}/x").mock(
        return_value=httpx.Response(400, json={"code": "validation_error", "message": "bad"})
    )
    with pytest.raises(NotionApiError):
        await client.get("/x")
    assert route.call_count == 1


@respx.mock
async def test_404_is_not_retried(client):
    route = respx.get(f"{BASE_URL}/x").mock(
        return_value=httpx.Response(404, json={"code": "object_not_found", "message": "gone"})
    )
    with pytest.raises(NotionApiError):
        await client.get("/x")
    assert route.call_count == 1


@respx.mock
async def test_notion_error_body_is_wrapped_not_leaked(client):
    respx.get(f"{BASE_URL}/x").mock(
        return_value=httpx.Response(
            403,
            json={"code": "restricted_resource", "message": "Integration lacks access"},
        )
    )
    with pytest.raises(NotionApiError) as caught:
        await client.get("/x")
    assert caught.value.code == "restricted_resource"
    assert caught.value.notion_message == "Integration lacks access"


@respx.mock
async def test_a_non_json_error_body_still_produces_a_readable_error(client):
    respx.get(f"{BASE_URL}/x").mock(return_value=httpx.Response(502, text="<html>nginx"))
    with pytest.raises(NotionApiError) as caught:
        await client.get("/x")
    assert caught.value.status == 502


@respx.mock
async def test_a_malformed_retry_after_falls_back_to_backoff(client, fake_time):
    respx.get(f"{BASE_URL}/x").mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "soon"}, json={}),
            httpx.Response(200, json={}),
        ]
    )
    await client.get("/x")
    assert fake_time.slept == [1.0]


@respx.mock
async def test_an_empty_response_body_is_returned_as_an_empty_dict(client):
    respx.delete(f"{BASE_URL}/blocks/b1").mock(return_value=httpx.Response(200))
    assert await client.delete("/blocks/b1") == {}


@respx.mock
async def test_post_and_patch_send_their_payloads(client):
    created = respx.post(f"{BASE_URL}/pages").mock(
        return_value=httpx.Response(200, json={"id": "p1"})
    )
    patched = respx.patch(f"{BASE_URL}/pages/p1").mock(
        return_value=httpx.Response(200, json={"id": "p1"})
    )
    await client.post("/pages", {"a": 1})
    await client.patch("/pages/p1", {"b": 2})
    import json

    assert json.loads(created.calls.last.request.content) == {"a": 1}
    assert json.loads(patched.calls.last.request.content) == {"b": 2}


@respx.mock
async def test_rate_limiter_serialises_a_burst_of_ten_requests(client, fake_time):
    respx.get(f"{BASE_URL}/x").mock(return_value=httpx.Response(200, json={}))

    for _ in range(10):
        await client.get("/x")

    # Capacity 3 is free, the remaining 7 each wait for a token at 2.5/second.
    assert len(fake_time.slept) == 7
    assert all(pytest.approx(0.4, abs=1e-6) == wait for wait in fake_time.slept)


async def test_the_bucket_refills_over_time(fake_time):
    bucket = TokenBucket(clock=fake_time, sleep=fake_time.sleep)
    for _ in range(3):
        await bucket.acquire()
    assert fake_time.slept == []

    fake_time.now += 10.0
    await bucket.acquire()
    assert fake_time.slept == []


async def test_aclose_closes_the_underlying_client():
    inner = httpx.AsyncClient(base_url=BASE_URL)
    await NotionHttpClient(token="t", client=inner).aclose()
    assert inner.is_closed
