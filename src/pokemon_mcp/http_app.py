"""App ASGI para servir o MCP via Streamable HTTP com autenticação Bearer.

O SDK monta o app Starlette do protocolo; aqui só adicionamos uma camada que
exige `Authorization: Bearer <token>` em tudo, exceto no health check usado
pelo load balancer.
"""

from __future__ import annotations

import hmac
import json
import logging
from collections.abc import Iterable

from mcp.server.mcpserver import MCPServer
from starlette.types import ASGIApp, Receive, Scope, Send

from pokemon_mcp.config import Settings

logger = logging.getLogger(__name__)

HEALTH_PATH = "/health"
PUBLIC_PATHS = frozenset({HEALTH_PATH})
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


class BearerAuthMiddleware:
    """Rejeita com 401 requisições HTTP sem um token válido.

    Aceita mais de um token para permitir rotação sem downtime: publica-se o
    token novo, os agentes migram, e só então o antigo é removido.
    """

    def __init__(self, app: ASGIApp, tokens: Iterable[str]) -> None:
        self.app = app
        self._tokens = [t.encode() for t in tokens if t]
        if not self._tokens:
            raise ValueError("BearerAuthMiddleware precisa de pelo menos um token.")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        # Eventos de lifespan e paths públicos passam direto.
        if scope["type"] != "http" or scope["path"] in PUBLIC_PATHS:
            await self.app(scope, receive, send)
            return

        if self._is_authorized(scope):
            await self.app(scope, receive, send)
            return

        client = scope.get("client") or ("?", 0)
        logger.warning("Requisição não autorizada de %s para %s", client[0], scope["path"])
        body = json.dumps({"error": "unauthorized"}).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                    (b"www-authenticate", b'Bearer realm="pokemon-mcp"'),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})

    def _is_authorized(self, scope: Scope) -> bool:
        header = dict(scope["headers"]).get(b"authorization", b"")
        scheme, _, token = header.partition(b" ")
        if scheme.lower() != b"bearer" or not token:
            return False
        # compare_digest em todos os tokens evita vazar informação por tempo de resposta.
        return any([hmac.compare_digest(token.strip(), valid) for valid in self._tokens])


def create_http_app(mcp: MCPServer, settings: Settings) -> ASGIApp:
    """Monta o app HTTP pronto para produção.

    Falha na subida se o servidor for exposto fora do loopback sem token:
    é melhor não subir do que subir aberto por engano.
    """
    app = mcp.streamable_http_app(
        # Sem estado de sessão: qualquer réplica atende qualquer requisição,
        # o que permite várias tasks atrás do ALB sem sticky sessions.
        stateless_http=True,
        host=settings.host,
    )

    if settings.auth_tokens:
        return BearerAuthMiddleware(app, settings.auth_tokens)
    if settings.host in _LOOPBACK_HOSTS:
        logger.warning("Autenticação desabilitada (MCP_AUTH_TOKENS vazio); aceito apenas por escutar em loopback.")
        return app
    raise RuntimeError(f"MCP_AUTH_TOKENS é obrigatório ao escutar em {settings.host!r} (fora do loopback).")
