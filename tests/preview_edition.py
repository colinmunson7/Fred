"""Builds a preview edition from real headlines seen while checking feeds on
2026-11-14. Links point at each source's homepage because the article links
weren't collected. Used only for the phone preview, not by the live site."""
import json
import sys
from pathlib import Path

E = [  # (topic, source, kind, title, link, published UTC)
    ("briefing", "NPR News", "article", "Alaska voters aren't ditching ranked choice voting, top-four primaries", "https://www.npr.org/", "2026-11-14T13:08:05+00:00"),
    ("climate", "Utility Dive", "article", "Utility, tech officials see opportunities to increase grid utilization", "https://www.utilitydive.com/", "2026-11-13T17:26:00+00:00"),
    ("climate", "Utility Dive", "article", "What's next for California's climate laws following an appeals court split decision", "https://www.utilitydive.com/", "2026-11-13T17:00:00+00:00"),
    ("climate", "Smart Cities Dive", "article", "The best large US cities for biking in 2026: PeopleForBikes", "https://www.smartcitiesdive.com/", "2026-11-13T16:43:00+00:00"),
    ("climate", "The Urbanist", "article", "Shoreline Pedestrian Bridge Defect Jeopardizes Already Delayed Timeline", "https://www.theurbanist.org/", "2026-11-13T22:59:31+00:00"),
    ("climate", "Seattle Transit Blog", "article", "Friday Roundtable: Cascadia High-Speed Rail and I-5", "https://seattletransitblog.com/", "2026-11-13T13:52:00+00:00"),
    ("outdoors", "Uphill Athlete", "article", "Dr. Stephen Seiler on Intensity, Rest, and the Mountain Athlete", "https://uphillathlete.com/", "2026-11-12T16:00:00+00:00"),
    ("outdoors", "Seattle Bike Blog", "article", "County will create temporary bike lane during U Bridge trolley wire work", "https://www.seattlebikeblog.com/", "2026-11-13T22:17:54+00:00"),
    ("outdoors", "Mountain Tactical Institute", "article", "New to MTI Nutrition: Simple Daily Meals Without Macro Complexity", "https://mtntactical.com/", "2026-11-11T14:09:28+00:00"),
    ("outdoors", "Uphill Athlete", "article", "How To Train for Two Mountain Sports at Once", "https://uphillathlete.com/", "2026-11-05T16:00:00+00:00"),
    ("dnd", "EN World", "article", "News Digest for November 14, 2026", "https://www.enworld.org/", "2026-11-14T06:10:00+00:00"),
    ("dnd", "EN World", "article", "World of Warcraft Deep Dive - Elves", "https://www.enworld.org/", "2026-11-14T11:56:00+00:00"),
    ("games", "PokéCommunity: ROM Hacks", "article", "POKEMON: Dark Rising", "https://www.pokecommunity.com/forums/progressing-rom-hacks-showcase.67/", "2026-11-14T12:50:02+00:00"),
    ("games", "PokéCommunity: Challenges", "article", "The Monotype Challenge v8, Tera Edition", "https://www.pokecommunity.com/forums/202/", "2026-11-14T15:02:54+00:00"),
    ("games", "Stardew Valley", "article", "Galaxy Sword replica now available from Fire & Steel!", "https://www.stardewvalley.net/", "2026-11-13T18:25:30+00:00"),
    ("games", "PokéCommunity: Challenges", "article", "The \"No Evolution\" Challenge", "https://www.pokecommunity.com/forums/202/", "2026-11-14T09:40:00+00:00"),
    ("sports", "The Equalizer", "article", "Temwa Chawinga should be the NWSL Most Valuable Player.", "https://equalizersoccer.com/", "2026-11-14T14:00:00+00:00"),
    ("sports", "ESPN NFL", "article", "Our guide to every Week 10 game: Matchup previews, predictions, picks and nuggets", "https://www.espn.com/nfl/", "2026-11-14T03:01:45+00:00"),
    ("sports", "Uni Watch", "article", "Welcome to \"Ask Me Anything\"", "https://www.uni-watch.com/", "2026-11-09T14:45:57+00:00"),
    ("local", "PubliCola", "article", "City Council Fails to Override Mayor's Veto of Proposed RV Ban", "https://publicola.com/", "2026-11-13T00:05:15+00:00"),
    ("clothing", "Put This On", "article", "Inside Track: November 1st – November 7th Edition", "https://putthison.com/", "2026-11-10T07:51:24+00:00"),
    ("other", "Diary of a Crossword Fiend", "article", "Saturday, November 14, 2026", "https://www.crosswordfiend.com/", "2026-11-14T04:42:34+00:00"),
    ("other", "Bogle Center", "article", "Bogleheads® on Investing with David Booth, co-founder & chairman of Dimensional Fund Advisors: Episode 99", "https://boglecenter.net/", "2026-10-20T16:00:00+00:00"),
    ("humor", "The Onion", "post", "Customer Service Discloses Call Will Be Monitored For Sadistic Amusement", "https://bsky.app/profile/theonion.com", "2026-11-14T16:00:00+00:00"),
    ("climate", "The Urbanist", "article", "Bellevue Council Settles On 10-Year Transportation Funding Plan", "https://www.theurbanist.org/", "2026-11-12T23:56:29+00:00"),
]

TOPICS = [("climate", "Climate & Clean Energy"), ("outdoors", "Outdoors"), ("dnd", "D&D"),
          ("games", "Video Games"), ("sports", "Sports"), ("local", "Seattle"),
          ("clothing", "Clothing"), ("other", "Money & Puzzles"), ("humor", "Humor")]


def item(n, row):
    topic, source, kind, title, link, when = row
    return {"id": f"p{n}", "title": title, "link": link, "source": source, "topic": topic,
            "kind": kind, "published": when, "score": None}


rows = [item(n, r) for n, r in enumerate(E)]
data = {
    "edition": "preview-2026-11-14",
    "label": "Morning edition · Saturday, November 14",
    "built": "2026-11-14T16:30:00+00:00",
    "preview": "Preview: real headlines collected while checking feeds on Nov 14, linking to each source's homepage. "
               "The live Fred fills every section with about 25 fresh stories, a full news briefing, Bluesky posts and YouTube videos.",
    "topics": [{"key": k, "label": l} for k, l in TOPICS],
    "briefing": [r for r in rows if r["topic"] == "briefing"],
    "items": [r for r in rows if r["topic"] != "briefing"],
    "reserve": [],
    "suggestion": "Clean something",
    "sources": [],
}
Path(sys.argv[1]).write_text(json.dumps(data, indent=1, ensure_ascii=False))
print(f"{len(data['items'])} items")
