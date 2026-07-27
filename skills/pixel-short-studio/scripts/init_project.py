#!/usr/bin/env python3
"""Initialize a neutral Pixel Short Studio project."""

from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path


SKILL = Path(__file__).resolve().parent.parent
TEMPLATE = SKILL / "assets" / "project-template"


def slugify(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    if not value:
        raise ValueError("name must contain letters or digits")
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True, help="Project name or slug")
    parser.add_argument("--out", required=True, help="Parent output directory")
    parser.add_argument("--force", action="store_true", help="Replace an existing empty template")
    args = parser.parse_args()

    target = Path(args.out).expanduser().resolve() / slugify(args.name)
    if target.exists():
        if not args.force:
            raise SystemExit(f"target exists: {target}")
        if any(target.iterdir()):
            raise SystemExit(f"refusing to replace non-empty target: {target}")
        target.rmdir()

    shutil.copytree(TEMPLATE, target)
    print(target)


if __name__ == "__main__":
    main()

