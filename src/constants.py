"""Tunable constants for family tree layout and rendering."""

from __future__ import annotations

from pathlib import Path

# Logical size of each person rectangle. Layout is computed in these logical
# units, then multiplied by OUTPUT_SCALE when the PNG is rendered.
NODE_WIDTH = 172
NODE_HEIGHT = 74

# Horizontal spacing between unrelated neighboring boxes and spouse boxes.
NODE_GAP = 64
PARTNER_GAP = 52

# Outer whitespace around the full rendered tree.
MARGIN_X = 80
MARGIN_Y = 80

# Vertical distance between generations.
GENERATION_GAP = 220

# Increase this to render a sharper, larger PNG without changing layout.
OUTPUT_SCALE = 2.0

# Basic line and fill styling.
LINE_WIDTH = 3
LINE_COLOR = (70, 74, 82)
DOTTED_LINE_DASH = 8
DOTTED_LINE_GAP = 7
BOX_OUTLINE = (52, 58, 67)
BOX_FILL = (252, 252, 250)
TEXT_COLOR = (24, 27, 31)
BACKGROUND_COLOR = (255, 255, 255)

# Font sizes and padding inside person rectangles.
MAX_PRIMARY_FONT_SIZE = 24
MAX_SECONDARY_FONT_SIZE = 20
MIN_FONT_SIZE = 10
TEXT_HORIZONTAL_PADDING = 14
TEXT_VERTICAL_PADDING = 10
TEXT_LINE_GAP = 7

# Child branches are routed through horizontal lanes below parent boxes.
CHILD_BRANCH_GAP = 72
CHILD_BRANCH_LANE_GAP = 20
CHILD_BRANCH_LANE_PADDING = 18

# Non-adjacent partner lines route above the boxes through separate lanes.
ROUTED_PARTNER_OFFSET = 30
ROUTED_PARTNER_LANE_GAP = 18
ROUTED_PARTNER_STUB = 14

# Iterative layout tuning weights. Higher parent/child weights pull the centers
# of related family blocks closer together while preserving ordering constraints.
LAYOUT_ITERATIONS = 30
PARENT_CENTERING_WEIGHT = 2.5
CHILD_CENTERING_WEIGHT = 2.0

# Prefer fonts with broad CJK coverage, falling back to common Latin fonts.
FONT_CANDIDATES = (
    Path("/System/Library/Fonts/PingFang.ttc"),
    Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
    Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
    Path("/Library/Fonts/Arial Unicode.ttf"),
    Path("/Library/Fonts/Arial.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
)
