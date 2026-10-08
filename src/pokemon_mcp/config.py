"""Configuração do servidor, lida de variáveis de ambiente.

Nada de valores "mágicos" espalhados pelo código: tudo que pode mudar entre
ambientes (URL da API, timeout, tamanho do cache) fica aqui.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    return float(raw) if raw else default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return int(raw) if raw else default


def _env_log_level(name: str, default: str) -> str:
    level = os.getenv(name, default).upper()
    if level not in _LOG_LEVELS:
        raise ValueError(f"{name} inválido: {level!r}. Use um de {sorted(_LOG_LEVELS)}.")
    return level


_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


@dataclass(frozen=True)
class Settings:
    pokeapi_base_url: str = "https://pokeapi.co/api/v2"
    http_timeout_seconds: float = 10.0
    cache_max_entries: int = 256
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            pokeapi_base_url=os.getenv("POKEAPI_BASE_URL", cls.pokeapi_base_url).rstrip("/"),
            http_timeout_seconds=_env_float("POKEAPI_TIMEOUT_SECONDS", cls.http_timeout_seconds),
            cache_max_entries=_env_int("POKEAPI_CACHE_MAX_ENTRIES", cls.cache_max_entries),
            log_level=_env_log_level("LOG_LEVEL", cls.log_level),
        )
