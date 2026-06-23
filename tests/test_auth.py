import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_register_and_login(client: AsyncClient):
    # Register
    register_resp = await client.post("/auth/register", json={
        "email": "test_ci@example.com",
        "password": "ci_password123",
        "full_name": "CI User"
    })
    assert register_resp.status_code == 200
    tokens = register_resp.json()
    assert "access_token" in tokens

    # Login
    login_resp = await client.post("/auth/login", data={
        "username": "test_ci@example.com",
        "password": "ci_password123"
    }, headers={"Content-Type": "application/x-www-form-urlencoded"})
    assert login_resp.status_code == 200
    assert "access_token" in login_resp.json()