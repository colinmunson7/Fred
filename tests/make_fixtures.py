"""Write fake feed files for every source in sources.yaml, for offline tests.

Each source gets 6 items spread over the last 3 days. A few sources get
special content so the filters can be tested.
"""
from __future__ import annotations

import re
import sys
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path
from xml.sax.saxutils import escape

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from build import offline_name  # noqa: E402

SPECIAL = {
    "Mountain Tactical Institute": [
        "SWAT Operator After a 22K Trail Race",
        "Mountain Base Fitness: 6-Week Plan Review",
        "AFROTC Cadets See Fitness Improvements",
        "How to Build Uphill Leg Strength",
    ],
    "Nintendo Life": [
        "Pikmin Soundtrack Added to Nintendo Music",
        "New Pokémon Legends Trailer Drops",
        "Mario Kart Update Patch Notes",
        "Zelda Anniversary Concert Announced",
    ],
}


def rss(name: str, titles: list[str], now: datetime, comments: bool, post: bool) -> str:
    items = []
    for n, title in enumerate(titles):
        when = now - timedelta(hours=3 + n * 11)
        slug = re.sub(r"[^a-z0-9]+", "-", f"{name} {title}".lower())
        body = f"<description>{escape(title)} and more detail.</description>"
        head = "" if post else f"<title>{escape(title)}</title>"
        extra = f"<slash:comments>{(7 - n) * 3}</slash:comments>" if comments else ""
        items.append(f"<item>{head}<link>https://example.com/{slug}</link>"
                     f"<pubDate>{format_datetime(when)}</pubDate>{body}{extra}</item>")
    return ('<?xml version="1.0"?><rss version="2.0" '
            'xmlns:slash="http://purl.org/rss/1.0/modules/slash/"><channel>'
            f"<title>{escape(name)}</title><link>https://example.com</link>"
            f"<description>fixture</description>{''.join(items)}</channel></rss>")


def main(out: Path) -> None:
    config = yaml.safe_load((ROOT / "sources.yaml").read_text())
    now = datetime.now(timezone.utc)
    out.mkdir(parents=True, exist_ok=True)
    sources = list(config["briefing"]) + [s for t in config["topics"] for s in t["sources"]]
    for i, src in enumerate(sources):
        titles = SPECIAL.get(src["name"]) or [f"{src['name']} story number {n + 1}" for n in range(6)]
        xml = rss(src["name"], titles, now, comments=(i % 3 == 0), post=src["type"] == "bluesky")
        (out / offline_name(src)).write_text(xml)
    print(f"wrote {len(sources)} fixtures to {out}")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "tests" / "fixtures")
