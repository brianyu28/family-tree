"""Data structures used by the family tree generator."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Person:
    identifier: str
    name: str | None = None
    secondary_name: str | None = None


@dataclass(frozen=True)
class Relationship:
    index: int
    partners: tuple[str, ...] = ()
    children: tuple[str, ...] = ()
    current: bool = True

    @property
    def participants(self) -> tuple[str, ...]:
        return self.partners + self.children


@dataclass(frozen=True)
class Config:
    origin: str
    skip_expansion: frozenset[str] = frozenset()
    skip_visit: frozenset[str] = frozenset()


@dataclass(frozen=True)
class Family:
    people: dict[str, Person]
    relationships: tuple[Relationship, ...]
    config: Config


@dataclass(frozen=True)
class Tree:
    people: dict[str, Person]
    relationships: tuple[Relationship, ...]
    config: Config
    generations: dict[str, int]


@dataclass
class Layout:
    positions: dict[str, tuple[float, float]]
    generation_order: dict[int, list[str]]
    width: int
    height: int
    child_lanes: dict[int, int] = field(default_factory=dict)
    partner_lanes: dict[int, int] = field(default_factory=dict)
