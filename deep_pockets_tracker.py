"""
Deep Pockets — Daily Keyword Trend Tracker
--------------------------------------------
Pulls today's articles from a list of RSS feeds (Indian + global news),
scans headlines/summaries for your niche keywords, and ranks them by
frequency (descending) — with the actual headlines/links behind each hit,
so you can go straight from "trending keyword" to "video idea".

Setup (one-time):
    pip install feedparser --break-system-packages

Run:
    python deep_pockets_tracker.py

Output:
    - Prints a ranked keyword table to the terminal
    - Saves a CSV: trend_report_YYYY-MM-DD.csv
    - Saves a readable digest: digest_YYYY-MM-DD.md (headlines grouped by keyword)
"""

import feedparser
from collections import defaultdict
from datetime import datetime, timedelta
import csv
import re
import time
import os
import json
import urllib.request
import urllib.error

# -----------------------------------------------------------------------
# 1. CONFIGURE YOUR SOURCES — add/remove RSS feeds freely
#    NOTE: dict keys must be unique. If you paste in a source name that
#    already exists, Python will silently overwrite the first one and
#    you'll lose that feed without any error. Give each entry a distinct
#    name if two feeds happen to share a source name.
# -----------------------------------------------------------------------
RSS_FEEDS = {
    "Bar and Bench": "https://www.barandbench.com/stories.rss",
    "Tribune India": "https://www.tribuneindia.com/rss-feeds",
    "9to5Google": "https://9to5google.com/feed",
    "Onmanorama": "https://www.onmanorama.com/rss.html",
    "The Talented Indian": "https://www.thetalentedindian.com/feed",
    "Gadgets 360": "https://www.gadgets360.com/rss",
    "BBC News": "https://feeds.bbci.co.uk/news/rss.xml",
    "Mongabay": "https://news.mongabay.com/feed/",
    "Storyboard18": "https://www.storyboard18.com/feed/",
    "Tourism India Online": "https://tourismindiaonline.com/feed/",
    "TwoCircles.net": "https://twocircles.net/feed",
    "The Better India": "https://www.thebetterindia.com/feed/",
    "The Whiskey Wash": "https://thewhiskeywash.com/feed/",
    "Homegrown": "https://homegrown.co.in/feed",
    "BuzzInContent": "https://www.buzzincontent.com/feed/",
    "Social Media Today": "https://www.socialmediatoday.com/feeds/news/",
    "India Today": "https://www.indiatoday.in/rss/home",
    "Architectural Digest India": "https://www.architecturaldigest.in/feed/",
    "The Established": "https://www.theestablished.com/feed/",
    "Monochrome Watches": "https://monochrome-watches.com/feed/",
    "Futura Sciences": "https://www.futura-sciences.com/en/rss/news.xml",
    "ELLE India": "https://elle.in/feed/",
}

KEYWORDS = [
    "Indian Heritage",
    "cultural revival",
    "Traditional Crafts",
    "Indian Artisans",
    "embroidery",
    "Brand Storytelling",
    "founder stories",
    "identity design",
    "Design Innovation",
    "packaging",
    "product design",
    "Consumer Psychology",
    "Buying behavior",
    "perception",
    "Indian Startups",
    "consumer brands",
    "manufacturing",
    "D2C Brands",
    "Factories",
    "Make in India",
    "production innovation",
    "Entrepreneurship",
    "Founders",
    "business creation",
    "scaling",
    "Cultural Entrepreneurship",
    "Businesses built around culture",
    "heritage business",
    "Craft Revival",
    "Modern revival",
    "dying crafts",
    "Sustainable Materials",
    "Natural fibres",
    "eco materials",
    "biomaterials",
    "Circular Economy",
    "Waste-to-value",
    "Rural Innovation",
    "Grassroots innovation",
    "Indigenous Technology",
    "Traditional techniques",
    "modern technology",
    "Packaging Innovation",
    "Premiumization",
    "Retail Trends",
    "Consumer retail",
    "retail shifts",
    "Luxury India",
    "Indian premium brands",
    "Made in India",
    "global recognition",
    "Export Growth",
    "Indian exports",
    "international markets",
    "Geographical Indications",
    "GI Tags",
    "GI registration",
    "GI commercialization",
    "Food Innovation",
    "Traditional foods",
    "food brands",
    "Fashion Innovation",
    "Textiles",
    "heritage fabrics",
    "fashion designers",
    "Consumer Trends",
    "Lifestyle shifts",
    "Marketing Campaigns",
    "Creative campaigns",
    "Creator Economy",
    "Personal brands",
    "media businesses",
    "Business Models",
    "distribution",
    "pricing",
    "monetization",
    "Future of Work",
    "India Innovation",
    "Technology",
    "research",
    "patents",
    "deep tech",
]

