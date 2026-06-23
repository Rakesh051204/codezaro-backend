import pytest
from httpx import AsyncClient
from app.main import app

@pytest.mark.asyncio
async def test_register_login():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        # Register
        reg_resp = await ac.post("/auth/register", json={
            "email": "testuser@example.com",
            "password": "testpass123",
            "full_name": "Test User"
        })
        assert reg_resp.status_code == 200
        assert "access_token" in reg_resp.json()

        # Login
        login_resp = await ac.post("/auth/login", data={
            "username": "testuser@example.com",
            "password": "testpass123"
        }, headers={"Content-Type": "application/x-www-form-urlencoded"})
        assert login_resp.status_code == 200
        assert "access_token" in login_resp.json()