"""Modelos de saída das tools.

Retornar modelos Pydantic (em vez de strings formatadas) faz o MCPServer
publicar um `outputSchema` e devolver `structuredContent`, que o cliente/LLM
consegue consumir sem precisar "parsear" texto livre.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PokemonStats(BaseModel):
    hp: int
    attack: int
    defense: int
    special_attack: int
    special_defense: int
    speed: int

    @property
    def total(self) -> int:
        return self.hp + self.attack + self.defense + self.special_attack + self.special_defense + self.speed


class Pokemon(BaseModel):
    id: int = Field(description="Número na Pokédex Nacional.")
    name: str
    height_m: float = Field(description="Altura em metros.")
    weight_kg: float = Field(description="Peso em quilogramas.")
    types: list[str]
    abilities: list[str]
    stats: PokemonStats
    base_stat_total: int = Field(description="Soma de todos os stats base.")

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Pokemon:
        """Converte o payload bruto da PokeAPI para o modelo de domínio."""
        raw_stats = {s["stat"]["name"].replace("-", "_"): s["base_stat"] for s in data["stats"]}
        stats = PokemonStats.model_validate(raw_stats)
        return cls(
            id=data["id"],
            name=data["name"],
            # A PokeAPI usa decímetros e hectogramas.
            height_m=data["height"] / 10,
            weight_kg=data["weight"] / 10,
            types=[t["type"]["name"] for t in sorted(data["types"], key=lambda t: t["slot"])],
            abilities=[a["ability"]["name"] for a in data["abilities"]],
            stats=stats,
            base_stat_total=stats.total,
        )


class SquadError(BaseModel):
    name: str
    error: str


class TournamentSquad(BaseModel):
    members: list[Pokemon]
    errors: list[SquadError] = Field(
        default_factory=list,
        description="Pokémon que não puderam ser adicionados e o motivo.",
    )
    type_coverage: list[str] = Field(description="Tipos distintos presentes no time.")
    average_base_stat_total: float | None
