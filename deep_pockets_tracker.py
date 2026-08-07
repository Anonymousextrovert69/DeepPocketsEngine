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

# -----------------------------------------------------------------------
# 1. CONFIGURE YOUR SOURCES — add/remove RSS feeds freely
#    NOTE: dict keys must be unique. If you paste in a source name that
#    already exists, Python will silently overwrite the first one and
#    you'll lose that feed without any error. Give each entry a distinct
#    name if two feeds happen to share a source name.
# -----------------------------------------------------------------------
RSS_FEEDS = {
    # # ---------------- General news ----------------
# "Times of India": "https://timesofindia.indiatimes.com/rssfeedstopstories.cms",
# "Hindustan Times": "https://www.hindustantimes.com/feeds/rss/india-news/rssfeed.xml",
# "The Hindu": "https://www.thehindu.com/news/national/feeder/default.rss",
# "Indian Express": "https://indianexpress.com/section/india/feed/",
# "NDTV": "https://feeds.feedburner.com/ndtvnews-india-news",

# # ---------------- Global news / affairs ----------------
# "BBC World": "http://feeds.bbci.co.uk/news/world/rss.xml",
# "BBC Business": "http://feeds.bbci.co.uk/news/business/rss.xml",
# "Reuters World": "https://www.reutersagency.com/feed/?best-topics=world&post_type=best",
# "Reuters Business": "https://www.reutersagency.com/feed/?best-topics=business-finance&post_type=best",
# "The Guardian World": "https://www.theguardian.com/world/rss",
# "The Guardian Business": "https://www.theguardian.com/business/rss",
# "CNN Business": "http://rss.cnn.com/rss/money_latest.rss",
# "Bloomberg": "https://feeds.bloomberg.com/markets/news.rss",
# "Financial Times": "https://www.ft.com/rss/home",
# "The Economist": "https://www.economist.com/business/rss.xml",

# # ---------------- India business & economy ----------------
# # Renamed pairs below: same source, two different feeds/sections each,
# # kept as separate entries instead of overwriting one another.
# "Economic Times - Top Stories": "https://economictimes.indiatimes.com/rssfeedstopstories.cms",
# "Economic Times - All News": "https://economictimes.indiatimes.com/rssfeedsdefault.cms",
# "Business Standard - Latest": "https://www.business-standard.com/rss/latest.rss",
# "Business Standard - Top Stories": "https://www.business-standard.com/rss/home_page_top_stories.rss",
# "Moneycontrol - Latest News": "https://www.moneycontrol.com/rss/latestnews.xml",
# "Moneycontrol - Business": "https://www.moneycontrol.com/rss/business.xml",
# "Livemint": "https://www.livemint.com/rss/news",
# "Financial Express": "https://www.financialexpress.com/feed/",

# # ---------------- Startups & D2C ----------------
# "YourStory": "https://yourstory.com/feed",
# "Inc42": "https://inc42.com/feed/",
# "Entrackr": "https://entrackr.com/feed/",
# "StartupTalky": "https://startuptalky.com/feed/",
# "StartupNews.fyi": "https://startupnews.fyi/feed",

# # ---------------- Marketing & branding ----------------
# "Marketing Week": "https://www.marketingweek.com/feed/",
# "Marketing Dive": "https://www.marketingdive.com/feeds/news/",
# "Adweek": "https://www.adweek.com/feed/",
# "Campaign Asia": "https://www.campaignasia.com/rss",
# "The Drum": "https://www.thedrum.com/rss.xml",

# # ---------------- Consumer trends ----------------
# "TrendWatching": "https://trendwatching.com/feed",
# "Springwise": "https://www.springwise.com/feed/",
# "PSFK": "https://www.psfk.com/feed",

# # ---------------- Retail & D2C ----------------
# "Retail Dive": "https://www.retaildive.com/feeds/news/",
# "Modern Retail": "https://www.modernretail.co/feed/",
# "Retail Gazette": "https://www.retailgazette.co.uk/blog/feed/",

# # ---------------- Manufacturing ----------------
# "Manufacturing Today India": "https://www.manufacturingtodayindia.com/feed",
# "Manufacturing Global": "https://manufacturingglobal.com/rss",

# # ---------------- India economy / policy ----------------
# "Reserve Bank of India": "https://www.rbi.org.in/Scripts/RSS.aspx",
# "PIB Business": "https://pib.gov.in/rss.aspx",
# "NITI Aayog": "https://www.niti.gov.in/rss.xml",
# "Invest India": "https://www.investindia.gov.in/rss.xml",
# "DPIIT": "https://dpiit.gov.in/rss.xml",

# # ---------------- Sustainability ----------------
# "GreenBiz": "https://www.greenbiz.com/rss.xml",
# "Circular Online": "https://www.circularonline.co.uk/feed/",

# # ---------------- Luxury ----------------
# "Business of Fashion": "https://www.businessoffashion.com/feed/",
# "Vogue Business": "https://www.voguebusiness.com/feed",

# # ---------------- Food industry ----------------
# "FoodNavigator Asia": "https://www.foodnavigator-asia.com/rss",
# "Food Business News": "https://www.foodbusinessnews.net/rss",

# # ---------------- Tech & innovation ----------------
# "TechCrunch": "https://techcrunch.com/feed/",
# "Rest of World": "https://restofworld.org/feed/latest/",
# "Wired": "https://www.wired.com/feed/rss",

# # ---------------- Design ----------------
# "Dezeen": "https://www.dezeen.com/feed/",
# "DesignBoom": "https://www.designboom.com/feed/",

# # ---------------- Packaging ----------------
# "Packaging Europe": "https://packagingeurope.com/feed/",
# "The Dieline": "https://thedieline.com/blog?format=rss",

# # ---------------- Agriculture ----------------
# "Down To Earth": "https://www.downtoearth.org.in/rss",
# "Mongabay India": "https://india.mongabay.com/feed/",

# # ---------------- Consumer goods ----------------
# "FMCG Gurus": "https://fmcggurus.com/feed/",
# "CPG Wire": "https://cpgwire.com/feed/",

    # ----------------- Deep Pockets -----------------
    "Bar and Bench": "https://www.barandbench.com/stories.rss,
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
      "Lyst Data": null,
      "BuzzInContent": "https://www.buzzincontent.com/feed/",
      "Social Media Today": "https://www.socialmediatoday.com/feeds/news/",
      "India Today": "https://www.indiatoday.in/rss/home",
      "Architectural Digest India": "https://www.architecturaldigest.in/feed/",
      "The Established": "https://www.theestablished.com/feed/",
      "Monochrome Watches": "https://monochrome-watches.com/feed/",
      "Futura Sciences": "https://www.futura-sciences.com/en/rss/news.xml",
      "ELLE India": "https://elle.in/feed/" 
    
}

