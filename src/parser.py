"""YAML parsing."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .model import Config, Family, Person, Relationship


def load_family_file(path: Path) -> Family:
    """Load a family YAML file into typed model objects."""
    with path.open("r", encoding="utf-8") as file:
        raw = yaml.safe_load(file) or {}

    people = _parse_people(raw.get("people", {}))
    relationships = tuple(_parse_relationships(raw.get("relationships", [])))
    config = _parse_config(raw.get("config", {}), people)
    return Family(people=people, relationships=relationships, config=config)


def _parse_people(raw_people: dict[str, Any]) -> dict[str, Person]:
    people: dict[str, Person] = {}
    for identifier, raw_person in raw_people.items():
        raw_person = raw_person or {}
        people[identifier] = Person(
            identifier=identifier,
            name=raw_person.get("name"),
            secondary_name=raw_person.get("secondaryName"),
        )
    return people


def _parse_relationships(raw_relationships: list[dict[str, Any]]) -> list[Relationship]:
    relationships: list[Relationship] = []
    for index, raw_relationship in enumerate(raw_relationships):
        raw_relationship = raw_relationship or {}
        relationships.append(
            Relationship(
                index=index,
                partners=tuple(raw_relationship.get("partners") or ()),
                children=tuple(raw_relationship.get("children") or ()),
                current=raw_relationship.get("current", True) is not False,
            )
        )
    return relationships


def _parse_config(raw_config: dict[str, Any], people: dict[str, Person]) -> Config:
    """Parse optional config, defaulting origin to the first person."""
    origin = raw_config.get("origin")
    if not origin:
        origin = next(iter(people), None)
    if origin is None:
        raise ValueError(
            "family YAML must define at least one person or a config.origin"
        )
    if origin not in people:
        raise ValueError(f"config.origin references unknown person {origin!r}")

    skip_visit = frozenset(raw_config.get("skipVisit") or ())
    if origin in skip_visit:
        raise ValueError("config.origin cannot also be listed in config.skipVisit")

    return Config(
        origin=origin,
        skip_expansion=frozenset(raw_config.get("skipExpansion") or ()),
        skip_visit=skip_visit,
    )
