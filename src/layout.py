"""Layered family tree layout."""

from __future__ import annotations

from collections import defaultdict
from statistics import mean
from typing import Callable

from .constants import (
    CHILD_BRANCH_GAP,
    CHILD_BRANCH_LANE_GAP,
    CHILD_BRANCH_LANE_PADDING,
    CHILD_CENTERING_WEIGHT,
    GENERATION_GAP,
    LAYOUT_ITERATIONS,
    MARGIN_X,
    MARGIN_Y,
    NODE_GAP,
    NODE_HEIGHT,
    NODE_WIDTH,
    PARENT_CENTERING_WEIGHT,
    PARTNER_GAP,
    ROUTED_PARTNER_LANE_GAP,
    ROUTED_PARTNER_OFFSET,
)
from .model import Layout, Relationship, Tree


def layout_tree(tree: Tree) -> Layout:
    """Compute node positions and routing lanes for a renderable tree."""
    generation_order = _initial_generation_order(tree)
    best_generation_order = generation_order
    best_score = float("inf")
    for _ in range(10):
        x_positions = _optimize_x_positions(tree, generation_order)
        for _ in range(2):
            x_positions = _align_parents_to_children(
                tree, generation_order, x_positions
            )
            x_positions = _align_children_to_parents(
                tree, generation_order, x_positions
            )
        score = _layout_score(tree, x_positions)
        if score < best_score:
            best_score = score
            best_generation_order = generation_order
        generation_order = _improve_generation_order(
            tree, generation_order, x_positions
        )
        generation_order = _apply_partner_parent_locality(tree, generation_order)

    generation_order = _apply_partner_parent_locality(tree, best_generation_order)
    x_positions = _optimize_x_positions(tree, generation_order)
    for _ in range(4):
        x_positions = _align_parents_to_children(tree, generation_order, x_positions)
        x_positions = _align_children_to_parents(tree, generation_order, x_positions)
    for _ in range(3):
        x_positions = _snap_single_children_to_parent_centers(
            tree, generation_order, x_positions
        )
    positions = _compose_positions(tree, x_positions)
    child_lanes = _assign_child_lanes(tree, positions)
    partner_lanes = _assign_partner_lanes(tree, positions, generation_order)

    min_x = min(x for x, _ in positions.values()) - NODE_WIDTH / 2
    max_x = max(x for x, _ in positions.values()) + NODE_WIDTH / 2
    min_y = min(y for _, y in positions.values())
    max_y = max(y for _, y in positions.values()) + NODE_HEIGHT

    shift_x = MARGIN_X - min_x
    shift_y = MARGIN_Y - min_y
    shifted_positions = {
        person_id: (x + shift_x, y + shift_y) for person_id, (x, y) in positions.items()
    }

    width = int(max_x - min_x + 2 * MARGIN_X)
    height = int(max_y - min_y + 2 * MARGIN_Y)
    return Layout(
        positions=shifted_positions,
        generation_order=generation_order,
        width=width,
        height=height,
        child_lanes=child_lanes,
        partner_lanes=partner_lanes,
    )


def _initial_generation_order(tree: Tree) -> dict[int, list[str]]:
    """Build the first stable ordering from YAML relationship order."""
    by_generation: dict[int, list[str]] = defaultdict(list)
    for relationship in tree.relationships:
        for person_id in relationship.participants:
            if (
                person_id in tree.generations
                and person_id not in by_generation[tree.generations[person_id]]
            ):
                by_generation[tree.generations[person_id]].append(person_id)
    for person_id, generation in tree.generations.items():
        if person_id not in by_generation[generation]:
            by_generation[generation].append(person_id)
    return {
        generation: _partner_sorted_nodes(tree, generation, nodes)
        for generation, nodes in sorted(by_generation.items())
    }


