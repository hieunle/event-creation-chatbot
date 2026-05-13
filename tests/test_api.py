"""API tests for POST /api/register-event."""
from __future__ import annotations

from datetime import date

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.events import router as events_router


pytestmark = pytest.mark.asyncio


@pytest.fixture
def app(repository, memory) -> FastAPI:
    application = FastAPI()
    application.include_router(events_router)
    application.state.repository = repository
    application.state.memory = memory
    return application


@pytest.fixture
async def client(app: FastAPI):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class TestRegisterEvent:
    async def test_valid_payload_succeeds(self, client, sample_event_kwargs):
        payload = {**sample_event_kwargs}
        # JSON-serialise dates / times
        payload["date"] = payload["date"].isoformat()
        payload["time"] = payload["time"].isoformat()
        payload["purchase_start"] = payload["purchase_start"].isoformat()
        payload["purchase_end"] = payload["purchase_end"].isoformat()

        r = await client.post("/api/register-event", json=payload)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "success"
        assert "event_id" in body
        assert sample_event_kwargs["name"] in body["message"]

    async def test_invalid_payload_returns_422(self, client):
        bad = {"name": "X", "date": "March 10th"}  # malformed + missing fields
        r = await client.post("/api/register-event", json=bad)
        assert r.status_code == 422

    async def test_missing_required_field_returns_422(
        self, client, sample_event_kwargs
    ):
        payload = {**sample_event_kwargs}
        del payload["venue_name"]
        payload["date"] = payload["date"].isoformat()
        payload["time"] = payload["time"].isoformat()
        payload["purchase_start"] = payload["purchase_start"].isoformat()
        payload["purchase_end"] = payload["purchase_end"].isoformat()
        r = await client.post("/api/register-event", json=payload)
        assert r.status_code == 422
        assert "venue_name" in r.text

    async def test_duplicate_returns_409(self, client, sample_event_kwargs):
        payload = {**sample_event_kwargs}
        payload["date"] = payload["date"].isoformat()
        payload["time"] = payload["time"].isoformat()
        payload["purchase_start"] = payload["purchase_start"].isoformat()
        payload["purchase_end"] = payload["purchase_end"].isoformat()

        r1 = await client.post("/api/register-event", json=payload)
        assert r1.status_code == 200
        r2 = await client.post("/api/register-event", json=payload)
        assert r2.status_code == 409
        assert "already exists" in r2.text


class TestListEvents:
    async def test_empty_returns_empty_list(self, client):
        r = await client.get("/api/events")
        assert r.status_code == 200
        assert r.json() == {"events": []}

    async def test_lists_saved_events(self, client, sample_event_kwargs):
        payload = {**sample_event_kwargs}
        payload["date"] = payload["date"].isoformat()
        payload["time"] = payload["time"].isoformat()
        payload["purchase_start"] = payload["purchase_start"].isoformat()
        payload["purchase_end"] = payload["purchase_end"].isoformat()
        r1 = await client.post("/api/register-event", json=payload)
        assert r1.status_code == 200

        r = await client.get("/api/events")
        assert r.status_code == 200
        body = r.json()
        assert len(body["events"]) == 1
        assert body["events"][0]["name"] == sample_event_kwargs["name"]
        assert "id" in body["events"][0]
