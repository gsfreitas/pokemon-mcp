from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from mcp import Client

from pokemon_mcp.config import Settings
from pokemon_mcp.server import build_server


def fake_pokemon(pokemon_id: int, name: str, types: list[str]) -> dict[str, Any]:
    stat_names = ["hp", "attack", "defense", "special-attack", "special-defense", "speed"]
    return {
        "id": pokemon_id,
        "name": name,
        "height": 4,
        "weight": 60,
        "types": [{"slot": i + 1, "type": {"name": t}} for i, t in enumerate(types)],
        "abilities": [{"ability": {"name": "static"}}],
        "stats": [{"stat": {"name": s}, "base_stat": 50} for s in stat_names],
    }


POKEDEX = {
    "pikachu": fake_pokemon(25, "pikachu", ["electric"]),
    "25": fake_pokemon(25, "pikachu", ["electric"]),
    "charizard": fake_pokemon(6, "charizard", ["fire", "flying"]),
}


class FakePokeAPI:
    def __init__(self) -> None:
        self.requests: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request.url.path)
        name = request.url.path.rsplit("/", 1)[-1]
        if name == "boom":
            return httpx.Response(500)
        if name in POKEDEX:
            return httpx.Response(200, json=POKEDEX[name])
        return httpx.Response(404, text="Not Found")


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def fake_api() -> FakePokeAPI:
    return FakePokeAPI()


@pytest.fixture
async def client(fake_api: FakePokeAPI) -> AsyncIterator[Client]:
    server = build_server(Settings(), transport=httpx.MockTransport(fake_api))
    async with Client(server) as c:
        yield c