def _improve_generation_order(
    tree: Tree,
    generation_order: dict[int, list[str]],
    x_positions: dict[str, float],
) -> dict[int, list[str]]:
    """Reorder each generation by nearby parent/child x-centers."""
    improved = {}
    for generation, nodes in sorted(generation_order.items()):
        blocks = _generation_blocks(tree, generation, nodes)
        block_edges = _block_order_edges(tree, generation, blocks)
        weights = []
        for block_index, block in enumerate(blocks):
            values = []
            for person_id in block:
                values.extend(
                    _vertical_neighbor_positions(
                        tree, person_id, generation, x_positions
                    )
                )
            weights.append(_block_weight(values, block_index))
        ordered_blocks = _topological_sort_blocks(blocks, block_edges, weights)
        improved[generation] = [
            person_id for block in ordered_blocks for person_id in block
        ]
    return improved


def _partner_sorted_nodes(tree: Tree, generation: int, nodes: list[str]) -> list[str]:
    blocks = _generation_blocks(tree, generation, nodes)
    return [person_id for block in blocks for person_id in block]


def _generation_blocks(
    tree: Tree, generation: int, nodes: list[str]
) -> list[list[str]]:
    """Return same-generation blocks that must move together.

    Partner pairs are always atomic. Sibling order is handled later as an
    ordering constraint so spouses can still sit next to the sibling they
    married into.
    """
    node_set = set(nodes)
    rank = {person_id: index for index, person_id in enumerate(nodes)}
    partner_adjacency: dict[str, set[str]] = {person_id: set() for person_id in nodes}
    partner_edges: list[tuple[str, str]] = []
    for relationship in tree.relationships:
        partners = [
            person_id for person_id in relationship.partners if person_id in node_set
        ]
        if len(partners) == 2 and all(
            tree.generations.get(person_id) == generation for person_id in partners
        ):
            left, right = partners
            partner_adjacency[left].add(right)
            partner_adjacency[right].add(left)
            partner_edges.append((left, right))
    components = _connected_person_components(nodes, partner_adjacency)
    return [
        _topological_sort_people(component, partner_edges, rank)
        for component in components
    ]


def _connected_person_components(
    nodes: list[str],
    adjacency: dict[str, set[str]],
) -> list[list[str]]:
    visited: set[str] = set()
    blocks: list[list[str]] = []
    for person_id in nodes:
        if person_id in visited:
            continue
        stack = [person_id]
        component = []
        visited.add(person_id)
        while stack:
            current = stack.pop()
            component.append(current)
            for neighbor in adjacency[current]:
                if neighbor not in visited:
                    visited.add(neighbor)
                    stack.append(neighbor)
        blocks.append(component)
    return blocks


def _topological_sort_people(
    people: list[str],
    edges: list[tuple[str, str]],
    rank: dict[str, int],
) -> list[str]:
    person_set = set(people)
    incoming = {person_id: 0 for person_id in people}
    outgoing = {person_id: [] for person_id in people}
    for left, right in edges:
        if left in person_set and right in person_set:
            incoming[right] += 1
            outgoing[left].append(right)

    ready = sorted(
        (person_id for person_id in people if incoming[person_id] == 0), key=rank.get
    )
    ordered = []
    while ready:
        person_id = ready.pop(0)
        ordered.append(person_id)
        for neighbor in outgoing[person_id]:
            incoming[neighbor] -= 1
            if incoming[neighbor] == 0:
                ready.append(neighbor)
                ready.sort(key=rank.get)
    if len(ordered) != len(people):
        return sorted(people, key=rank.get)
    return ordered


def _block_order_edges(
    tree: Tree,
    generation: int,
    blocks: list[list[str]],
) -> list[tuple[int, int]]:
    """Build ordering constraints between movable blocks."""
    block_by_person = {
        person_id: block_index
        for block_index, block in enumerate(blocks)
        for person_id in block
    }
    edges = set()
    for relationship in tree.relationships:
        children = [
            child_id
            for child_id in relationship.children
            if tree.generations.get(child_id) == generation
            and child_id in block_by_person
        ]
        for left, right in zip(children, children[1:]):
            left_block = block_by_person[left]
            right_block = block_by_person[right]
            if left_block != right_block:
                edges.add((left_block, right_block))
    edges.update(_sibling_family_order_edges(tree, generation, block_by_person))
    return sorted(edges)


