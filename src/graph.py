"""Graph expansion and generation assignment."""

from __future__ import annotations

from collections import defaultdict, deque

from .model import Family, Relationship, Tree


def build_tree(family: Family) -> Tree:
    """Expand the connected family subset from config.origin."""
    relationship_index = _relationships_by_person(family.relationships)
    included_people = _expand_people(family, relationship_index)
    included_relationships = tuple(
        relationship
        for relationship in (
            _relationship_for_included_people(relationship, included_people)
            for relationship in family.relationships
        )
        if relationship is not None
    )
    generations = _assign_generations(family.config.origin, included_relationships)
    people = {
        person_id: family.people[person_id]
        for person_id in included_people
        if person_id in generations
    }
    return Tree(
        people=people,
        relationships=included_relationships,
        config=family.config,
        generations=generations,
    )


def _relationships_by_person(
    relationships: tuple[Relationship, ...],
) -> dict[str, list[Relationship]]:
    indexed: dict[str, list[Relationship]] = defaultdict(list)
    for relationship in relationships:
        for person_id in relationship.participants:
            indexed[person_id].append(relationship)
    return indexed


def _expand_people(
    family: Family,
    relationship_index: dict[str, list[Relationship]],
) -> set[str]:
    """Walk relationships outward until skipExpansion, skipVisit, or graph exhaustion."""
    if family.config.origin in family.config.skip_visit:
        raise ValueError("config.origin cannot also be listed in config.skipVisit")

    included = {family.config.origin}
    queue = deque([family.config.origin])

    while queue:
        person_id = queue.popleft()
        if person_id in family.config.skip_expansion:
            continue
        for relationship in relationship_index.get(person_id, ()):
            for related_person_id in relationship.participants:
                if related_person_id not in family.people:
                    raise ValueError(
                        f"relationship references unknown person {related_person_id!r}"
                    )
                if related_person_id in family.config.skip_visit:
                    continue
                if related_person_id not in included:
                    included.add(related_person_id)
                    queue.append(related_person_id)
    return included


def _relationship_for_included_people(
    relationship: Relationship,
    included_people: set[str],
) -> Relationship | None:
    partners = tuple(
        person_id for person_id in relationship.partners if person_id in included_people
    )
    children = tuple(
        person_id for person_id in relationship.children if person_id in included_people
    )
    if len(partners) + len(children) < 2:
        return None
    return Relationship(
        index=relationship.index,
        partners=partners,
        children=children,
        current=relationship.current,
    )


def _assign_generations(
    origin: str,
    relationships: tuple[Relationship, ...],
) -> dict[str, int]:
    """Assign generation numbers relative to the origin person."""
    relationship_index = _relationships_by_person(relationships)
    generations = {origin: 0}
    queue = deque([origin])

    while queue:
        person_id = queue.popleft()
        generation = generations[person_id]
        for relationship in relationship_index.get(person_id, ()):
            for related_person_id, related_generation in _related_generations(
                relationship,
                person_id,
                generation,
            ):
                if related_person_id in generations:
                    continue
                generations[related_person_id] = related_generation
                queue.append(related_person_id)

    return generations


def _related_generations(
    relationship: Relationship,
    person_id: str,
    generation: int,
) -> list[tuple[str, int]]:
    related: list[tuple[str, int]] = []
    if person_id in relationship.partners:
        related.extend((partner_id, generation) for partner_id in relationship.partners)
        related.extend((child_id, generation + 1) for child_id in relationship.children)
    elif person_id in relationship.children:
        related.extend(
            (partner_id, generation - 1) for partner_id in relationship.partners
        )
        related.extend((child_id, generation) for child_id in relationship.children)
    return [
        (related_person_id, related_generation)
        for related_person_id, related_generation in related
        if related_person_id != person_id
    ]
