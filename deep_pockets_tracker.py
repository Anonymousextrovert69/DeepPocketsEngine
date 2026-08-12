"""
Deep Pockets — Daily Keyword Trend Tracker
--------------------------------------------
Pulls recent articles from a list of RSS feeds (Indian + global news),
scans headlines/summaries for your niche keywords, and ranks them by how
many DISTINCT articles mention them — with the actual headlines/links
behind each hit, so you can go straight from "trending keyword" to
"video idea".

Setup (one-time):
    pip install -r requirements.txt

Run:
    python deep_pockets_tracker.py                # normal run
    python deep_pockets_tracker.py --check-feeds  # validate every feed URL

Output (written to ./output/):
    - trend_report_YYYY-MM-DD.csv   ranked keyword table
    - digest_YYYY-MM-DD.md          headlines grouped by keyword
"""

import argparse
import csv
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta

import feedparser

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

KEYWORDS = [
    "Indian Heritage",
    "cultural revival",
    "Traditional Crafts",
    "Indian Artisans",
    "artisan",
    "handloom",
    "handicraft",
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
    "D2C",
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
    "GI Tag",
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

# Broad words that will always top the chart on volume alone and drown out
# the signal. They still get counted and reported, just pushed below the
# specific terms in the ranking.
GENERIC_KEYWORDS = {
    "Technology", "research", "manufacturing", "packaging", "perception",
    "scaling", "distribution", "pricing", "Founders", "Textiles",
    "monetization", "product design",
}
GENERIC_WEIGHT = 0.3

# How many days back to consider an article "recent" (RSS often mixes dates)
LOOKBACK_DAYS = 2

# -----------------------------------------------------------------------
# 3. AI SUMMARIZATION SETTINGS
#    Requires an Anthropic API key set as the ANTHROPIC_API_KEY env var.
#    In GitHub Actions, add it under Settings > Secrets > Actions.
#    If it's not set, the script still runs — you just get the plain
#    headline-only digest.
# -----------------------------------------------------------------------
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL = "claude-sonnet-5"
SUMMARIZE_TOP_N_KEYWORDS = 15   # only summarize the top N ranked keywords
SUMMARIZE_MIN_ARTICLES = 2      # skip keywords with fewer distinct articles
MAX_ARTICLES_PER_SUMMARY = 8    # cap how many headlines get sent per keyword


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

                title = entry.get("title", "")
                summary = entry.get("summary", "") or entry.get("description", "")
                # Strip HTML tags out of summaries so they don't pollute matches
                summary = re.sub(r"<[^>]+>", " ", summary)

                articles.append({
                    "source": source,
                    "title": title,
                    "summary": summary,
                    "link": link,
                    "text": f"{title} {summary}".lower(),
                })
                kept += 1
            print(f"  {source:<30} {kept:>3} recent")
        except Exception as e:
            print(f"  [!] Could not fetch {source}: {e}")

    return articles


def count_keywords(articles):
    """For each keyword, record how many DISTINCT articles mention it and
    how many total mentions there were. Ranking on distinct articles stops
    one repetitive article from faking a trend."""
    article_counts = defaultdict(int)
    mention_counts = defaultdict(int)
    matches = defaultdict(list)

    for kw in KEYWORDS:
        # \b word boundaries stop "Technology" matching inside "biotechnology"
        pattern = re.compile(r"\b" + re.escape(kw) + r"\b", re.IGNORECASE)
        for art in articles:
            hits = len(pattern.findall(art["text"]))
            if hits:
                article_counts[kw] += 1
                mention_counts[kw] += hits
                matches[kw].append(art)

    return article_counts, mention_counts, matches


def rank_keywords(article_counts, mention_counts):
    """Sort by weighted distinct-article count, then raw mentions."""
    def score(kw):
        weight = GENERIC_WEIGHT if kw in GENERIC_KEYWORDS else 1.0
        return article_counts[kw] * weight

    return sorted(
        article_counts.keys(),
        key=lambda kw: (score(kw), mention_counts[kw]),
        reverse=True,
    )


def summarize_keyword_trend(keyword, articles):
    """Send the matched headlines for one keyword to Claude and get back a
    short 'what's actually happening' summary plus a suggested video angle.
    Returns None if no API key is configured or the call fails — callers
    fall back to the plain headline list."""
    if not ANTHROPIC_API_KEY:
        return None

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
        text_parts = [b["text"] for b in data.get("content", []) if b.get("type") == "text"]
        return "".join(text_parts).strip() or None
    except (urllib.error.URLError, urllib.error.HTTPError, KeyError, ValueError) as e:
        print(f"  [!] Summarization failed for '{keyword}': {e}")
        return None


def print_report(ranked, article_counts, mention_counts):
    print("\n" + "=" * 68)
    print(f"  DEEP POCKETS — TREND REPORT — {datetime.now().date()}")
    print("=" * 68)
    if not ranked:
        print("No keyword matches. Widen LOOKBACK_DAYS, or run --check-feeds.")
        return
    print(f"{'#':>3}  {'KEYWORD':<30} {'ARTICLES':>8} {'MENTIONS':>9}")
    print("-" * 68)
    for i, kw in enumerate(ranked, 1):
        tag = " (broad)" if kw in GENERIC_KEYWORDS else ""
        print(f"{i:>3}. {kw + tag:<30} {article_counts[kw]:>8} {mention_counts[kw]:>9}")
    print("=" * 68 + "\n")


def save_csv(ranked, article_counts, mention_counts, date_str):
    fname = os.path.join(OUTPUT_DIR, f"trend_report_{date_str}.csv")
    with open(fname, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Rank", "Keyword", "Articles", "Mentions", "Broad"])
        for i, kw in enumerate(ranked, 1):
            writer.writerow([
                i, kw, article_counts[kw], mention_counts[kw],
                "yes" if kw in GENERIC_KEYWORDS else "no",
            ])
    print(f"Saved: {fname}")


def save_digest(ranked, article_counts, matches, summaries, date_str):
    fname = os.path.join(OUTPUT_DIR, f"digest_{date_str}.md")
    with open(fname, "w", encoding="utf-8") as f:
        f.write(f"# Deep Pockets — Trend Digest — {date_str}\n\n")
        f.write(f"Sources scanned: {len(RSS_FEEDS)} | Lookback: {LOOKBACK_DAYS} days\n\n")
        for kw in ranked:
            f.write(f"## {kw} ({article_counts[kw]} articles)\n\n")
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
    parser = argparse.ArgumentParser(description="Deep Pockets trend tracker")
    parser.add_argument("--check-feeds", action="store_true",
                        help="Validate every feed URL and exit")
    args = parser.parse_args()

    if args.check_feeds:
        sys.exit(check_feeds())

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print(f"Fetching from {len(RSS_FEEDS)} RSS feeds...")
    articles = fetch_articles()
    print(f"\nFetched {len(articles)} unique recent articles.")

    article_counts, mention_counts, matches = count_keywords(articles)
    ranked = rank_keywords(article_counts, mention_counts)
    print_report(ranked, article_counts, mention_counts)

    date_str = str(datetime.now().date())
    if not ranked:
        return

    save_csv(ranked, article_counts, mention_counts, date_str)

    summaries = {}
    if ANTHROPIC_API_KEY:
        print("Generating AI summaries for top trending keywords...")
        to_summarize = [
            kw for kw in ranked[:SUMMARIZE_TOP_N_KEYWORDS]
            if article_counts[kw] >= SUMMARIZE_MIN_ARTICLES
        ]
        for kw in to_summarize:
            print(f"  Summarizing '{kw}' ({article_counts[kw]} articles)...")
            summaries[kw] = summarize_keyword_trend(kw, matches[kw])
    else:
        print("  [i] ANTHROPIC_API_KEY not set — skipping AI summaries, "
              "digest will show headlines only.")

    save_digest(ranked, article_counts, matches, summaries, date_str)


if __name__ == "__main__":
    main()
