import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_review_submission(client: AsyncClient):
    # Register and get token
    reg = await client.post("/auth/register", json={
        "email": "review_ci@example.com",
        "password": "ci_password123",
        "full_name": "Review CI"
    })
    assert reg.status_code == 200
    token = reg.json()["access_token"]

    # Submit a review
    review_resp = await client.post("/review/", json={
        "code": "def add(a,b): return a+b",
        "language": "python"
    }, headers={"Authorization": f"Bearer {token}"})
    assert review_resp.status_code == 200
    data = review_resp.json()
    assert "review_result" in data
    assert data["model_used"] == "CodeZaro AI"