def _sibling_family_order_edges(
    tree: Tree,
    generation: int,
    block_by_person: dict[str, int],
) -> set[tuple[int, int]]:
    """Preserve sibling order for the child-family branches below them."""
    edges = set()
    for sibling_relationship in tree.relationships:
        sibling_parents = [
            child_id
            for child_id in sibling_relationship.children
            if tree.generations.get(child_id) == generation - 1
        ]
        sibling_child_blocks: list[list[int]] = []
        for sibling_parent_id in sibling_parents:
            child_blocks = []
            for child_relationship in tree.relationships:
                if sibling_parent_id not in child_relationship.partners:
                    continue
                for child_id in child_relationship.children:
                    if (
                        tree.generations.get(child_id) == generation
                        and child_id in block_by_person
                    ):
                        child_blocks.append(block_by_person[child_id])
            if child_blocks:
                sibling_child_blocks.append(sorted(set(child_blocks)))

        for left_blocks, right_blocks in zip(
            sibling_child_blocks, sibling_child_blocks[1:]
        ):
            for left_block in left_blocks:
                for right_block in right_blocks:
                    if left_block != right_block:
                        edges.add((left_block, right_block))
    return edges


def _topological_sort_blocks(
    blocks: list[list[str]],
    edges: list[tuple[int, int]],
    weights: list[float],
) -> list[list[str]]:
    incoming = [0 for _ in blocks]
    outgoing = [[] for _ in blocks]
    for left, right in edges:
        incoming[right] += 1
        outgoing[left].append(right)

    ready = sorted(
        (index for index, count in enumerate(incoming) if count == 0),
        key=lambda index: (weights[index], index),
    )
    ordered_indices = []
    while ready:
        index = ready.pop(0)
        ordered_indices.append(index)
        for neighbor in outgoing[index]:
            incoming[neighbor] -= 1
            if incoming[neighbor] == 0:
                ready.append(neighbor)
                ready.sort(key=lambda item: (weights[item], item))
    if len(ordered_indices) != len(blocks):
        return blocks
    return [blocks[index] for index in ordered_indices]


def _vertical_neighbor_positions(
    tree: Tree,
    person_id: str,
    generation: int,
    x_positions: dict[str, float],
) -> list[float]:
    """Return x-centers of directly related people in adjacent generations."""
    values = []
    for relationship in tree.relationships:
        partners = [
            partner_id
            for partner_id in relationship.partners
            if partner_id in x_positions
        ]
        children = [
            child_id for child_id in relationship.children if child_id in x_positions
        ]
        if person_id in relationship.children and partners:
            values.append(
                mean(x_positions[partner_id] for partner_id in partners[:2] or partners)
            )
        if person_id in relationship.partners and children:
            same_generation_partners = [
                partner_id
                for partner_id in partners
                if tree.generations.get(partner_id) == generation
            ]
            if same_generation_partners:
                values.append(mean(x_positions[child_id] for child_id in children))
    return values


def _block_weight(values: list[float], fallback: int) -> float:
    if not values:
        return float(fallback)
    return min(values) + mean(values) * 0.001


