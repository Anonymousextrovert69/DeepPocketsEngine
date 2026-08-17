"""
Deep Pockets — Daily Story Tracker
-----------------------------------
Pulls recent articles from a list of RSS feeds (Indian + global news) and
scores each ARTICLE with the tiered keyword engine, so the digest ranks
stories you could actually make a video about — not raw keyword volume.

Why article-first: keyword counts tell you "handloom was mentioned 12
times today". That is not a video. Article scoring tells you WHICH story
tripped a discovery trigger (an award win, an auction record, a celebrity
adopting a craft, a purity-test failure) and why.

Requires keyword_engine.py in the SAME directory.

Setup (one-time):
    pip install -r requirements.txt

Run:
    python deep_pockets_tracker.py                # normal run
    python deep_pockets_tracker.py --check-feeds  # validate every feed URL
    python deep_pockets_tracker.py --all          # include context-only items

Output (written to ./output/):
    - stories_YYYY-MM-DD.csv     ranked story table (score + why it ranked)
    - digest_YYYY-MM-DD.md       stories grouped by trigger family
"""

import argparse
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta

import feedparser

from keyword_engine import (
    TIER3_FAMILIES,
    clean_text,
    explain,
    score_article,
)

# Many Indian publishers 403 the default feedparser user-agent.
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 DeepPocketsTracker/1.0"
)

OUTPUT_DIR = "output"

# -----------------------------------------------------------------------
# 1. SOURCES — grouped by the job each one does in your pipeline.
#
#    Dict keys must be UNIQUE. A duplicate key silently overwrites the
#    earlier entry with no error, and you lose that feed.
#
#    Feed URLs rot. Run `--check-feeds` after any edit; delete or replace
#    anything that reports DEAD or EMPTY rather than leaving it in.
# -----------------------------------------------------------------------
RSS_FEEDS = {
    # --- TIER 1: DISCOVERY (new brands, funding, launches) ---------------
    "Inc42": "https://inc42.com/feed/",
    "Entrackr": "https://entrackr.com/feed/",
    "YourStory": "https://yourstory.com/feed",
    "ET BrandEquity": "https://brandequity.economictimes.indiatimes.com/rss/topstories",
    "ET Retail": "https://retail.economictimes.indiatimes.com/rss/topstories",
    "Storyboard18": "https://www.storyboard18.com/feed/",
    "Afaqs": "https://www.afaqs.com/rss.xml",
    "Campaign India": "https://www.campaignindia.in/rss/all",
    "Indian Retailer": "https://www.indianretailer.com/rss.rss",
    "VCCircle": "https://www.vccircle.com/feed",
    "Moneycontrol Business": "https://www.moneycontrol.com/rss/business.xml",
    "Business Standard Companies": "https://www.business-standard.com/rss/companies-101.rss",
    "Mint Companies": "https://www.livemint.com/rss/companies",
    "The Established": "https://www.theestablished.com/feed/",
    "Homegrown": "https://homegrown.co.in/feed",
    "BuzzInContent": "https://www.buzzincontent.com/feed/",

    # --- TIER 2: DEPTH / VERIFICATION ------------------------------------
    # (Ken and Morning Context are paywalled, but the headlines alone tell
    #  you what serious business desks think is worth a week of reporting.)
    "The Ken": "https://the-ken.com/feed/",
    "The Morning Context": "https://themorningcontext.com/feed",
    "Rest of World": "https://restofworld.org/feed/latest",
    "Scroll.in": "https://scroll.in/feed",
    "The Wire": "https://thewire.in/rss",
    "IndiaSpend": "https://www.indiaspend.com/stories.rss",

    # --- TIER 3: HERITAGE / CRAFT / RURAL (your moat) --------------------
    "Gaatha": "https://gaatha.com/feed/",
    "Sarmaya": "https://sarmaya.in/feed/",
    "Live History India": "https://www.livehistoryindia.com/feed/",
    "Village Square": "https://villagesquare.in/feed/",
    "Gaon Connection": "https://en.gaonconnection.com/feed/",
    "PARI": "https://ruralindiaonline.org/en/feed/",
    "The Better India": "https://www.thebetterindia.com/feed/",
    "Mongabay India": "https://india.mongabay.com/feed/",
    "The Voice of Fashion": "https://thevoiceoffashion.com/feed",
    "Architectural Digest India": "https://www.architecturaldigest.in/feed/",
    "ELLE India": "https://elle.in/feed/",
    "Tourism India Online": "https://tourismindiaonline.com/feed/",

    # --- TIER 4: POLICY / GOVERNMENT (GI tags, schemes, export data) -----
    # PIB carries Ministry of Textiles, MSME and Commerce announcements —
    # this is where GI registrations and craft-cluster schemes surface
    # first, usually weeks before anyone writes them up.
    "PIB Releases": "https://www.pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=3",
    "Bar and Bench": "https://www.barandbench.com/stories.rss",

    # --- TIER 5: OUTSIDE-IN / CROSS-DOMAIN -------------------------------
    # Low hit rate, occasional gold. Cut these first if runs get slow.
    "BBC News": "https://feeds.bbci.co.uk/news/rss.xml",
    "India Today": "https://www.indiatoday.in/rss/home",
    "TwoCircles.net": "https://twocircles.net/feed",
    "The Talented Indian": "https://www.thetalentedindian.com/feed",
    "The Whiskey Wash": "https://thewhiskeywash.com/feed/",
    "Monochrome Watches": "https://monochrome-watches.com/feed/",
    "Mongabay Global": "https://news.mongabay.com/feed/",
    "Social Media Today": "https://www.socialmediatoday.com/feeds/news/",

    # --- REMOVED (these were NOT feeds — they are HTML index pages that
    #     list feeds, so feedparser returned zero entries silently):
    #       Tribune India   https://www.tribuneindia.com/rss-feeds
    #       Onmanorama      https://www.onmanorama.com/rss.html
    #       Gadgets 360     https://www.gadgets360.com/rss
    #     Open those pages, copy the specific section feed you want, and
    #     add it back with a distinct key.
    #
    # --- ALSO REMOVED: 9to5Google, Futura Sciences — off-niche noise.
}

