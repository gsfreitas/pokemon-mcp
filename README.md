# pokemon-mcp

Servidor MCP que expõe dados da [PokeAPI](https://pokeapi.co/).

| Tipo     | Nome                       | O que faz                                                         |
|----------|----------------------------|-------------------------------------------------------------------|
| Tool     | `get_pokemon_info`         | Tipos, habilidades, altura, peso e stats base de um Pokémon        |
| Tool     | `create_tournament_squad`  | Monta um time (1–6), com cobertura de tipos e média de stats       |
| Resource | `pokemon://{pokemon_name}` | Ficha do Pokémon em JSON                                           |
| Prompt   | `analyze_squad`            | Pede ao modelo uma análise estratégica do time                     |

## Estrutura

```
src/pokemon_mcp/
├── config.py   # configuração via variáveis de ambiente
├── models.py   # modelos Pydantic de saída (geram o outputSchema das tools)
├── pokeapi.py  # cliente HTTP da PokeAPI (validação, cache, erros)
└── server.py   # MCPServer: lifespan, tools, resource e prompt
tests/          # testes com HTTP mockado (sem rede)
```

## Boas práticas aplicadas

- **Lifespan**: um único `httpx.AsyncClient` (pool de conexões) criado na subida e fechado no desligamento.
- **Tools bem descritas**: `title`, docstring e `ToolAnnotations` (`read_only_hint`, `idempotent_hint`, `open_world_hint`).
- **Entrada validada**: `Annotated` + `Field` (tamanho, limites e descrição viram JSON Schema para o LLM) e
  normalização do nome, para impedir que a entrada altere o path da URL.
- **Saída estruturada**: modelos Pydantic geram `outputSchema` e `structuredContent`.
- **Erros**: falhas esperadas viram `ToolError`/`ResourceError` com mensagem clara; erros inesperados não vazam detalhes.
- **Falha parcial**: no time, Pokémon inválidos ou repetidos vão para `errors` sem derrubar o resto.
- **Performance**: buscas em paralelo (`asyncio.gather`) e cache LRU em memória (pedido pela política de uso da PokeAPI).
- **Logs em stderr**: no transporte stdio, stdout é reservado ao protocolo.
- **Testável**: `build_server(transport=...)` permite injetar um `httpx.MockTransport`.

## Uso

```bash
uv sync
```

```bash
uv run pokemon-mcp
```

Inspecionar com o MCP Inspector:

```bash
npx -y -p @modelcontextprotocol/inspector mcp-inspector uv run pokemon-mcp
```

> `uv run mcp dev` não funciona com o Inspector 2.x: o pacote passou a expor dois
> binários (`mcp-inspector` e `mcpdo`) e o `npx` não consegue escolher qual executar
> ("could not determine executable to run"). Por isso o binário é indicado explicitamente.

### Claude Desktop / Claude Code

```json
{
  "mcpServers": {
    "pokemon": {
      "command": "uv",
      "args": ["--directory", "C:/caminho/para/pokemon", "run", "pokemon-mcp"]
    }
  }
}
```

### Variáveis de ambiente

| Variável                    | Padrão                      |
|-----------------------------|-----------------------------|
| `POKEAPI_BASE_URL`          | `https://pokeapi.co/api/v2` |
| `POKEAPI_TIMEOUT_SECONDS`   | `10`                        |
| `POKEAPI_CACHE_MAX_ENTRIES` | `256`                       |
| `LOG_LEVEL`                 | `INFO`                      |

## Desenvolvimento

```bash
uv run pytest
```

```bash
uv run ruff check . && uv run ruff format --check .
```
