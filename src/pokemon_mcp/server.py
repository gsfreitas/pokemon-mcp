"""Servidor MCP de Pokémon.

Boas práticas aplicadas:
- `lifespan` gerencia recursos compartilhados (um único `httpx.AsyncClient`);
- tools com nome, título, descrição e `ToolAnnotations` (somente leitura etc.);
- parâmetros validados com `Annotated` + `Field` (viram JSON Schema para o LLM);
- saída estruturada via modelos Pydantic (`outputSchema` + `structuredContent`);
- falhas esperadas viram `ToolError` (mensagem clara para o modelo), e
  falhas inesperadas não vazam detalhes internos;
- logs sempre em stderr: no transporte stdio, stdout é o canal do protocolo.
"""

import argparse
import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from typing import Annotated, Literal, cast

import httpx
import uvicorn
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ResourceError, ResourceNotFoundError, ToolError
from mcp.types import ToolAnnotations
from pydantic import Field
from starlette.requests import Request
from starlette.responses import JSONResponse

from pokemon_mcp.config import Settings
from pokemon_mcp.http_app import create_http_app
from pokemon_mcp.models import Pokemon, SquadError, TournamentSquad
from pokemon_mcp.pokeapi import PokeAPIClient, PokeAPIError, PokemonNotFoundError

logger = logging.getLogger(__name__)

MAX_SQUAD_SIZE = 6

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

# Todas as tools só consultam uma API pública externa: não alteram estado,
# podem ser repetidas com segurança e falam com o "mundo aberto".
READ_ONLY_EXTERNAL = ToolAnnotations(
    read_only_hint=True,
    destructive_hint=False,
    idempotent_hint=True,
    open_world_hint=True,
)

PokemonName = Annotated[
    str,
    Field(
        min_length=1,
        max_length=50,
        description="Nome (ex.: 'pikachu', 'mr-mime') ou número da Pokédex (ex.: '25').",
    ),
]


@dataclass(slots=True)
class AppContext:
    pokeapi: PokeAPIClient