# -----------------------------------------------------------------------
# 2. SCORING
#
#    The old flat KEYWORDS list lived here. It is gone — all matching now
#    happens in keyword_engine.py, which holds:
#       TIER 1  core niche terms          (weight 3)
#       TIER 2  theme terms               (weight 2)
#       TIER 3  regex TRIGGER FAMILIES    (weight 2, fire once each)
#       TIER 4  context terms             (weight 1, can never surface alone)
#    Edit keywords THERE, not here.
# -----------------------------------------------------------------------

# How many days back to consider an article "recent" (RSS often mixes dates)
LOOKBACK_DAYS = 2

# Stories scoring below this are dropped even if they technically surface.
# Raise to 5-6 once you see a week of real output and want a tighter digest.
MIN_SCORE = 3

# -----------------------------------------------------------------------
# 3. AI SUMMARIZATION SETTINGS
#    Requires an Anthropic API key set as the ANTHROPIC_API_KEY env var.
#    In GitHub Actions, add it under Settings > Secrets > Actions.
#    If it's not set, the script still runs — you just get the plain
#    headline-only digest.
# -----------------------------------------------------------------------
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL = "claude-sonnet-5"
SUMMARIZE_TOP_N = 8   # only summarize the top N ranked STORIES


def parse_feed(url):
    """Fetch one feed with a browser-ish user agent."""
    return feedparser.parse(url, agent=USER_AGENT)


def check_feeds():
    """Validate every configured feed. Prints OK / EMPTY / DEAD per source
    so you can prune the list. Exits non-zero if anything is broken, which
    makes it usable as a CI step too."""
    print(f"Checking {len(RSS_FEEDS)} feeds...\n")
    broken = []
    for source, url in sorted(RSS_FEEDS.items()):
        try:
            feed = parse_feed(url)
            status = getattr(feed, "status", None)
            n = len(feed.entries)
            if n > 0:
                print(f"  OK    {source:<30} {n:>3} entries  ({status})")
            elif status and status >= 400:
                print(f"  DEAD  {source:<30} HTTP {status}  {url}")
                broken.append(source)
            else:
                print(f"  EMPTY {source:<30} 0 entries — not a feed?  {url}")
                broken.append(source)
        except Exception as e:
            print(f"  DEAD  {source:<30} {e}  {url}")
            broken.append(source)

    print()
    if broken:
        print(f"{len(broken)} feed(s) need attention: {', '.join(broken)}")
        return 1
    print("All feeds healthy.")
    return 0