def _apply_partner_parent_locality(
    tree: Tree,
    generation_order: dict[int, list[str]],
) -> dict[int, list[str]]:
    """Move parent pairs to mirror the left-to-right order of their children.

    If A is left of B, for example, A's parents should sit to
    the left of B's parents when both parent pairs are visible.
    """
    adjusted = {
        generation: list(nodes) for generation, nodes in generation_order.items()
    }
    parent_relationships = _parent_relationships_by_child(tree)

    for relationship in tree.relationships:
        if len(relationship.partners) < 2:
            continue
        for left_partner, right_partner in zip(
            relationship.partners, relationship.partners[1:]
        ):
            if (
                left_partner not in tree.generations
                or right_partner not in tree.generations
            ):
                continue
            if tree.generations[left_partner] != tree.generations[right_partner]:
                continue

            parent_generation = tree.generations[left_partner] - 1
            if parent_generation not in adjusted:
                continue
            left_parents = parent_relationships.get(left_partner)
            right_parents = parent_relationships.get(right_partner)
            if not left_parents or not right_parents:
                continue

            adjusted[parent_generation] = _move_parent_block_before(
                tree,
                parent_generation,
                adjusted[parent_generation],
                left_parents.partners,
                right_parents.partners,
            )
    return adjusted


def _parent_relationships_by_child(tree: Tree) -> dict[str, Relationship]:
    parent_relationships = {}
    for relationship in tree.relationships:
        if not relationship.partners:
            continue
        for child_id in relationship.children:
            parent_relationships[child_id] = relationship
    return parent_relationships


def _move_parent_block_before(
    tree: Tree,
    generation: int,
    nodes: list[str],
    moving_people: tuple[str, ...],
    target_people: tuple[str, ...],
) -> list[str]:
    blocks = _generation_blocks(tree, generation, nodes)
    moving_index = _block_index_containing(blocks, moving_people)
    target_index = _block_index_containing(blocks, target_people)
    if moving_index is None or target_index is None or moving_index == target_index:
        return nodes

    moving_block = blocks.pop(moving_index)
    if moving_index < target_index:
        target_index -= 1
    blocks.insert(target_index, moving_block)
    return [person_id for block in blocks for person_id in block]


def _block_index_containing(
    blocks: list[list[str]],
    people: tuple[str, ...],
) -> int | None:
    people_set = set(people)
    for index, block in enumerate(blocks):
        if people_set.intersection(block):
            return index
    return None


def _layout_score(tree: Tree, x_positions: dict[str, float]) -> float:
    """Score an ordering by relationship span and sibling compactness."""
    score = 0.0
    for relationship in tree.relationships:
        partners = [
            person_id for person_id in relationship.partners if person_id in x_positions
        ]
        children = [
            person_id for person_id in relationship.children if person_id in x_positions
        ]
        if partners and children:
            parent_center = mean(
                x_positions[person_id] for person_id in partners[:2] or partners
            )
            child_center = mean(x_positions[person_id] for person_id in children)
            score += abs(parent_center - child_center) * 3.0
            score += (
                sum(abs(x_positions[child_id] - parent_center) for child_id in children)
                * 0.15
            )
            for left_id, right_id in zip(children, children[1:]):
                score += abs(x_positions[right_id] - x_positions[left_id]) * 1.5
        if len(partners) >= 2:
            score += abs(x_positions[partners[0]] - x_positions[partners[1]]) * 0.1
    return score