# -----------------------------------------------------------------------
# 2. CONFIGURE YOUR KEYWORDS — this is your niche lens
#    NOTE: list entries CAN legally repeat (unlike dict keys) — Python
#    won't stop you. But every repeated keyword gets counted twice per
#    mention, which artificially inflates its rank. Keep each keyword
#    (case-insensitive) listed exactly once.
# -----------------------------------------------------------------------
KEYWORDS = [
    Indian Heritage,
    Indian Handicrafts,
    cultural revival,
    Traditional Crafts,
    Indian Artisans,
    embroidery,
    Brand Storytelling,
    founder stories,
    identity design,
    Design Innovation,
    Industrial design,
    packaging,
    product design,
    Consumer Psychology,
    Buying behavior,
    perception,
    habits,
    Indian Startups,
    consumer brands,
    manufacturing,
    D2C Brands,
    Manufacturing,
    Factories,
    Make in India,
    production innovation,
    Entrepreneurship,
    Founders,
    business creation,
    scaling,
    Cultural Entrepreneurship,
    Businesses built around culture,
    heritage business,
    Craft Revival,
    Modern revival,
    dying crafts,
    Sustainable Materials,
    Natural fibres,
    eco materials,
    biomaterials,
    Circular Economy,
    Waste-to-value,
    Rural Innovation,
    Grassroots innovation,
    Indigenous Technology,
    Traditional techniques,
    modern technology,
    Packaging Innovation,
    Premiumization,
    Retail Trends,
    Consumer retail,
    retail shifts,
    Luxury India,
    Indian premium brands,
    Made in India,
    global recognition,
    Export Growth,
    Indian exports,
    international markets,
    Geographical Indications,
    GI Tags,
    GI registration,
    GI commercialization,
    Food Innovation,
    Traditional foods,
    food brands,
    Fashion Innovation,
    Textiles,
    heritage fabrics,
    fashion designers,
    Consumer Trends,
    Lifestyle shifts,
    Marketing Campaigns,
    Creative campaigns,
    Creator Economy,
    Personal brands,
    media businesses,
    Business Models,
    distribution,
    pricing,
    monetization,
    Future of Work,
    AI,
    automation,
    manufacturing jobs,
    India Innovation,
    Technology,
    research,
    patents,
    deep tech
]

# How many days back to consider an article "recent" (RSS often mixes dates)
LOOKBACK_DAYS = 2


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


def save_digest(ranked, matches, date_str):
    fname = f"digest_{date_str}.md"
    with open(fname, "w", encoding="utf-8") as f:
        f.write(f"# Deep Pockets — Trend Digest — {date_str}\n\n")
        for kw, count in ranked:
            f.write(f"## {kw} ({count} mentions)\n\n")
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
    if ranked:
        save_csv(ranked, date_str)
        save_digest(ranked, matches, date_str)


if __name__ == "__main__":
    main()
