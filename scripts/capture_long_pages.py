#!/usr/bin/env python3
"""Capture the public KfreqAI dashboard and product/blog top using kargov."""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.page_capture import capture_pages


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "images")
    parser.add_argument("--width", type=int, default=1440)
    parser.add_argument("--height", type=int, default=900)
    args = parser.parse_args()
    pages = [
        ("kfreqai_blog", "https://kfreqai.exbridge.jp/"),
        ("kfreqai_dashboard", "https://kurage.exbridge.jp/kfreqai.php?view=summary"),
    ]
    paths = asyncio.run(capture_pages(pages, args.output, width=args.width, height=args.height))
    for path in paths:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