def _optimize_x_positions(
    tree: Tree,
    generation_order: dict[int, list[str]],
) -> dict[str, float]:
    """Place ordered blocks while pulling related families toward each other."""
    generation_blocks = {
        generation: _generation_blocks(tree, generation, nodes)
        for generation, nodes in generation_order.items()
    }
    block_offsets = {
        generation: [_block_offsets(tree, block) for block in blocks]
        for generation, blocks in generation_blocks.items()
    }

    x_positions: dict[str, float] = {}
    block_bases: dict[tuple[int, int], float] = {}
    for generation, blocks in generation_blocks.items():
        cursor = 0.0
        previous_block = None
        for block_index, block in enumerate(blocks):
            offsets = block_offsets[generation][block_index]
            if previous_block is not None:
                cursor += _between_block_gap(tree, previous_block, block)
            block_bases[(generation, block_index)] = cursor
            for person_id, offset in zip(block, offsets):
                x_positions[person_id] = cursor + offset
            previous_block = block

    for _ in range(LAYOUT_ITERATIONS):
        desired: dict[str, list[tuple[float, float]]] = defaultdict(list)
        for relationship in tree.relationships:
            _add_relationship_desires(tree, relationship, x_positions, desired)
        for generation, blocks in generation_blocks.items():
            desired_bases = []
            for block_index, block in enumerate(blocks):
                offsets = block_offsets[generation][block_index]
                base_values = []
                for person_id, offset in zip(block, offsets):
                    for desired_x, weight in desired[person_id]:
                        base_values.append((desired_x - offset, weight))
                fallback = block_bases[(generation, block_index)]
                desired_bases.append(_weighted_average(base_values, fallback))

            gaps = [
                _minimum_block_base_gap(tree, left, right, left_offsets, right_offsets)
                for left, right, left_offsets, right_offsets in zip(
                    blocks,
                    blocks[1:],
                    block_offsets[generation],
                    block_offsets[generation][1:],
                )
            ]
            placed_bases = _place_ordered(desired_bases, gaps)
            for block_index, (block, base) in enumerate(zip(blocks, placed_bases)):
                block_bases[(generation, block_index)] = base
                offsets = block_offsets[generation][block_index]
                for person_id, offset in zip(block, offsets):
                    x_positions[person_id] = base + offset
    return x_positions


def _block_offsets(tree: Tree, block: list[str]) -> list[float]:
    offsets = [0.0]
    for left_id, right_id in zip(block, block[1:]):
        offsets.append(offsets[-1] + _minimum_gap(tree, left_id, right_id))
    return offsets


def _between_block_gap(
    tree: Tree, left_block: list[str], right_block: list[str]
) -> float:
    return _minimum_gap(tree, left_block[-1], right_block[0])


def _minimum_block_base_gap(
    tree: Tree,
    left_block: list[str],
    right_block: list[str],
    left_offsets: list[float],
    right_offsets: list[float],
) -> float:
    return (
        left_offsets[-1]
        + _between_block_gap(tree, left_block, right_block)
        - right_offsets[0]
    )


def _align_children_to_parents(
    tree: Tree,
    generation_order: dict[int, list[str]],
    x_positions: dict[str, float],
) -> dict[str, float]:
    return _align_generation_blocks(
        tree,
        generation_order,
        x_positions,
        _child_alignment_desires,
        sorted(generation_order),
    )


def _align_parents_to_children(
    tree: Tree,
    generation_order: dict[int, list[str]],
    x_positions: dict[str, float],
) -> dict[str, float]:
    return _align_generation_blocks(
        tree,
        generation_order,
        x_positions,
        _parent_alignment_desires,
        sorted(generation_order, reverse=True),
    )


def _align_generation_blocks(
    tree: Tree,
    generation_order: dict[int, list[str]],
    x_positions: dict[str, float],
    desire_builder: Callable[
        [Tree, int, dict[str, float]], dict[str, list[tuple[float, float]]]
    ],
    generations: list[int],
) -> dict[str, float]:
    """Run one directional centering pass over generation blocks."""
    generation_blocks = {
        generation: _generation_blocks(tree, generation, nodes)
        for generation, nodes in generation_order.items()
    }
    block_offsets = {
        generation: [_block_offsets(tree, block) for block in blocks]
        for generation, blocks in generation_blocks.items()
    }
    block_bases = {
        (generation, block_index): x_positions[block[0]]
        - block_offsets[generation][block_index][0]
        for generation, blocks in generation_blocks.items()
        for block_index, block in enumerate(blocks)
    }

    for generation in generations:
        desired = desire_builder(tree, generation, x_positions)
        blocks = generation_blocks[generation]
        desired_bases = []
        for block_index, block in enumerate(blocks):
            offsets = block_offsets[generation][block_index]
            base_values = []
            for person_id, offset in zip(block, offsets):
                for desired_x, weight in desired[person_id]:
                    base_values.append((desired_x - offset, weight))
            fallback = block_bases[(generation, block_index)]
            desired_bases.append(_weighted_average(base_values, fallback))
        gaps = [
            _minimum_block_base_gap(tree, left, right, left_offsets, right_offsets)
            for left, right, left_offsets, right_offsets in zip(
                blocks,
                blocks[1:],
                block_offsets[generation],
                block_offsets[generation][1:],
            )
        ]
        placed_bases = _place_ordered(desired_bases, gaps)
        for block_index, (block, base) in enumerate(zip(blocks, placed_bases)):
            block_bases[(generation, block_index)] = base
            for person_id, offset in zip(block, block_offsets[generation][block_index]):
                x_positions[person_id] = base + offset
    return x_positions


