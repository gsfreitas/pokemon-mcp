"""Cliente assíncrono da PokeAPI, isolado da camada MCP.

Separar o acesso HTTP das tools permite testar cada parte isoladamente e
reutilizar uma única conexão (connection pooling) durante toda a vida do
servidor, em vez de abrir um `httpx.AsyncClient` novo a cada chamada.
"""

from __future__ import annotations

import logging
import re
from collections import OrderedDict
from typing import Any

import httpx

from pokemon_mcp.config import Settings
from pokemon_mcp.models import Pokemon

logger = logging.getLogger(__name__)

# Nomes da PokeAPI são slugs (ex.: "mr-mime", "porygon-z") ou números da Pokédex.
_VALID_IDENTIFIER = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class PokeAPIError(Exception):
    """Falha esperada ao consultar a PokeAPI (mensagem segura para o usuário)."""


class PokemonNotFoundError(PokeAPIError):
    """O Pokémon pedido não existe."""


def normalize_identifier(name_or_id: str) -> str:
    """Normaliza e valida o identificador antes de montá-lo na URL.

    Evita que entradas como "../berry/1" ou "pikachu?x=y" alterem o path
    da requisição.
    """
    identifier = name_or_id.strip().lower().replace(" ", "-")
    if not _VALID_IDENTIFIER.fullmatch(identifier):
        raise PokeAPIError(
            f"Identificador inválido: {name_or_id!r}. Use o nome (ex.: 'pikachu', 'mr-mime') ou o número da Pokédex."
        )
    return identifier


class PokeAPIClient:
    def __init__(self, http: httpx.AsyncClient, *, cache_max_entries: int = 256) -> None:
        self._http = http
        self._cache: OrderedDict[str, Pokemon] = OrderedDict()
        self._cache_max_entries = cache_max_entries

    @classmethod
    def create_http_client(
        cls, settings: Settings, transport: httpx.AsyncBaseTransport | None = None
    ) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=settings.pokeapi_base_url,
            timeout=settings.http_timeout_seconds,
            headers={"User-Agent": "pokemon-mcp/0.1"},
            transport=transport,
        )

    async def get_pokemon(self, name_or_id: str) -> Pokemon:
        identifier = normalize_identifier(name_or_id)

        if (cached := self._cache.get(identifier)) is not None:
            self._cache.move_to_end(identifier)
            return cached

        data = await self._get_json(f"/pokemon/{identifier}", not_found_label=name_or_id)
        pokemon = Pokemon.from_api(data)
        self._store(identifier, pokemon)
        return pokemon

    async def _get_json(self, path: str, *, not_found_label: str) -> dict[str, Any]:
        try:
            response = await self._http.get(path)
        except httpx.TimeoutException as exc:
            logger.warning("Timeout ao consultar %s", path)
            raise PokeAPIError("A PokeAPI demorou demais para responder. Tente novamente.") from exc
        except httpx.HTTPError as exc:
            logger.warning("Erro de rede ao consultar %s: %s", path, exc)
            raise PokeAPIError("Não foi possível conectar à PokeAPI.") from exc

        if response.status_code == httpx.codes.NOT_FOUND:
            raise PokemonNotFoundError(f"Pokémon {not_found_label!r} não encontrado.")
        if response.is_error:
            logger.warning("PokeAPI respondeu %s para %s", response.status_code, path)
            raise PokeAPIError(f"A PokeAPI respondeu com erro HTTP {response.status_code}.")

        return response.json()

    def _store(self, identifier: str, pokemon: Pokemon) -> None:
        # Cacheia pelo nome canônico e pelo id, para "25" e "pikachu" baterem no mesmo item.
        for key in {identifier, pokemon.name, str(pokemon.id)}:
            self._cache[key] = pokemon
            self._cache.move_to_end(key)
        while len(self._cache) > self._cache_max_entries:
            self._cache.popitem(last=False)
