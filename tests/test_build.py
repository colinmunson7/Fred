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


def news(items):
    """Everything except picks shown on top of the caps (Wikipedia)."""
    return [i for i in items if i["kind"] != "wikipedia"]


def test_edition_size(edition):
    payload, *_ = edition
    assert len(news(payload["items"])) == SETTINGS["posts_per_batch"]
    assert len(payload["briefing"]) == SETTINGS["briefing_size"]
    assert len(payload["reserve"]) <= SETTINGS["reserve_size"]


def test_caps(edition):
    payload, *_ = edition
    topics = Counter(i["topic"] for i in news(payload["items"]))
    sources = Counter(i["source"] for i in news(payload["items"]))
    config = yaml.safe_load((ROOT / "sources.yaml").read_text())
    caps = {t["key"]: t.get("max", SETTINGS["max_per_topic"]) for t in config["topics"]}
    assert all(n <= caps[t] for t, n in topics.items())
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
    assert len(news(payload["items"])) == SETTINGS["posts_per_batch"]


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


def test_puzzles_always_has_a_daily_game(edition):
    payload, *_ = edition
    games = [i for i in payload["items"] if i["kind"] == "game"]
    assert len(games) == 1 and games[0]["topic"] == "puzzles"


def test_videos_section_is_youtube_only(edition):
    payload, *_ = edition
    vids = [i for i in payload["items"] + payload["reserve"] if i["topic"] == "videos"]
    assert vids and all(i["kind"] == "video" for i in vids)
    assert all(i["topic"] == "videos" for i in payload["items"] + payload["reserve"] if i["kind"] == "video")


def test_slow_sources_still_get_in(tmp_path):
    """A weekly blog's latest post should beat a busy site's fourth story."""
    now = datetime.now(timezone.utc)
    def it(n, src, hours):
        return build.Item(f"{src}{n}", f"{src} story {n}", f"https://x/{src}/{n}", src, "dnd", "article",
                          (now - timedelta(hours=hours)).isoformat())
    busy = [it(n, "EN World", n) for n in range(1, 10)]
    weekly = [it(1, "Sly Flourish", 24 * 5)]
    picked = build.fresh_by_source(busy + weekly, SETTINGS, now, set())
    assert any(i.source == "Sly Flourish" for i in picked)


def test_happening_now_takes_live_blogs_out_of_the_briefing(edition):
    payload, *_ = edition
    assert [i["title"] for i in payload["happening"]] == ["Live updates: Storm makes landfall on the Gulf Coast"]
    assert all(not i["title"].lower().startswith("live updates") for i in payload["briefing"])
    assert payload["happening"][0]["kind"] == "live"


def test_wikipedia_picks_sit_on_top_of_the_puzzles_cap(edition):
    payload, *_ = edition
    puzzles = [i for i in payload["items"] if i["topic"] == "puzzles"]
    wiki = [i for i in puzzles if i["kind"] == "wikipedia"]
    assert len(wiki) == 3
    assert len(puzzles) - len(wiki) <= SETTINGS["max_per_topic"]


def test_bluesky_has_its_own_section(edition):
    payload, *_ = edition
    posts = [i for i in payload["items"] + payload["reserve"] if i["kind"] == "post"]
    assert posts and all(i["topic"] == "bluesky" for i in posts)
    config = yaml.safe_load((ROOT / "sources.yaml").read_text())
    cap = next(t["max"] for t in config["topics"] if t["key"] == "bluesky")
    assert sum(1 for i in payload["items"] if i["topic"] == "bluesky") <= cap


def test_money_mixes_live_posts_and_archive_picks(edition):
    payload, *_ = edition
    money = [i for i in payload["items"] + payload["reserve"] if i["topic"] == "money"]
    kinds = {i["source"]: i["kind"] for i in money}
    assert kinds.get("Get Rich Slowly") == "archive"
    assert kinds.get("The Evidence-Based Investor") == "archive"
    titles = [i["title"] for i in payload["items"] + payload["reserve"] if i["source"] == "A Wealth of Common Sense"]
    assert titles and not any("Animal Spirits" in t or "Talk Your Book" in t for t in titles)


def test_backup_run_skips_an_edition_already_built(edition):
    payload, fixtures, out, history = edition
    assert build.build(ROOT / "sources.yaml", out, history, fixtures, skip_if_built=True) is None
    later = datetime.now(timezone.utc) + timedelta(hours=12)
    assert build.build(ROOT / "sources.yaml", out, history, fixtures, now=later, skip_if_built=True) is not None
