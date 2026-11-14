"""Checks that an edition follows the PRD's feed rules. Run: python -m pytest tests"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

from datetime import datetime, timedelta, timezone

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))
import build  # noqa: E402
import make_fixtures  # noqa: E402

SETTINGS = yaml.safe_load((ROOT / "sources.yaml").read_text())["settings"]


@pytest.fixture()
def edition(tmp_path):
    fixtures = tmp_path / "fixtures"
    make_fixtures.main(fixtures)
    out, history = tmp_path / "data.json", tmp_path / "history.json"
    payload = build.build(ROOT / "sources.yaml", out, history, fixtures)
    return payload, fixtures, out, history


def test_edition_size(edition):
    payload, *_ = edition
    assert len(payload["items"]) == SETTINGS["posts_per_batch"]
    assert len(payload["briefing"]) == SETTINGS["briefing_size"]
    assert len(payload["reserve"]) <= SETTINGS["reserve_size"]


def test_caps(edition):
    payload, *_ = edition
    topics = Counter(i["topic"] for i in payload["items"])
    sources = Counter(i["source"] for i in payload["items"])
    assert max(topics.values()) <= SETTINGS["max_per_topic"]
    assert max(sources.values()) <= SETTINGS["max_per_source"]


def test_every_topic_gets_a_turn(edition):
    payload, *_ = edition
    keys = {t["key"] for t in payload["topics"]}
    assert {i["topic"] for i in payload["items"]} == keys


def test_no_duplicates_across_sections(edition):
    payload, *_ = edition
    everything = payload["briefing"] + payload["items"] + payload["reserve"]
    assert len({i["id"] for i in everything}) == len(everything)


def test_filters(edition):
    payload, *_ = edition
    titles = [i["title"] for i in payload["items"] + payload["reserve"]]
    assert not any("SWAT" in t or "AFROTC" in t for t in titles)
    _, fixtures, *_ = edition
    config = yaml.safe_load((ROOT / "sources.yaml").read_text())
    games = next(t for t in config["topics"] if t["key"] == "games")
    src = next(s for s in games["sources"] if s["name"] == "Nintendo Life")
    nintendo = [i.title for i in build.parse(src, "games", (fixtures / "nintendo-life.xml").read_bytes())]
    assert sorted(nintendo) == ["New Pokémon Legends Trailer Drops", "Zelda Anniversary Concert Announced"]


def test_bluesky_posts_use_text_as_headline(edition):
    payload, *_ = edition
    posts = [i for i in payload["items"] + payload["reserve"] if i["kind"] == "post"]
    assert posts and all(p["title"] for p in posts)


def test_next_edition_skips_what_was_shown(edition):
    payload, fixtures, out, history = edition
    later = datetime.now(timezone.utc) + timedelta(hours=12)
    second = build.build(ROOT / "sources.yaml", out, history, fixtures, now=later)
    first_ids = {i["id"] for i in payload["briefing"] + payload["items"] + payload["reserve"]}
    second_ids = {i["id"] for i in second["briefing"] + second["items"] + second["reserve"]}
    assert not first_ids & second_ids


def test_broken_feed_does_not_break_edition(tmp_path):
    fixtures = tmp_path / "fixtures"
    make_fixtures.main(fixtures)
    (fixtures / "utility-dive.xml").write_text("not a feed at all <<<")
    payload = build.build(ROOT / "sources.yaml", tmp_path / "d.json", tmp_path / "h.json", fixtures)
    report = {s["source"]: s for s in payload["sources"]}
    assert report["Utility Dive"]["ok"] is False
    assert len(payload["items"]) == SETTINGS["posts_per_batch"]


def test_youtube_feed_skips_shorts():
    url = build.feed_url({"type": "youtube", "channel_id": "UCvjsnl6wNtVIm0i1sCpN9Uw"})
    assert url.endswith("playlist_id=UULFvjsnl6wNtVIm0i1sCpN9Uw")


def test_rebuilding_same_edition_does_not_use_up_stories(edition):
    payload, fixtures, out, history = edition
    again = build.build(ROOT / "sources.yaml", out, history, fixtures)
    assert [i["id"] for i in again["items"]] == [i["id"] for i in payload["items"]]
    assert len(again["briefing"]) == SETTINGS["briefing_size"]


def test_topic_picks_come_from_different_sources(edition):
    payload, *_ = edition
    config = yaml.safe_load((ROOT / "sources.yaml").read_text())
    available = {t["key"]: len(t["sources"]) for t in config["topics"]}
    for topic in {i["topic"] for i in payload["items"]}:
        sources = [i["source"] for i in payload["items"] if i["topic"] == topic]
        # Repeats only when a topic has fewer sources than picks (e.g. Seattle has one).
        assert len(set(sources)) == min(len(sources), available[topic]), topic
