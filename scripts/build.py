#!/usr/bin/env python3
"""Build one edition of Fred.

Reads sources.yaml, pulls every feed, picks the edition's headlines and writes
site/data.json for the front page. Remembers what it has already shown in
data/history.json so the same headline doesn't come back in later editions.

Usage:
    python scripts/build.py                     # live run (fetches feeds)
    python scripts/build.py --offline FIXTURES  # read saved feed files instead
"""
from __future__ import annotations

import argparse
import concurrent.futures as futures
import hashlib
import html
import json
import re
import sys
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import feedparser
import yaml

ROOT = Path(__file__).resolve().parent.parent
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/130.0 Safari/537.36 Fred/1.1")
HISTORY_DAYS = 14


# ---------------------------------------------------------------- data shapes

@dataclass
class Item:
    id: str
    title: str
    link: str
    source: str
    topic: str
    kind: str              # article | post | video | game
    published: str         # ISO 8601, UTC
    score: int | None = None   # popularity signal (comment count) when a feed has one

    @property
    def published_dt(self) -> datetime:
        return datetime.fromisoformat(self.published)


@dataclass
class FetchReport:
    source: str
    ok: bool
    items: int = 0
    error: str = ""
    verify: bool = False


# ---------------------------------------------------------------- feed URLs

def feed_url(src: dict) -> str:
    kind = src["type"]
    if kind == "rss":
        return src["url"]
    if kind == "bluesky":
        return f"https://bsky.app/profile/{src['handle']}/rss"
    if kind == "youtube":
        # The UULF playlist is a channel's long-form uploads only (no Shorts).
        return f"https://www.youtube.com/feeds/videos.xml?playlist_id=UULF{src['channel_id'][2:]}"
    raise ValueError(f"Unknown source type: {kind}")


DLES_LIST = "https://raw.githubusercontent.com/aukspot/dles/main/src/lib/data/dles.json"


def dles_item(src: dict, topic: str, now: datetime, edition_id: str,
              offline_dir: Path | None) -> list[Item]:
    """Pick one game from the dles.aukspot.com list (open source: github.com/aukspot/dles).

    The choice is seeded by the edition, so rebuilding an edition keeps the same game.
    """
    import random

    def item(name: str, description: str, url: str) -> Item:
        title = f"{name}: {description}" if description else name
        uid = hashlib.sha1(f"{url}|{edition_id}".encode()).hexdigest()[:12]
        return Item(uid, title, url, src["name"], topic, "game", now.isoformat())

    if offline_dir is not None:
        return [item("Bandle", "Guess the song, one instrument at a time.", "https://bandle.app")]

    import requests

    games = requests.get(DLES_LIST, headers={"User-Agent": USER_AGENT}, timeout=20).json()
    games = sorted((g for g in games if g.get("url")), key=lambda g: g.get("id", 0))
    game = random.Random(edition_id).choice(games)
    return [item(game["name"], (game.get("description") or "").strip(), game["url"])]


def offline_name(src: dict) -> str:
    return re.sub(r"[^a-z0-9]+", "-", src["name"].lower()).strip("-") + ".xml"


# ---------------------------------------------------------------- fetching