def build_server(
    settings: Settings | None = None,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> MCPServer[AppContext]:
    """Monta o servidor. `transport` permite injetar um mock HTTP nos testes."""
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(_: MCPServer[AppContext]) -> AsyncIterator[AppContext]:
        async with PokeAPIClient.create_http_client(settings, transport) as http:
            logger.info("Servidor iniciado (PokeAPI em %s)", settings.pokeapi_base_url)
            yield AppContext(pokeapi=PokeAPIClient(http, cache_max_entries=settings.cache_max_entries))
        logger.info("Servidor finalizado")

    mcp: MCPServer[AppContext] = MCPServer(
        name="pokemon",
        title="Pokémon",
        version="0.1.0",
        instructions=(
            "Consulta dados de Pokémon na PokeAPI. Use `get_pokemon_info` para um Pokémon "
            f"e `create_tournament_squad` para montar e avaliar um time de até {MAX_SQUAD_SIZE}."
        ),
        lifespan=lifespan,
        log_level=cast(LogLevel, settings.log_level),
    )

    def pokeapi_from(ctx: Context) -> PokeAPIClient:
        return cast(AppContext, ctx.request_context.lifespan_context).pokeapi

    # ------------------------------------------------------------------ tools

    @mcp.tool(
        title="Informações de um Pokémon",
        annotations=READ_ONLY_EXTERNAL,
    )
    async def get_pokemon_info(pokemon_name: PokemonName, ctx: Context) -> Pokemon:
        """Busca tipos, habilidades, altura, peso e stats base de um Pokémon."""
        try:
            return await pokeapi_from(ctx).get_pokemon(pokemon_name)
        except PokeAPIError as exc:
            raise ToolError(str(exc)) from exc

    @mcp.tool(
        title="Montar time de torneio",
        annotations=READ_ONLY_EXTERNAL,
    )
    async def create_tournament_squad(
        pokemon_names: Annotated[
            list[PokemonName],
            Field(
                min_length=1,
                max_length=MAX_SQUAD_SIZE,
                description=f"Lista de 1 a {MAX_SQUAD_SIZE} Pokémon (nomes ou números), sem repetição.",
            ),
        ],
        ctx: Context,
    ) -> TournamentSquad:
        """Monta um time de torneio, resumindo cobertura de tipos e média de stats.

        Pokémon inválidos ou repetidos são listados em `errors`, sem impedir o
        restante do time de ser montado.
        """
        pokeapi = pokeapi_from(ctx)

        # Busca em paralelo: o tempo total passa a ser o da requisição mais lenta.
        results = await asyncio.gather(
            *(pokeapi.get_pokemon(name) for name in pokemon_names),
            return_exceptions=True,
        )

        members: list[Pokemon] = []
        errors: list[SquadError] = []
        seen_ids: set[int] = set()
        for name, result in zip(pokemon_names, results, strict=True):
            if isinstance(result, PokeAPIError):
                errors.append(SquadError(name=name, error=str(result)))
            elif isinstance(result, BaseException):
                raise result  # erro inesperado: deixa o SDK tratar sem vazar detalhes
            elif result.id in seen_ids:
                errors.append(SquadError(name=name, error=f"{result.name!r} já está no time."))
            else:
                seen_ids.add(result.id)
                members.append(result)

        if not members:
            details = "; ".join(f"{e.name}: {e.error}" for e in errors)
            raise ToolError(f"Nenhum Pokémon válido para montar o time. {details}")

        return TournamentSquad(
            members=members,
            errors=errors,
            type_coverage=sorted({t for p in members for t in p.types}),
            average_base_stat_total=round(sum(p.base_stat_total for p in members) / len(members), 1),
        )

    # -------------------------------------------------------------- resources

    @mcp.resource(
        "pokemon://{pokemon_name}",
        title="Ficha de Pokémon",
        description="Dados de um Pokémon em JSON.",
        mime_type="application/json",
    )
    async def pokemon_resource(pokemon_name: str, ctx: Context) -> str:
        try:
            pokemon = await pokeapi_from(ctx).get_pokemon(pokemon_name)
        except PokemonNotFoundError as exc:
            raise ResourceNotFoundError(str(exc)) from exc
        except PokeAPIError as exc:
            raise ResourceError(str(exc)) from exc
        return pokemon.model_dump_json(indent=2)

    # ---------------------------------------------------------------- prompts

    @mcp.prompt(title="Analisar time de torneio")
    def analyze_squad(pokemon_names: str) -> str:
        """Pede ao modelo uma análise estratégica de um time (nomes separados por vírgula)."""
        return (
            f"Use a tool `create_tournament_squad` com estes Pokémon: {pokemon_names}.\n"
            "Depois, analise o time: pontos fortes, fraquezas de tipo não cobertas, "
            "papéis (atacante, tanque, suporte) e sugira até duas substituições."
        )

    # ----------------------------------------------------------- HTTP extras

    @mcp.custom_route("/health", methods=["GET"], include_in_schema=False)
    async def health(_: Request) -> JSONResponse:
        """Health check do load balancer (público, não toca na PokeAPI)."""
        return JSONResponse({"status": "ok"})

    return mcp


# Instância de módulo para `mcp dev src/pokemon_mcp/server.py` e `mcp run`.
mcp = build_server()


def main(argv: list[str] | None = None) -> None:
    settings = Settings.from_env()
    parser = argparse.ArgumentParser(prog="pokemon-mcp", description="Servidor MCP de Pokémon.")
    parser.add_argument(
        "--transport",
        choices=["stdio", "streamable-http"],
        default=settings.transport,
        help="stdio para clientes locais; streamable-http para expor na rede (padrão: %(default)s).",
    )
    parser.add_argument("--host", default=settings.host, help="Interface HTTP (padrão: %(default)s).")
    parser.add_argument("--port", type=int, default=settings.port, help="Porta HTTP (padrão: %(default)s).")
    args = parser.parse_args(argv)

    if args.transport == "stdio":
        mcp.run(transport="stdio")
        return

    settings = replace(settings, host=args.host, port=args.port)
    app = create_http_app(mcp, settings)
    # proxy_headers: confia no X-Forwarded-* do ALB para logar o IP real do agente.
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
        proxy_headers=True,
        forwarded_allow_ips="*",
    )


if __name__ == "__main__":
    main()