def fetch_articles():
    """Pull entries from all feeds, tag with source, filter to the last
    LOOKBACK_DAYS when the feed provides a parseable date, and de-duplicate
    globally by link (the same story often syndicates across feeds).
    Entries with no date at all are kept — better to include an undated
    item than to silently drop it."""
    articles = []
    seen_links = set()
    cutoff = datetime.now() - timedelta(days=LOOKBACK_DAYS)

    for source, url in RSS_FEEDS.items():
        try:
            feed = parse_feed(url)
            if not feed.entries:
                print(f"  [!] {source}: 0 entries (run --check-feeds)")
                continue

            kept = 0
            for entry in feed.entries:
                struct = entry.get("published_parsed") or entry.get("updated_parsed")
                if struct is not None:
                    entry_dt = datetime.fromtimestamp(time.mktime(struct))
                    if entry_dt < cutoff:
                        continue  # too old

                link = entry.get("link", "")
                if link and link in seen_links:
                    continue  # already have this story from another feed
                if link:
                    seen_links.add(link)

                # clean_text() strips HTML tags AND unescapes entities.
                # feedparser summaries arrive as HTML; matching raw HTML
                # fails silently, which is how &amp;-mangled text used to
                # slip past the keyword patterns.
                title = clean_text(entry.get("title", ""))
                summary = clean_text(
                    entry.get("summary", "") or entry.get("description", "")
                )

                articles.append({
                    "source": source,
                    "title": title,
                    "summary": summary,
                    "link": link,
                })
                kept += 1
            print(f"  {source:<30} {kept:>3} recent")
        except Exception as e:
            print(f"  [!] Could not fetch {source}: {e}")

    return articles


def score_all(articles, include_all=False):
    """Score every article with the tiered engine.

    Returns (stories, family_counts):
      stories        list of article dicts + score/reason/families,
                     sorted best-first
      family_counts  how many stories each TIER 3 trigger family fired on
                     — this is your 'what kind of story is in the air today'
                     signal, and it replaces the old keyword frequency table
    """
    stories = []
    family_counts = defaultdict(int)

    for art in articles:
        result = score_article(art["title"], art["summary"])

        if not include_all:
            if not result["surfaces"] or result["score"] < MIN_SCORE:
                continue

        families = [e["family"] for e in result["matched"]["tier3"]]
        for fam in families:
            family_counts[fam] += 1

        stories.append({
            **art,
            "score": result["score"],
            "reason": explain(result),
            "families": families,
            "core": result["matched"]["tier1"],
        })

    stories.sort(key=lambda s: (s["score"], len(s["families"])), reverse=True)
    return stories, family_counts