# How many days back to consider an article "recent" (RSS often mixes dates)
LOOKBACK_DAYS = 2

# -----------------------------------------------------------------------
# 3. AI SUMMARIZATION SETTINGS
#    Turns a pile of matched headlines into an actual "what's happening
#    and why it could be a video" summary, instead of just a link list.
#    Requires an Anthropic API key (console.anthropic.com) set as the
#    ANTHROPIC_API_KEY environment variable. If it's not set, the script
#    still runs fine — you just get the old headline-only digest.
# -----------------------------------------------------------------------
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL = "claude-sonnet-5"
SUMMARIZE_TOP_N_KEYWORDS = 15   # only summarize the top N ranked keywords, to control API cost
SUMMARIZE_MIN_MENTIONS = 2      # skip summarizing keywords with fewer mentions than this
MAX_ARTICLES_PER_SUMMARY = 8    # cap how many headlines get sent per keyword


def fetch_articles():
    """Pull entries from all feeds, tag with source, and filter to the
    last LOOKBACK_DAYS days when the feed provides a parseable date.
    If a feed entry has no date at all, it's kept (better to include an
    undated item than to silently drop it)."""
    articles = []
    cutoff = datetime.now() - timedelta(days=LOOKBACK_DAYS)

    for source, url in RSS_FEEDS.items():
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                # feedparser exposes parsed dates as time.struct_time via
                # published_parsed / updated_parsed when it can figure
                # the format out. Fall back gracefully when it can't.
                struct = entry.get("published_parsed") or entry.get("updated_parsed")
                if struct is not None:
                    entry_dt = datetime.fromtimestamp(time.mktime(struct))
                    if entry_dt < cutoff:
                        continue  # too old, skip it

                title = entry.get("title", "")
                summary = entry.get("summary", "") or entry.get("description", "")
                link = entry.get("link", "")
                articles.append({
                    "source": source,
                    "title": title,
                    "summary": summary,
                    "link": link,
                    "text": f"{title} {summary}".lower(),
                })
        except Exception as e:
            print(f"  [!] Could not fetch {source}: {e}")

    return articles


def count_keywords(articles):
    """Count keyword frequency across all articles, and keep matching articles."""
    counts = defaultdict(int)
    matches = defaultdict(list)

    for kw in KEYWORDS:
        pattern = re.compile(re.escape(kw), re.IGNORECASE)
        for art in articles:
            hits = len(pattern.findall(art["text"]))
            if hits:
                counts[kw] += hits
                matches[kw].append(art)

    return counts, matches