def fetch(src: dict, offline_dir: Path | None) -> bytes:
    if offline_dir is not None:
        path = offline_dir / offline_name(src)
        if not path.exists():
            raise FileNotFoundError(f"no fixture {path.name}")
        return path.read_bytes()
    import requests  # imported here so offline runs and tests don't need network libs

    resp = requests.get(feed_url(src), headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, */*;q=0.8"}, timeout=20)
    resp.raise_for_status()
    return resp.content


TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")


def clean(text: str) -> str:
    text = html.unescape(TAG_RE.sub(" ", text or ""))
    return SPACE_RE.sub(" ", text).strip()


def shorten(text: str, limit: int = 160) -> str:
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return cut.rstrip(",.;:") + "…"


def entry_time(entry) -> datetime | None:
    for key in ("published_parsed", "updated_parsed"):
        value = entry.get(key)
        if value:
            return datetime(*value[:6], tzinfo=timezone.utc)
    return None


def comment_count(entry) -> int | None:
    # WordPress and many forums publish <slash:comments>; feedparser exposes it here.
    for key in ("slash_comments", "thr_total"):
        value = entry.get(key)
        if value not in (None, ""):
            try:
                return int(value)
            except (TypeError, ValueError):
                pass
    return None


def parse(src: dict, topic: str, raw: bytes) -> list[Item]:
    feed = feedparser.parse(raw)
    if feed.bozo and not feed.entries:
        raise ValueError(f"unreadable feed ({feed.bozo_exception})")
    kind = {"bluesky": "post", "youtube": "video"}.get(src["type"], "article")
    items = []
    for entry in feed.entries:
        when = entry_time(entry)
        link = entry.get("link", "")
        if not when or not link:
            continue
        title = clean(entry.get("title", ""))
        if kind == "post" or not title:
            # Bluesky posts have no headline: the post text is the headline.
            text = clean(entry.get("summary") or entry.get("description") or title)
            text = text.replace("[contains quote post or other embedded content]", "").strip()
            title = shorten(text)
        if not title:
            continue
        if kind == "post" and src.get("skip_replies", True) and title.startswith("@"):
            continue
        uid = hashlib.sha1(link.encode()).hexdigest()[:12]
        items.append(Item(uid, title, link, src["name"], topic, kind,
                          when.isoformat(), comment_count(entry)))
    return apply_filters(src, items)


def apply_filters(src: dict, items: list[Item]) -> list[Item]:
    include = [w.lower() for w in src.get("include", [])]
    exclude = [w.lower() for w in src.get("exclude", [])]
    kept = []
    for item in items:
        text = item.title.lower()
        if include and not any(w in text for w in include):
            continue
        if any(re.search(rf"\b{re.escape(w)}\b", text) for w in exclude):
            continue
        kept.append(item)
    return kept


def gather(groups: list[tuple[str, list[dict]]], offline_dir: Path | None,
           now: datetime | None = None, edition_id: str = ""):
    """Fetch every source in parallel. Returns (items by topic, reports)."""
    now = now or datetime.now(timezone.utc)
    jobs = [(topic, src) for topic, sources in groups for src in sources]
    by_topic: dict[str, list[Item]] = {topic: [] for topic, _ in groups}
    reports: list[FetchReport] = []

    def run(job):
        topic, src = job
        try:
            if src["type"] == "dles":
                items = dles_item(src, topic, now, edition_id, offline_dir)
            else:
                items = parse(src, topic, fetch(src, offline_dir))
            return topic, items, FetchReport(src["name"], True, len(items), verify=src.get("verify", False))
        except Exception as exc:  # one broken feed should never break the edition
            return topic, [], FetchReport(src["name"], False, 0, str(exc)[:200], src.get("verify", False))

    with futures.ThreadPoolExecutor(max_workers=12) as pool:
        for topic, items, report in pool.map(run, jobs):
            by_topic[topic].extend(items)
            reports.append(report)
    return by_topic, reports


# ---------------------------------------------------------------- choosing headlines

def norm_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def dedupe(items: list[Item], seen: set[str]) -> list[Item]:
    out, links, titles = [], set(), set()
    for item in items:
        key = norm_title(item.title)
        if item.id in seen or item.link in links or key in titles:
            continue
        links.add(item.link)
        titles.add(key)
        out.append(item)
    return out


def rank(items: list[Item]) -> list[Item]:
    """Popularity where a feed reports it, otherwise newest first.

    Items with a comment count are compared on comments-per-hour so a busy
    week-old thread doesn't beat a lively new one.
    """
    now = datetime.now(timezone.utc)

    def key(item: Item):
        age_h = max((now - item.published_dt).total_seconds() / 3600, 1)
        heat = (item.score / age_h) if item.score else 0
        return (heat, item.published_dt)

    return sorted(items, key=key, reverse=True)


def interleave(items: list[Item]) -> list[Item]:
    """Take each source's best item in turn, so a topic's picks come from
    different sources (a busy Bluesky account can't fill a whole topic)."""
    by_source: dict[str, list[Item]] = {}
    for item in items:                      # items arrive already ranked
        by_source.setdefault(item.source, []).append(item)
    out: list[Item] = []
    while any(by_source.values()):
        for queue in by_source.values():
            if queue:
                out.append(queue.pop(0))
    return out


def recent(items: list[Item], hours: float, now: datetime) -> list[Item]:
    cutoff = now - timedelta(hours=hours)
    return [i for i in items if i.published_dt >= cutoff]


def fresh_by_source(items: list[Item], settings: dict, now: datetime, seen: set[str]) -> list[Item]:
    """Everything from the last lookback_hours, plus, for any source with nothing
    that recent, its newest unseen item from the last slow_topic_lookback_days."""
    by_source: dict[str, list[Item]] = {}
    for item in items:
        by_source.setdefault(item.source, []).append(item)
    out: list[Item] = []
    for source_items in by_source.values():
        fresh = recent(source_items, settings["lookback_hours"], now)
        if not [i for i in fresh if i.id not in seen]:
            older = [i for i in recent(source_items, settings["slow_topic_lookback_days"] * 24, now)
                     if i.id not in seen]
            fresh = sorted(older, key=lambda i: i.published_dt, reverse=True)[:1]
        out.extend(fresh)
    return out


def pick(by_topic: dict[str, list[Item]], settings: dict, now: datetime,
         seen: set[str]) -> tuple[list[Item], list[Item]]:
    """Round-robin across topics so every area gets a turn, within the caps."""
    total = settings["posts_per_batch"] + settings["reserve_size"]
    per_topic = settings["max_per_topic"]
    per_source = settings["max_per_source"]

    queues: dict[str, list[Item]] = {}
    for topic, items in by_topic.items():
        queues[topic] = interleave(rank(dedupe(fresh_by_source(items, settings, now, seen), seen)))

    chosen: list[Item] = []
    topic_count = {t: 0 for t in queues}
    source_count: dict[str, int] = {}
    used_titles: set[str] = set()

    def take_one(topic: str, cap: int) -> bool:
        if topic_count[topic] >= cap:
            return False
        queue = queues[topic]
        while queue:
            item = queue.pop(0)
            if source_count.get(item.source, 0) >= per_source:
                continue
            if norm_title(item.title) in used_titles:
                continue
            chosen.append(item)
            topic_count[topic] += 1
            source_count[item.source] = source_count.get(item.source, 0) + 1
            used_titles.add(norm_title(item.title))
            return True
        return False

    # Main edition: strict caps.
    while len(chosen) < settings["posts_per_batch"]:
        progressed = False
        for topic in queues:
            if len(chosen) >= settings["posts_per_batch"]:
                break
            progressed |= take_one(topic, per_topic)
        if not progressed:
            break
    main = chosen[:]

    # Reserve for "show a few more": allow one extra per topic beyond the cap.
    while len(chosen) < total:
        progressed = False
        for topic in queues:
            if len(chosen) >= total:
                break
            progressed |= take_one(topic, per_topic + 2)
        if not progressed:
            break
    reserve = chosen[len(main):]
    return main, reserve


def pick_briefing(items: list[Item], size: int, now: datetime, seen: set[str]) -> list[Item]:
    """Newest stories, alternating between outlets."""
    fresh = dedupe(sorted(recent(items, 24, now), key=lambda i: i.published_dt, reverse=True), seen)
    by_source: dict[str, list[Item]] = {}
    for item in fresh:
        by_source.setdefault(item.source, []).append(item)
    out: list[Item] = []
    while len(out) < size and any(by_source.values()):
        for queue in by_source.values():
            if queue and len(out) < size:
                out.append(queue.pop(0))
    return out


# ---------------------------------------------------------------- history

def load_history(path: Path, now: datetime) -> dict[str, dict]:
    """{item id: {"t": when shown, "e": edition id}} for the last two weeks."""
    if not path.exists():
        return {}
    data = json.loads(path.read_text())
    cutoff = now - timedelta(days=HISTORY_DAYS)
    out = {}
    for key, value in data.items():
        if isinstance(value, str):          # older format: no edition recorded
            value = {"t": value, "e": ""}
        if datetime.fromisoformat(value["t"]) >= cutoff:
            out[key] = value
    return out


# ---------------------------------------------------------------- main

def edition_name(now: datetime, tz: str) -> tuple[str, str]:
    local = now.astimezone(ZoneInfo(tz))
    label = "Morning" if local.hour < 12 else "Evening"
    return f"{local:%Y-%m-%d}-{label.lower()}", f"{label} edition · {local:%A, %B} {local.day}"


def build(config_path: Path, out_path: Path, history_path: Path,
          offline_dir: Path | None = None, now: datetime | None = None) -> dict:
    config = yaml.safe_load(config_path.read_text())
    settings = config["settings"]
    now = now or datetime.now(timezone.utc)
    history = load_history(history_path, now)
    edition_id, edition_label = edition_name(now, settings["timezone"])
    # Skip stories shown in earlier editions, but not ones from this same edition:
    # a rebuild of the current edition should come out the same, not use up stories.
    seen = {k for k, v in history.items() if v["e"] != edition_id}

    groups = [("briefing", config.get("briefing", []))]
    groups += [(t["key"], t["sources"]) for t in config["topics"]]
    by_topic, reports = gather(groups, offline_dir, now, edition_id)

    briefing = pick_briefing(by_topic.pop("briefing"), settings["briefing_size"], now, seen)
    main, reserve = pick(by_topic, settings, now, seen | {i.id for i in briefing})

    suggestions = config.get("suggestions", [])
    index = int(hashlib.sha1(edition_id.encode()).hexdigest(), 16) % max(len(suggestions), 1)

    payload = {
        "edition": edition_id,
        "label": edition_label,
        "built": now.isoformat(),
        "topics": [{"key": t["key"], "label": t["label"]} for t in config["topics"]],
        "briefing": [asdict(i) for i in briefing],
        "items": [asdict(i) for i in main],
        "reserve": [asdict(i) for i in reserve],
        "suggestion": suggestions[index] if suggestions else "",
        "sources": [asdict(r) for r in sorted(reports, key=lambda r: r.source)],
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=1, ensure_ascii=False))

    for item in briefing + main + reserve:
        history.setdefault(item.id, {"t": now.isoformat(), "e": edition_id})
    history_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.write_text(json.dumps(history, indent=0, sort_keys=True))
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Build one edition of Fred.")
    parser.add_argument("--config", default=ROOT / "sources.yaml", type=Path)
    parser.add_argument("--out", default=ROOT / "site" / "data.json", type=Path)
    parser.add_argument("--history", default=ROOT / "data" / "history.json", type=Path)
    parser.add_argument("--offline", type=Path, help="read feeds from saved files in this folder")
    args = parser.parse_args()

    payload = build(args.config, args.out, args.history, args.offline)
    failed = [s for s in payload["sources"] if not s["ok"]]
    print(f"{payload['label']}: {len(payload['briefing'])} briefing, "
          f"{len(payload['items'])} headlines, {len(payload['reserve'])} in reserve")
    for s in failed:
        flag = " (unverified source)" if s["verify"] else ""
        print(f"  ! {s['source']}{flag}: {s['error']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
