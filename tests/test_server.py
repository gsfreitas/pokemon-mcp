import pytest
from mcp import Client

from pokemon_mcp.pokeapi import PokeAPIError, normalize_identifier

from .conftest import FakePokeAPI

pytestmark = pytest.mark.anyio


async def test_tools_are_listed_with_annotations_and_output_schema(client: Client) -> None:
    tools = {t.name: t for t in (await client.list_tools()).tools}

    assert set(tools) == {"get_pokemon_info", "create_tournament_squad"}
    for tool in tools.values():
        assert tool.annotations is not None
        assert tool.annotations.read_only_hint is True
        assert tool.output_schema is not None


async def test_get_pokemon_info_returns_structured_content(client: Client) -> None:
    result = await client.call_tool("get_pokemon_info", {"pokemon_name": "  Pikachu "})

    assert not result.is_error
    assert result.structured_content is not None
    assert result.structured_content["name"] == "pikachu"
    assert result.structured_content["height_m"] == 0.4
    assert result.structured_content["base_stat_total"] == 300


async def test_get_pokemon_info_not_found_is_tool_error(client: Client) -> None:
    result = await client.call_tool("get_pokemon_info", {"pokemon_name": "missingno"})

    assert result.is_error
    assert "não encontrado" in result.content[0].text


async def test_upstream_failure_is_tool_error(client: Client) -> None:
    result = await client.call_tool("get_pokemon_info", {"pokemon_name": "boom"})

    assert result.is_error
    assert "HTTP 500" in result.content[0].text


async def test_results_are_cached(client: Client, fake_api: FakePokeAPI) -> None:
    await client.call_tool("get_pokemon_info", {"pokemon_name": "pikachu"})
    await client.call_tool("get_pokemon_info", {"pokemon_name": "25"})

    assert fake_api.requests == ["/api/v2/pokemon/pikachu"]


async def test_squad_reports_partial_failures_and_duplicates(client: Client) -> None:
    result = await client.call_tool(
        "create_tournament_squad",
        {"pokemon_names": ["pikachu", "charizard", "missingno", "25"]},
    )

    assert not result.is_error
    squad = result.structured_content
    assert [m["name"] for m in squad["members"]] == ["pikachu", "charizard"]
    assert [e["name"] for e in squad["errors"]] == ["missingno", "25"]
    assert squad["type_coverage"] == ["electric", "fire", "flying"]


async def test_squad_rejects_more_than_six(client: Client) -> None:
    result = await client.call_tool("create_tournament_squad", {"pokemon_names": ["pikachu"] * 7})

    assert result.is_error


async def test_squad_with_no_valid_members_is_error(client: Client) -> None:
    result = await client.call_tool("create_tournament_squad", {"pokemon_names": ["missingno"]})

    assert result.is_error
    assert "Nenhum Pokémon válido" in result.content[0].text


async def test_resource_template_returns_json(client: Client) -> None:
    result = await client.read_resource("pokemon://charizard")

    assert '"name": "charizard"' in result.contents[0].text


async def test_prompt_mentions_squad_tool(client: Client) -> None:
    result = await client.get_prompt("analyze_squad", {"pokemon_names": "pikachu, charizard"})

    assert "create_tournament_squad" in result.messages[0].content.text


@pytest.mark.parametrize("raw", ["../berry/1", "pika?x=1", "", "a/b"])
def test_normalize_identifier_rejects_path_injection(raw: str) -> None:
    with pytest.raises(PokeAPIError):
        normalize_identifier(raw)


def test_normalize_identifier_accepts_slugs_and_ids() -> None:
    assert normalize_identifier("Mr Mime") == "mr-mime"
    assert normalize_identifier("25") == "25"
