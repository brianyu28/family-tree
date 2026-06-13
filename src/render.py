"""PNG rendering with Pillow."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .constants import (
    BACKGROUND_COLOR,
    BOX_FILL,
    BOX_OUTLINE,
    DOTTED_LINE_DASH,
    DOTTED_LINE_GAP,
    FONT_CANDIDATES,
    LINE_COLOR,
    LINE_WIDTH,
    MAX_PRIMARY_FONT_SIZE,
    MAX_SECONDARY_FONT_SIZE,
    MIN_FONT_SIZE,
    NODE_HEIGHT,
    NODE_WIDTH,
    OUTPUT_SCALE,
    ROUTED_PARTNER_STUB,
    TEXT_COLOR,
    TEXT_HORIZONTAL_PADDING,
    TEXT_LINE_GAP,
    TEXT_VERTICAL_PADDING,
)
from .layout import child_branch_y, routed_partner_y
from .model import Layout, Person, Relationship, Tree


def render_png(tree: Tree, layout: Layout, output_path: Path) -> None:
    """Render the tree to a PNG, scaling drawing operations for sharp output."""
    scale = _output_scale()
    image = Image.new(
        "RGB",
        (_scaled_int(layout.width, scale), _scaled_int(layout.height, scale)),
        BACKGROUND_COLOR,
    )
    draw = ImageDraw.Draw(image)

    for relationship in tree.relationships:
        _draw_relationship(draw, relationship, tree, layout, scale)
    for person_id in _draw_order(tree):
        _draw_person(draw, tree.people[person_id], layout.positions[person_id], scale)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path)


def _draw_order(tree: Tree) -> list[str]:
    return sorted(
        tree.people, key=lambda person_id: (tree.generations[person_id], person_id)
    )


def _draw_relationship(
    draw: ImageDraw.ImageDraw,
    relationship: Relationship,
    tree: Tree,
    layout: Layout,
    scale: float,
) -> None:
    """Draw partner and child connectors for one relationship."""
    partners = [
        person_id
        for person_id in relationship.partners
        if person_id in layout.positions
    ]
    children = [
        person_id
        for person_id in relationship.children
        if person_id in layout.positions
    ]

    _draw_partner_line(draw, relationship, partners, layout, scale)
    if children:
        _draw_child_lines(draw, relationship, partners, children, layout, scale)


def _draw_partner_line(
    draw: ImageDraw.ImageDraw,
    relationship: Relationship,
    partners: list[str],
    layout: Layout,
    scale: float,
) -> None:
    if len(partners) < 2:
        return
    left_id, right_id = partners[:2]
    start, end = _partner_side_points(left_id, right_id, layout)

    lane = layout.partner_lanes.get(relationship.index, 0)
    if lane == 0:
        _line(draw, [start, end], relationship.current, scale)
        return

    y_route = routed_partner_y(layout.positions[left_id][1], lane)
    stub_direction = 1 if end[0] > start[0] else -1
    points = [
        start,
        (start[0] + stub_direction * ROUTED_PARTNER_STUB, start[1]),
        (start[0] + stub_direction * ROUTED_PARTNER_STUB, y_route),
        (end[0] - stub_direction * ROUTED_PARTNER_STUB, y_route),
        (end[0] - stub_direction * ROUTED_PARTNER_STUB, end[1]),
        end,
    ]
    _line(draw, points, relationship.current, scale)


def _draw_child_lines(
    draw: ImageDraw.ImageDraw,
    relationship: Relationship,
    partners: list[str],
    children: list[str],
    layout: Layout,
    scale: float,
) -> None:
    """Draw the vertical stem, sibling branch, and child drops."""
    if partners:
        parent_x_values = [layout.positions[person_id][0] for person_id in partners]
        parent_top = min(layout.positions[person_id][1] for person_id in partners)
        if len(partners) == 1:
            origin_x = parent_x_values[0]
            origin_y = parent_top + NODE_HEIGHT
        elif layout.partner_lanes.get(relationship.index, 0) > 0:
            origin_x, origin_y = _routed_partner_child_origin(
                relationship, partners, children, layout, parent_top
            )
        else:
            origin_x = sum(parent_x_values[:2]) / min(len(parent_x_values), 2)
            origin_y = parent_top + NODE_HEIGHT / 2
    else:
        child_x_values = [layout.positions[person_id][0] for person_id in children]
        origin_x = sum(child_x_values) / len(child_x_values)
        parent_top = (
            min(layout.positions[person_id][1] for person_id in children) - NODE_HEIGHT
        )
        origin_y = parent_top + NODE_HEIGHT

    lane = layout.child_lanes.get(relationship.index, 0)
    branch_y = child_branch_y(parent_top, lane)
    child_points = [
        (layout.positions[child_id][0], layout.positions[child_id][1])
        for child_id in children
    ]

    if len(children) == 1:
        child_x, child_top = child_points[0]
        _line(
            draw,
            [
                (origin_x, origin_y),
                (origin_x, branch_y),
                (child_x, branch_y),
                (child_x, child_top),
            ],
            True,
            scale,
        )
        return

    first_x = min([origin_x, *(x for x, _ in child_points)])
    last_x = max([origin_x, *(x for x, _ in child_points)])
    _line(draw, [(origin_x, origin_y), (origin_x, branch_y)], True, scale)
    _line(draw, [(first_x, branch_y), (last_x, branch_y)], True, scale)
    for child_x, child_top in child_points:
        _line(draw, [(child_x, branch_y), (child_x, child_top)], True, scale)


def _routed_partner_child_origin(
    relationship: Relationship,
    partners: list[str],
    children: list[str],
    layout: Layout,
    parent_top: float,
) -> tuple[float, float]:
    """Choose a clear child stem point on a routed partner connector."""
    left_id, right_id = partners[:2]
    start, end = _partner_side_points(left_id, right_id, layout)
    lane = layout.partner_lanes[relationship.index]
    route_y = routed_partner_y(parent_top, lane)
    stub_direction = 1 if end[0] > start[0] else -1
    segment_start_x = start[0] + stub_direction * ROUTED_PARTNER_STUB
    segment_end_x = end[0] - stub_direction * ROUTED_PARTNER_STUB
    low_x = min(segment_start_x, segment_end_x)
    high_x = max(segment_start_x, segment_end_x)

    child_x_values = [layout.positions[child_id][0] for child_id in children]
    desired_x = sum(child_x_values) / len(child_x_values)
    return (
        _nearest_open_vertical_x(layout, desired_x, low_x, high_x, route_y, parent_top),
        route_y,
    )


def _partner_side_points(
    left_id: str,
    right_id: str,
    layout: Layout,
) -> tuple[tuple[float, float], tuple[float, float]]:
    left_x, left_y = layout.positions[left_id]
    right_x, right_y = layout.positions[right_id]
    if left_x <= right_x:
        return (
            (left_x + NODE_WIDTH / 2, left_y + NODE_HEIGHT / 2),
            (right_x - NODE_WIDTH / 2, right_y + NODE_HEIGHT / 2),
        )
    return (
        (left_x - NODE_WIDTH / 2, left_y + NODE_HEIGHT / 2),
        (right_x + NODE_WIDTH / 2, right_y + NODE_HEIGHT / 2),
    )


def _nearest_open_vertical_x(
    layout: Layout,
    desired_x: float,
    low_x: float,
    high_x: float,
    origin_y: float,
    row_top: float,
) -> float:
    """Find the closest x where a vertical stem can pass between row boxes."""
    padding = max(LINE_WIDTH * 6, 18)
    blocked_intervals = []
    row_bottom = row_top + NODE_HEIGHT
    for center_x, top in layout.positions.values():
        bottom = top + NODE_HEIGHT
        if bottom < origin_y or top > row_bottom:
            continue
        blocked_intervals.append(
            (
                center_x - NODE_WIDTH / 2 - padding,
                center_x + NODE_WIDTH / 2 + padding,
            )
        )

    open_intervals: list[tuple[float, float]] = []
    cursor = low_x
    for blocked_start, blocked_end in sorted(blocked_intervals):
        if blocked_end <= low_x or blocked_start >= high_x:
            continue
        blocked_start = max(blocked_start, low_x)
        blocked_end = min(blocked_end, high_x)
        if cursor < blocked_start:
            open_intervals.append((cursor, blocked_start))
        cursor = max(cursor, blocked_end)
    if cursor < high_x:
        open_intervals.append((cursor, high_x))

    if not open_intervals:
        return min(max(desired_x, low_x), high_x)

    candidates = [
        _preferred_x_in_interval(desired_x, interval_start, interval_end)
        for interval_start, interval_end in open_intervals
    ]
    return min(candidates, key=lambda x: abs(x - desired_x))


def _preferred_x_in_interval(
    desired_x: float,
    interval_start: float,
    interval_end: float,
) -> float:
    if interval_start <= desired_x <= interval_end:
        return desired_x
    return (interval_start + interval_end) / 2


def _line(
    draw: ImageDraw.ImageDraw,
    points: list[tuple[float, float]],
    solid: bool,
    scale: float,
) -> None:
    scaled_points = [_scaled_point(point, scale) for point in points]
    if solid:
        draw.line(
            scaled_points,
            fill=LINE_COLOR,
            width=_scaled_width(LINE_WIDTH, scale),
            joint="curve",
        )
        return
    for start, end in zip(scaled_points, scaled_points[1:]):
        _dotted_segment(draw, start, end, scale)


def _dotted_segment(
    draw: ImageDraw.ImageDraw,
    start: tuple[float, float],
    end: tuple[float, float],
    scale: float,
) -> None:
    x1, y1 = start
    x2, y2 = end
    length = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
    if length == 0:
        return
    dx = (x2 - x1) / length
    dy = (y2 - y1) / length
    cursor = 0.0
    dash = DOTTED_LINE_DASH * scale
    gap = DOTTED_LINE_GAP * scale
    while cursor < length:
        dash_end = min(cursor + dash, length)
        draw.line(
            [
                (x1 + dx * cursor, y1 + dy * cursor),
                (x1 + dx * dash_end, y1 + dy * dash_end),
            ],
            fill=LINE_COLOR,
            width=_scaled_width(LINE_WIDTH, scale),
        )
        cursor += dash + gap


def _draw_person(
    draw: ImageDraw.ImageDraw,
    person: Person,
    center_top: tuple[float, float],
    scale: float,
) -> None:
    center_x, top = center_top
    left = center_x - NODE_WIDTH / 2
    right = center_x + NODE_WIDTH / 2
    bottom = top + NODE_HEIGHT
    draw.rectangle(
        _scaled_box((left, top, right, bottom), scale),
        fill=BOX_FILL,
        outline=BOX_OUTLINE,
        width=_scaled_width(2, scale),
    )

    primary = person.name or ""
    secondary = person.secondary_name
    if not primary and not secondary:
        return

    text_box_width = (NODE_WIDTH - 2 * TEXT_HORIZONTAL_PADDING) * scale
    text_box_height = (NODE_HEIGHT - 2 * TEXT_VERTICAL_PADDING) * scale
    if primary and secondary:
        primary_font = _fit_font(primary, MAX_PRIMARY_FONT_SIZE, text_box_width, scale)
        secondary_font = _fit_font(
            secondary, MAX_SECONDARY_FONT_SIZE, text_box_width, scale
        )
        lines = [(primary, primary_font), (secondary, secondary_font)]
    else:
        lines = _fit_single_name(
            primary or secondary or "", text_box_width, text_box_height, scale
        )

    total_height = sum(_text_metrics(draw, text, font)[1] for text, font in lines)
    total_height += TEXT_LINE_GAP * scale * (len(lines) - 1)
    center_x *= scale
    top *= scale
    y = top + (NODE_HEIGHT * scale - total_height) / 2
    for text, font in lines:
        width, height, left_offset, top_offset = _text_metrics(draw, text, font)
        draw.text(
            (center_x - width / 2 - left_offset, y - top_offset),
            text,
            fill=TEXT_COLOR,
            font=font,
        )
        y += height + TEXT_LINE_GAP * scale


def _fit_single_name(
    text: str,
    max_width: float,
    max_height: float,
    scale: float,
) -> list[tuple[str, ImageFont.FreeTypeFont | ImageFont.ImageFont]]:
    """Fit a one-name label, splitting into two balanced lines if helpful."""
    one_line_font = _fit_font(text, MAX_PRIMARY_FONT_SIZE, max_width, scale)
    if _font_size(one_line_font) >= _scaled_font_size(MAX_PRIMARY_FONT_SIZE - 2, scale):
        return [(text, one_line_font)]

    words = text.split()
    if len(words) <= 1:
        return [(text, one_line_font)]

    split_index = _balanced_split_index(words)
    lines = [" ".join(words[:split_index]), " ".join(words[split_index:])]
    font_size = _scaled_font_size(MAX_PRIMARY_FONT_SIZE, scale)
    min_font_size = _scaled_font_size(MIN_FONT_SIZE, scale)
    while font_size >= min_font_size:
        font = _load_font(font_size)
        dummy = Image.new("RGB", (1, 1))
        draw = ImageDraw.Draw(dummy)
        widths = [_text_metrics(draw, line, font)[0] for line in lines]
        heights = [_text_metrics(draw, line, font)[1] for line in lines]
        if (
            max(widths) <= max_width
            and sum(heights) + TEXT_LINE_GAP * scale <= max_height
        ):
            return [(line, font) for line in lines]
        font_size -= 1
    font = _load_font(min_font_size)
    return [(line, font) for line in lines]


def _balanced_split_index(words: list[str]) -> int:
    best_index = 1
    best_score = float("inf")
    for index in range(1, len(words)):
        left = " ".join(words[:index])
        right = " ".join(words[index:])
        score = abs(len(left) - len(right))
        if score < best_score:
            best_score = score
            best_index = index
    return best_index


def _fit_font(
    text: str,
    max_size: int,
    max_width: float,
    scale: float,
) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Return the largest available font that fits the supplied width."""
    dummy = Image.new("RGB", (1, 1))
    draw = ImageDraw.Draw(dummy)
    min_size = _scaled_font_size(MIN_FONT_SIZE, scale)
    for size in range(_scaled_font_size(max_size, scale), min_size - 1, -1):
        font = _load_font(size)
        if _text_metrics(draw, text, font)[0] <= max_width:
            return font
    return _load_font(min_size)


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for candidate in FONT_CANDIDATES:
        if candidate.exists():
            try:
                return ImageFont.truetype(str(candidate), size=size)
            except OSError:
                continue
    return ImageFont.load_default(size=size)


def _font_size(font: ImageFont.FreeTypeFont | ImageFont.ImageFont) -> int:
    return getattr(font, "size", MIN_FONT_SIZE)


def _text_metrics(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
) -> tuple[int, int, int, int]:
    """Return width, height, and bbox offsets for precise visual centering."""
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1], bbox[0], bbox[1]


def _output_scale() -> float:
    return max(float(OUTPUT_SCALE), 1.0)


def _scaled_int(value: float, scale: float) -> int:
    return int(round(value * scale))


def _scaled_width(value: float, scale: float) -> int:
    return max(1, _scaled_int(value, scale))


def _scaled_font_size(value: int, scale: float) -> int:
    return max(1, _scaled_int(value, scale))


def _scaled_point(point: tuple[float, float], scale: float) -> tuple[float, float]:
    return point[0] * scale, point[1] * scale


def _scaled_box(
    box: tuple[float, float, float, float], scale: float
) -> tuple[float, float, float, float]:
    left, top, right, bottom = box
    return left * scale, top * scale, right * scale, bottom * scale
