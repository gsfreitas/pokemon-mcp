import httpx
import pytest
from starlette.testclient import TestClient

from pokemon_mcp.config import Settings
from pokemon_mcp.http_app import create_http_app
from pokemon_mcp.server import build_server

from .conftest import FakePokeAPI

TOKEN = "s3cr3t-token"
MCP_HEADERS = {"accept": "application/json, text/event-stream", "content-type": "application/json"}
INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}},
}


@pytest.fixture
def http_client() -> TestClient:
    settings = Settings(host="0.0.0.0", auth_tokens=("old-token", TOKEN))
    mcp = build_server(settings, transport=httpx.MockTransport(FakePokeAPI()))
    with TestClient(create_http_app(mcp, settings), base_url="http://testserver") as client:
        yield client


def test_health_is_public(http_client: TestClient) -> None:
    response = http_client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.parametrize("auth", [None, "Bearer wrong", "Basic czNjcjN0", f"bearer{TOKEN}"])
def test_mcp_requires_valid_bearer_token(http_client: TestClient, auth: str | None) -> None:
    headers = MCP_HEADERS | ({"authorization": auth} if auth else {})

    response = http_client.post("/mcp", json=INITIALIZE, headers=headers)

    assert response.status_code == 401
    assert response.headers["www-authenticate"].startswith("Bearer")


@pytest.mark.parametrize("token", [TOKEN, "old-token"])
def test_mcp_accepts_any_configured_token(http_client: TestClient, token: str) -> None:
    response = http_client.post("/mcp", json=INITIALIZE, headers=MCP_HEADERS | {"authorization": f"Bearer {token}"})

    assert response.status_code == 200


def test_refuses_to_start_unauthenticated_outside_loopback() -> None:
    settings = Settings(host="0.0.0.0")

    with pytest.raises(RuntimeError, match="MCP_AUTH_TOKENS"):
        create_http_app(build_server(settings), settings)


def test_allows_unauthenticated_on_loopback() -> None:
    settings = Settings(host="127.0.0.1")

    assert create_http_app(build_server(settings), settings) is not None