def _snap_single_children_to_parent_centers(
    tree: Tree,
    generation_order: dict[int, list[str]],
    x_positions: dict[str, float],
) -> dict[str, float]:
    """Center one-child family blocks within their available horizontal gap."""
    generation_blocks = {
        generation: _generation_blocks(tree, generation, nodes)
        for generation, nodes in generation_order.items()
    }
    block_offsets = {
        generation: [_block_offsets(tree, block) for block in blocks]
        for generation, blocks in generation_blocks.items()
    }

    for relationship in tree.relationships:
        if len(relationship.children) != 1 or not relationship.partners:
            continue
        child_id = relationship.children[0]
        partners = [
            person_id for person_id in relationship.partners if person_id in x_positions
        ]
        if child_id not in x_positions or not partners:
            continue
        generation = tree.generations.get(child_id)
        if generation not in generation_blocks:
            continue
        block_index = _block_index_containing(
            generation_blocks[generation], (child_id,)
        )
        if block_index is None:
            continue

        blocks = generation_blocks[generation]
        offsets = block_offsets[generation]
        block = blocks[block_index]
        current_base = x_positions[block[0]] - offsets[block_index][0]
        child_offset = offsets[block_index][block.index(child_id)]
        desired_base = (
            mean(x_positions[person_id] for person_id in partners[:2] or partners)
            - child_offset
        )

        min_base = None
        max_base = None
        if block_index > 0:
            previous_block = blocks[block_index - 1]
            previous_offsets = offsets[block_index - 1]
            previous_base = x_positions[previous_block[0]] - previous_offsets[0]
            min_base = previous_base + _minimum_block_base_gap(
                tree,
                previous_block,
                block,
                previous_offsets,
                offsets[block_index],
            )
        if block_index < len(blocks) - 1:
            next_block = blocks[block_index + 1]
            next_offsets = offsets[block_index + 1]
            next_base = x_positions[next_block[0]] - next_offsets[0]
            max_base = next_base - _minimum_block_base_gap(
                tree,
                block,
                next_block,
                offsets[block_index],
                next_offsets,
            )

        new_base = desired_base
        if min_base is not None:
            new_base = max(new_base, min_base)
        if max_base is not None:
            new_base = min(new_base, max_base)
        if abs(new_base - current_base) < 0.5:
            continue
        for person_id, offset in zip(block, offsets[block_index]):
            x_positions[person_id] = new_base + offset
    return x_positions


def _child_alignment_desires(
    tree: Tree,
    generation: int,
    x_positions: dict[str, float],
) -> dict[str, list[tuple[float, float]]]:
    desired: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for relationship in tree.relationships:
        partners = [
            person_id for person_id in relationship.partners if person_id in x_positions
        ]
        children = [
            child_id
            for child_id in relationship.children
            if child_id in x_positions and tree.generations.get(child_id) == generation
        ]
        if not partners or not children:
            continue
        parent_center = mean(
            x_positions[partner_id] for partner_id in partners[:2] or partners
        )
        child_offsets = _centered_offsets(len(children), NODE_WIDTH + NODE_GAP)
        for child_id, offset in zip(children, child_offsets):
            weight = (
                CHILD_CENTERING_WEIGHT * 4
                if len(children) == 1
                else CHILD_CENTERING_WEIGHT
            )
            desired[child_id].append((parent_center + offset, weight))
    return desired


