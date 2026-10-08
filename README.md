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
├── http_app.py # app HTTP com autenticação Bearer e health check
├── models.py   # modelos Pydantic de saída (geram o outputSchema das tools)
├── pokeapi.py  # cliente HTTP da PokeAPI (validação, cache, erros)
└── server.py   # MCPServer: lifespan, tools, resource e prompt
tests/          # testes com HTTP mockado (sem rede)
infra/terraform # deploy na AWS (ECS Fargate + ALB interno)
Dockerfile      # imagem multi-stage, usuário não-root
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
uv run mcp dev src/pokemon_mcp/server.py
```

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

### Expor via HTTP para outros agentes

```bash
uv run pokemon-mcp --transport streamable-http --port 8000
```

O endpoint fica em `http://127.0.0.1:8000/mcp`. Qualquer cliente MCP com suporte a Streamable HTTP conecta por essa URL:

```bash
claude mcp add --transport http pokemon http://127.0.0.1:8000/mcp
```

Fora do loopback (`--host 0.0.0.0`) o servidor **exige** `MCP_AUTH_TOKENS` e recusa subir sem ele. Os agentes enviam
`Authorization: Bearer <token>`; `/health` fica público para o load balancer. O modo é *stateless*, então várias réplicas
podem rodar atrás de um load balancer.

## Deploy na AWS (agentes internos)

```
agentes (VPCs / VPN) ──HTTPS──▶ ALB interno ──▶ ECS Fargate (2+ tasks, multi-AZ) ──NAT──▶ PokeAPI
                                                   ▲
                                 Secrets Manager (MCP_AUTH_TOKENS)
```

O Terraform em [`infra/terraform`](infra/terraform) cria: ECR, ECS Fargate com autoscaling e rollback automático,
ALB **interno** (sem acesso pela internet), security groups restritos às redes dos agentes, token no Secrets Manager,
logs no CloudWatch e, opcionalmente, um registro DNS privado no Route 53.

Pré-requisitos: VPC com subnets privadas em 2+ AZs **com NAT** (a PokeAPI é externa), certificado ACM para o nome
interno e backend remoto do Terraform (o state guarda o token inicial; mantenha-o criptografado).

### 1. Infraestrutura

```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars   # preencha VPC, subnets, CIDRs, certificado e DNS
terraform init
terraform apply -target=aws_ecr_repository.this   # cria o repositório antes da primeira imagem
```

### 2. Imagem

```bash
REPO=$(terraform output -raw ecr_repository_url)
aws ecr get-login-password | docker login --username AWS --password-stdin "${REPO%%/*}"
docker build --platform linux/amd64 -t "$REPO:0.1.0" ../..
docker push "$REPO:0.1.0"
```

### 3. Serviço

```bash
terraform apply -var image_tag=0.1.0
terraform output mcp_url
```

Para uma nova versão: build/push com uma tag nova e `terraform apply -var image_tag=<tag>`.

### 4. Conectar os agentes

```bash
aws secretsmanager get-secret-value --secret-id pokemon-mcp/auth-tokens --query SecretString --output text
```

Claude Code:

```bash
claude mcp add --transport http pokemon https://pokemon-mcp.interno.empresa.com/mcp --header "Authorization: Bearer <token>"
```

Python (SDK `mcp`):

```python
import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

http = httpx2.AsyncClient(headers={"Authorization": f"Bearer {token}"})
async with Client(streamable_http_client(MCP_URL, http_client=http)) as client:
    result = await client.call_tool("get_pokemon_info", {"pokemon_name": "pikachu"})
```

Distribua o token aos times pelo próprio Secrets Manager (permissão IAM de leitura no secret), nunca por chat ou e-mail.

### Rotação do token (sem downtime)

1. Grave `token_antigo,token_novo` no secret e force um novo deploy:
   `aws ecs update-service --cluster pokemon-mcp --service pokemon-mcp --force-new-deployment`
2. Migre os agentes para o token novo.
3. Grave só `token_novo` no secret e force outro deploy.

### Variáveis de ambiente

| Variável                    | Padrão                      |
|-----------------------------|-----------------------------|
| `POKEAPI_BASE_URL`          | `https://pokeapi.co/api/v2` |
| `POKEAPI_TIMEOUT_SECONDS`   | `10`                        |
| `POKEAPI_CACHE_MAX_ENTRIES` | `256`                       |
| `LOG_LEVEL`                 | `INFO`                      |
| `MCP_TRANSPORT`             | `stdio`                     |
| `MCP_HOST`                  | `127.0.0.1`                 |
| `MCP_PORT`                  | `8000`                      |
| `MCP_AUTH_TOKENS`           | vazio (obrigatório fora do loopback) |

## Desenvolvimento

```bash
uv run pytest
```

```bash
uv run ruff check . && uv run ruff format --check .
```