def summarize_keyword_trend(keyword, articles):
    """Send the matched headlines for one keyword to Claude and get back
    a short 'what's actually happening' summary plus a suggested video
    angle. Returns None if no API key is configured or the call fails —
    callers should fall back to the plain headline list in that case."""
    if not ANTHROPIC_API_KEY:
        return None

    # Dedup by link, cap how many we send
    seen_links = set()
    unique_articles = []
    for art in articles:
        if art["link"] in seen_links:
            continue
        seen_links.add(art["link"])
        unique_articles.append(art)
        if len(unique_articles) >= MAX_ARTICLES_PER_SUMMARY:
            break

    headlines_block = "\n".join(
        f"- [{a['source']}] {a['title']}: {a['summary'][:200]}"
        for a in unique_articles
    )

    prompt = (
        f"These are today's news headlines/snippets that mention \"{keyword}\", "
        f"collected for a YouTube channel (Deep Pockets) about India's branding and "
        f"value-capture gaps in global markets (e.g. India creates a product/craft/"
        f"resource but another country or brand captures the global value from it).\n\n"
        f"{headlines_block}\n\n"
        f"In under 80 words total, do two things:\n"
        f"1) Summarize what is actually being reported about \"{keyword}\" today — "
        f"the real event, deal, launch, dispute, or trend driving these headlines.\n"
        f"2) One line suggesting whether/how this could become a Deep Pockets video "
        f"angle, or say 'Not a strong fit' if it's off-niche.\n"
        f"Plain text, no headers, no markdown."
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
        text_parts = [block["text"] for block in data.get("content", []) if block.get("type") == "text"]
        return "".join(text_parts).strip() or None
    except (urllib.error.URLError, urllib.error.HTTPError, KeyError, ValueError) as e:
        print(f"  [!] Summarization failed for '{keyword}': {e}")
        return None


def print_report(counts):
    print("\n" + "=" * 55)
    print(f"  DEEP POCKETS — TREND REPORT — {datetime.now().date()}")
    print("=" * 55)
    ranked = sorted(counts.items(), key=lambda x: x[1], reverse=True)
    if not ranked:
        print("No keyword matches found today. Try widening LOOKBACK_DAYS or keywords.")
        return ranked
    for i, (kw, count) in enumerate(ranked, 1):
        print(f"{i:>2}. {kw:<28} {count} mention(s)")
    print("=" * 55 + "\n")
    return ranked


def save_csv(ranked, date_str):
    fname = f"trend_report_{date_str}.csv"
    with open(fname, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Rank", "Keyword", "Mentions"])
        for i, (kw, count) in enumerate(ranked, 1):
            writer.writerow([i, kw, count])
    print(f"Saved: {fname}")


def save_digest(ranked, matches, summaries, date_str):
    fname = f"digest_{date_str}.md"
    with open(fname, "w", encoding="utf-8") as f:
        f.write(f"# Deep Pockets — Trend Digest — {date_str}\n\n")
        for kw, count in ranked:
            f.write(f"## {kw} ({count} mentions)\n\n")
            summary = summaries.get(kw)
            if summary:
                f.write(f"**What's happening:** {summary}\n\n")
            seen_links = set()
            for art in matches[kw]:
                if art["link"] in seen_links:
                    continue
                seen_links.add(art["link"])
                f.write(f"- **{art['title']}** — *{art['source']}*\n  {art['link']}\n")
            f.write("\n")
    print(f"Saved: {fname}")


def main():
    print("Fetching articles from RSS feeds...")
    articles = fetch_articles()
    print(f"Fetched {len(articles)} articles from {len(RSS_FEEDS)} sources.")

    counts, matches = count_keywords(articles)
    ranked = print_report(counts)

    date_str = str(datetime.now().date())
    if not ranked:
        return

    save_csv(ranked, date_str)

    summaries = {}
    if ANTHROPIC_API_KEY:
        print("Generating AI summaries for top trending keywords...")
        to_summarize = [
            (kw, count) for kw, count in ranked[:SUMMARIZE_TOP_N_KEYWORDS]
            if count >= SUMMARIZE_MIN_MENTIONS
        ]
        for kw, count in to_summarize:
            print(f"  Summarizing '{kw}' ({count} mentions)...")
            summaries[kw] = summarize_keyword_trend(kw, matches[kw])
    else:
        print("  [i] ANTHROPIC_API_KEY not set — skipping AI summaries, "
              "digest will show headlines only.")

    save_digest(ranked, matches, summaries, date_str)


if __name__ == "__main__":
    main()