def _parent_alignment_desires(
    tree: Tree,
    generation: int,
    x_positions: dict[str, float],
) -> dict[str, list[tuple[float, float]]]:
    desired: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for relationship in tree.relationships:
        partners = [
            person_id
            for person_id in relationship.partners
            if person_id in x_positions
            and tree.generations.get(person_id) == generation
        ]
        children = [
            child_id for child_id in relationship.children if child_id in x_positions
        ]
        if not partners or not children:
            continue
        child_center = mean(x_positions[child_id] for child_id in children)
        if len(partners) == 1:
            desired[partners[0]].append((child_center, PARENT_CENTERING_WEIGHT))
        elif len(partners) >= 2:
            left, right = partners[:2]
            gap = _minimum_gap(tree, left, right)
            desired[left].append((child_center - gap / 2, PARENT_CENTERING_WEIGHT))
            desired[right].append((child_center + gap / 2, PARENT_CENTERING_WEIGHT))
    return desired


def _add_relationship_desires(
    tree: Tree,
    relationship: Relationship,
    x_positions: dict[str, float],
    desired: dict[str, list[tuple[float, float]]],
) -> None:
    """Accumulate parent/child x-position targets for the solver."""
    partners = [
        person_id for person_id in relationship.partners if person_id in x_positions
    ]
    children = [
        person_id for person_id in relationship.children if person_id in x_positions
    ]
    if partners and children:
        child_center = mean(x_positions[child_id] for child_id in children)
        if len(partners) == 1:
            desired[partners[0]].append((child_center, PARENT_CENTERING_WEIGHT))
        elif len(partners) >= 2:
            left, right = partners[:2]
            gap = _minimum_gap(tree, left, right)
            desired[left].append((child_center - gap / 2, PARENT_CENTERING_WEIGHT))
            desired[right].append((child_center + gap / 2, PARENT_CENTERING_WEIGHT))
        parent_center = mean(
            x_positions[partner_id] for partner_id in partners[:2] or partners
        )
        child_offsets = _centered_offsets(len(children), NODE_WIDTH + NODE_GAP)
        for child_id, offset in zip(children, child_offsets):
            desired[child_id].append((parent_center + offset, CHILD_CENTERING_WEIGHT))


def _centered_offsets(count: int, step: float) -> list[float]:
    if count <= 1:
        return [0.0]
    center = (count - 1) / 2
    return [(index - center) * step for index in range(count)]


def _weighted_average(values: list[tuple[float, float]], fallback: float) -> float:
    if not values:
        return fallback
    total_weight = sum(weight for _, weight in values)
    return sum(value * weight for value, weight in values) / total_weight


def _minimum_gap(tree: Tree, left_id: str, right_id: str) -> float:
    if _are_partners(tree, left_id, right_id):
        return NODE_WIDTH + PARTNER_GAP
    return NODE_WIDTH + NODE_GAP


def _are_partners(tree: Tree, left_id: str, right_id: str) -> bool:
    return any(
        len(relationship.partners) >= 2
        and relationship.partners[0] == left_id
        and relationship.partners[1] == right_id
        for relationship in tree.relationships
    )


def _place_ordered(desired: list[float], gaps: list[float]) -> list[float]:
    """Find positions closest to desired values while preserving minimum gaps."""
    offsets = [0.0]
    for gap in gaps:
        offsets.append(offsets[-1] + gap)
    adjusted = [value - offset for value, offset in zip(desired, offsets)]
    levels = _isotonic_nondecreasing(adjusted)
    return [level + offset for level, offset in zip(levels, offsets)]


