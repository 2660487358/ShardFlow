from httpx import ASGITransport, AsyncClient


async def test_health_check():
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/agent/v1/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
