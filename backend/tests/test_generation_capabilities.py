import httpx
import pytest
from app import routers


@pytest.mark.asyncio
@pytest.mark.parametrize("available", [True, False])
async def test_frontend_capabilities_follow_adapter_readiness(client, monkeypatch, available):
    class AdapterClient:
        def __init__(self, **kwargs):
            assert kwargs["trust_env"] is False
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def get(self, url):
            if not available:
                raise httpx.ConnectError("offline")
            return httpx.Response(200, json={"available_modes": ["high_quality"], "pbr_required": True}, request=httpx.Request("GET", url))

    monkeypatch.setattr(routers.httpx, "AsyncClient", AdapterClient)
    response = await client.get("/api/v1/generation/capabilities")
    assert response.status_code == (200 if available else 503)
    if available:
        assert response.json()["available_modes"] == ["high_quality"]