def _isotonic_nondecreasing(values: list[float]) -> list[float]:
    """Pool adjacent violators so adjusted positions stay nondecreasing."""
    blocks: list[dict[str, float | int]] = []
    for value in values:
        blocks.append(
            {"sum": value, "weight": 1, "start": len(blocks), "end": len(blocks)}
        )
        while len(blocks) >= 2:
            left = blocks[-2]
            right = blocks[-1]
            if left["sum"] / left["weight"] <= right["sum"] / right["weight"]:
                break
            merged = {
                "sum": left["sum"] + right["sum"],
                "weight": left["weight"] + right["weight"],
                "start": left["start"],
                "end": right["end"],
            }
            blocks[-2:] = [merged]
    result = [0.0 for _ in values]
    cursor = 0
    for block in blocks:
        level = float(block["sum"]) / int(block["weight"])
        for _ in range(int(block["weight"])):
            result[cursor] = level
            cursor += 1
    return result


def _compose_positions(
    tree: Tree,
    x_positions: dict[str, float],
) -> dict[str, tuple[float, float]]:
    min_generation = min(tree.generations.values())
    return {
        person_id: (
            x_positions[person_id],
            (tree.generations[person_id] - min_generation) * GENERATION_GAP,
        )
        for person_id in tree.people
    }


def _assign_child_lanes(
    tree: Tree,
    positions: dict[str, tuple[float, float]],
) -> dict[int, int]:
    """Assign non-overlapping horizontal lanes for parent-to-child branches."""
    lanes_by_generation: dict[int, list[list[tuple[float, float]]]] = defaultdict(list)
    assigned: dict[int, int] = {}
    for relationship in tree.relationships:
        if not relationship.children or not relationship.partners:
            continue
        endpoints = [
            positions[person_id][0]
            for person_id in relationship.partners + relationship.children
            if person_id in positions
        ]
        if not endpoints:
            continue
        generation = tree.generations[relationship.partners[0]]
        interval = (
            min(endpoints) - CHILD_BRANCH_LANE_PADDING,
            max(endpoints) + CHILD_BRANCH_LANE_PADDING,
        )
        lanes = lanes_by_generation[generation]
        lane_index = _first_non_overlapping_lane(lanes, interval)
        assigned[relationship.index] = lane_index
    return assigned


def _assign_partner_lanes(
    tree: Tree,
    positions: dict[str, tuple[float, float]],
    generation_order: dict[int, list[str]],
) -> dict[int, int]:
    """Assign route lanes for partner lines whose boxes are not adjacent."""
    lanes_by_generation: dict[int, list[list[tuple[float, float]]]] = defaultdict(list)
    assigned: dict[int, int] = {}
    ranks = {
        person_id: index
        for nodes in generation_order.values()
        for index, person_id in enumerate(nodes)
    }
    for relationship in tree.relationships:
        if len(relationship.partners) < 2:
            continue
        left, right = relationship.partners[:2]
        if left not in positions or right not in positions:
            continue
        if abs(ranks[left] - ranks[right]) == 1:
            assigned[relationship.index] = 0
            continue
        generation = tree.generations[left]
        interval = (
            min(positions[left][0], positions[right][0]) - ROUTED_PARTNER_OFFSET,
            max(positions[left][0], positions[right][0]) + ROUTED_PARTNER_OFFSET,
        )
        lanes = lanes_by_generation[generation]
        lane_index = _first_non_overlapping_lane(lanes, interval)
        assigned[relationship.index] = lane_index + 1
    return assigned


def _first_non_overlapping_lane(
    lanes: list[list[tuple[float, float]]],
    interval: tuple[float, float],
) -> int:
    for lane_index, lane in enumerate(lanes):
        if all(interval[1] < used[0] or interval[0] > used[1] for used in lane):
            lane.append(interval)
            return lane_index
    lanes.append([interval])
    return len(lanes) - 1


def child_branch_y(parent_top: float, lane: int) -> float:
    return parent_top + NODE_HEIGHT + CHILD_BRANCH_GAP + lane * CHILD_BRANCH_LANE_GAP


def routed_partner_y(top: float, lane: int) -> float:
    return top - ROUTED_PARTNER_OFFSET - (lane - 1) * ROUTED_PARTNER_LANE_GAP
