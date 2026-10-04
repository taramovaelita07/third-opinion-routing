"""Tests for service-level endpoints."""

import asyncio

from httpx import ASGITransport, AsyncClient

from app.main import app


def test_health_check() -> None:
    async def request_health():
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get("/health")

    response = asyncio.run(request_health())

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "third-opinion-routing-api",
        "version": "1.4.0",
    }


def test_root_serves_clinician_interface() -> None:
    async def request_root():
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get("/")

    response = asyncio.run(request_root())

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Третье мнение" in response.text
    assert "Кабинет врача" in response.text