def summarize_story(story):
    """Send one story to Claude and get back a short 'what's actually
    happening' read plus a video-angle verdict. Returns None if no API key
    is configured or the call fails — callers fall back to headline only."""
    if not ANTHROPIC_API_KEY:
        return None

    trigger_note = ", ".join(story["families"]) or "core keyword match"

    prompt = (
        f"This story surfaced in a daily tracker for a YouTube channel "
        f"(Deep Pockets) about Indian heritage, crafts and brands with global "
        f"potential — specifically India's value-capture gaps, where India "
        f"makes something but another country or brand captures the global "
        f"brand value.\n\n"
        f"Source: {story['source']}\n"
        f"Headline: {story['title']}\n"
        f"Snippet: {story['summary'][:400]}\n"
        f"Tracker trigger: {trigger_note}\n\n"
        f"In under 80 words total:\n"
        f"1) What is actually being reported here — the real event, deal, "
        f"launch, dispute or data point.\n"
        f"2) One line on whether this is a Deep Pockets video angle and what "
        f"the angle would be, or say 'Not a strong fit' if it is off-niche.\n"
        f"Be honest about weak stories. Plain text, no headers, no markdown."
    )

    body = json.dumps({
        "model": ANTHROPIC_MODEL,
        "max_tokens": 300,
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=body,
        headers={
            "Content-Type": "application/json",
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        parts = [b["text"] for b in data.get("content", []) if b.get("type") == "text"]
        return "".join(parts).strip() or None
    except (urllib.error.URLError, urllib.error.HTTPError, KeyError, ValueError) as e:
        print(f"  [!] Summarization failed for '{story['title'][:40]}': {e}")
        return None


def print_report(stories, family_counts):
    print("\n" + "=" * 78)
    print(f"  DEEP POCKETS — STORY TRACKER — {datetime.now().date()}")
    print("=" * 78)

    if not stories:
        print("No stories cleared the bar today.")
        print("This is NORMAL on a quiet day — the engine only surfaces items")
        print("with a core-niche or trigger-family hit. If it stays empty for")
        print("several days: lower MIN_SCORE, raise LOOKBACK_DAYS, or run")
        print("--check-feeds to confirm the feeds are alive.")
        return

    if family_counts:
        print("\nTRIGGERS FIRING TODAY")
        print("-" * 78)
        for fam, n in sorted(family_counts.items(), key=lambda x: -x[1]):
            why = TIER3_FAMILIES[fam]["why"]
            print(f"  {n:>2}x  {fam:<22} {why}")

    print("\nTOP STORIES")
    print("-" * 78)
    for i, s in enumerate(stories[:25], 1):
        print(f"{i:>3}. [{s['score']:>2}] {s['title'][:66]}")
        print(f"      {s['source']} — {s['reason'][:70]}")
    if len(stories) > 25:
        print(f"\n  ...and {len(stories) - 25} more in the CSV.")
    print("=" * 78 + "\n")


def save_csv(stories, date_str):
    fname = os.path.join(OUTPUT_DIR, f"stories_{date_str}.csv")
    with open(fname, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Rank", "Score", "Title", "Source", "Triggers",
            "CoreTerms", "Why", "Link",
        ])
        for i, s in enumerate(stories, 1):
            writer.writerow([
                i, s["score"], s["title"], s["source"],
                "|".join(s["families"]),
                "|".join(s["core"]),
                s["reason"],
                s["link"],
            ])
    print(f"Saved: {fname}")


def save_digest(stories, family_counts, summaries, date_str):
    fname = os.path.join(OUTPUT_DIR, f"digest_{date_str}.md")
    with open(fname, "w", encoding="utf-8") as f:
        f.write(f"# Deep Pockets — Story Digest — {date_str}\n\n")
        f.write(
            f"Sources scanned: {len(RSS_FEEDS)} | "
            f"Lookback: {LOOKBACK_DAYS} days | "
            f"Stories surfaced: {len(stories)}\n\n"
        )

        if family_counts:
            f.write("## Triggers firing today\n\n")
            for fam, n in sorted(family_counts.items(), key=lambda x: -x[1]):
                f.write(f"- **{fam}** ({n}) — {TIER3_FAMILIES[fam]['why']}\n")
            f.write("\n---\n\n")

        # Group by trigger family so you read by story TYPE, not by source.
        by_family = defaultdict(list)
        for s in stories:
            if s["families"]:
                for fam in s["families"]:
                    by_family[fam].append(s)
            else:
                by_family["_core_only"].append(s)

        ordered = sorted(
            by_family.items(),
            key=lambda kv: (kv[0] == "_core_only", -len(kv[1])),
        )

        for fam, items in ordered:
            if fam == "_core_only":
                f.write("## Core keyword matches (no trigger fired)\n\n")
                f.write("_Niche-relevant, but no discovery event attached._\n\n")
            else:
                f.write(f"## {fam} — {TIER3_FAMILIES[fam]['why']}\n\n")

            for s in items:
                f.write(f"### [{s['score']}] {s['title']}\n")
                f.write(f"*{s['source']}* — {s['link']}\n\n")
                f.write(f"`{s['reason']}`\n\n")
                note = summaries.get(s["link"])
                if note:
                    f.write(f"**Read:** {note}\n\n")
            f.write("\n")
    print(f"Saved: {fname}")


def main():
    parser = argparse.ArgumentParser(description="Deep Pockets story tracker")
    parser.add_argument("--check-feeds", action="store_true",
                        help="Validate every feed URL and exit")
    parser.add_argument("--all", action="store_true",
                        help="Include low-signal/context-only articles too")
    args = parser.parse_args()

    if args.check_feeds:
        sys.exit(check_feeds())

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print(f"Fetching from {len(RSS_FEEDS)} RSS feeds...")
    articles = fetch_articles()
    print(f"\nFetched {len(articles)} unique recent articles.")

    stories, family_counts = score_all(articles, include_all=args.all)
    print_report(stories, family_counts)

    date_str = str(datetime.now().date())
    if not stories:
        return

    save_csv(stories, date_str)

    summaries = {}
    if ANTHROPIC_API_KEY:
        print("Generating AI reads for top stories...")
        for s in stories[:SUMMARIZE_TOP_N]:
            print(f"  Reading '{s['title'][:50]}'...")
            note = summarize_story(s)
            if note:
                summaries[s["link"]] = note
    else:
        print("  [i] ANTHROPIC_API_KEY not set — skipping AI reads, "
              "digest will show headlines only.")

    save_digest(stories, family_counts, summaries, date_str)


if __name__ == "__main__":
    main()
