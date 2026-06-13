#!/usr/bin/env python3
import argparse
from pathlib import Path

from src.graph import build_tree
from src.layout import layout_tree
from src.parser import load_family_file
from src.render import render_png


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a family tree PNG.")
    parser.add_argument(
        "yaml_path",
        help="Path to the family YAML file.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output PNG path. Defaults to the YAML filename with a .png suffix.",
    )
    args = parser.parse_args()

    yaml_path = Path(args.yaml_path)
    output_path = args.output or yaml_path.with_suffix(".png")

    family = load_family_file(yaml_path)
    tree = build_tree(family)
    layout = layout_tree(tree)
    render_png(tree, layout, output_path)
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
