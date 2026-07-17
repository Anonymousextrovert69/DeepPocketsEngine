"""
Deep Pockets — Daily Keyword Trend Tracker
--------------------------------------------
Pulls today's articles from a list of RSS feeds (Indian + global news),
scans headlines/summaries for your niche keywords, and ranks them by
frequency (descending) — with the actual headlines/links behind each hit,
so you can go straight from "trending keyword" to "video idea".

Setup (one-time):
    pip install feedparser requests --break-system-packages

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

# -----------------------------------------------------------------------
# 1. CONFIGURE YOUR SOURCES — add/remove RSS feeds freely
# -----------------------------------------------------------------------
RSS_FEEDS = {
    # General news (context, GI/trademark disputes often break here first)
    "Times of India": "https://timesofindia.indiatimes.com/rssfeedstopstories.cms",
    "Hindustan Times": "https://www.hindustantimes.com/feeds/rss/india-news/rssfeed.xml",
    "The Hindu": "https://www.thehindu.com/news/national/feeder/default.rss",
    "Indian Express": "https://indianexpress.com/section/india/feed/",
    "NDTV": "https://feeds.feedburner.com/ndtvnews-india-news",

    # Business & economy (this is where your actual story angle lives)
    "Economic Times": "https://economictimes.indiatimes.com/rssfeedstopstories.cms",
    "Livemint": "https://www.livemint.com/rss/news",
    "Business Standard": "https://www.business-standard.com/rss/latest.rss",
    "Moneycontrol": "https://www.moneycontrol.com/rss/latestnews.xml",
    "YourStory (startups/D2C)": "https://yourstory.com/feed",

    # Global comparison anchors
    "BBC World": "http://feeds.bbci.co.uk/news/world/rss.xml",
    "Reuters World": "https://www.reutersagency.com/feed/?best-topics=world&post_type=best",
    "The Guardian World": "https://www.theguardian.com/world/rss",
    
    # Add more here: "Source Name": "RSS URL",
    # ---------------- Global Business ----------------
    "Reuters Business": "https://www.reutersagency.com/feed/?best-topics=business-finance&post_type=best",
    "Bloomberg": "https://feeds.bloomberg.com/markets/news.rss",
    "Financial Times": "https://www.ft.com/rss/home",
    "The Economist": "https://www.economist.com/business/rss.xml",
    
    # ---------------- India Business ----------------
    "Moneycontrol": "https://www.moneycontrol.com/rss/business.xml",
    "Economic Times": "https://economictimes.indiatimes.com/rssfeedsdefault.cms",
    "Business Standard": "https://www.business-standard.com/rss/home_page_top_stories.rss",
    "Mint": "https://www.livemint.com/rss/news",
    "Financial Express": "https://www.financialexpress.com/feed/",
    
    # ---------------- Startups & D2C ----------------
    "YourStory": "https://yourstory.com/feed",
    "Inc42": "https://inc42.com/feed/",
    "Entrackr": "https://entrackr.com/feed/",
    "StartupTalky": "https://startuptalky.com/feed/",
    "StartupNews.fyi": "https://startupnews.fyi/feed",
    
    # ---------------- Marketing & Branding ----------------
    "Marketing Week": "https://www.marketingweek.com/feed/",
    "Marketing Dive": "https://www.marketingdive.com/feeds/news/",
    "Adweek": "https://www.adweek.com/feed/",
    "Campaign Asia": "https://www.campaignasia.com/rss",
    "The Drum": "https://www.thedrum.com/rss.xml",
    
    # ---------------- Consumer Trends ----------------
    "TrendWatching": "https://trendwatching.com/feed",
    "Springwise": "https://www.springwise.com/feed/",
    "PSFK": "https://www.psfk.com/feed",
    
    # ---------------- Retail & D2C ----------------
    "Retail Dive": "https://www.retaildive.com/feeds/news/",
    "Modern Retail": "https://www.modernretail.co/feed/",
    "Retail Gazette": "https://www.retailgazette.co.uk/blog/feed/",
    
    # ---------------- Manufacturing ----------------
    "Manufacturing Today India": "https://www.manufacturingtodayindia.com/feed",
    "Manufacturing Global": "https://manufacturingglobal.com/rss",
    
    # ---------------- India Economy ----------------
    "Reserve Bank of India": "https://www.rbi.org.in/Scripts/RSS.aspx",
    "PIB Business": "https://pib.gov.in/rss.aspx",
    "NITI Aayog": "https://www.niti.gov.in/rss.xml",
    
    # ---------------- Policy ----------------
    "Invest India": "https://www.investindia.gov.in/rss.xml",
    "DPIIT": "https://dpiit.gov.in/rss.xml",
    
    # ---------------- Sustainability ----------------
    "GreenBiz": "https://www.greenbiz.com/rss.xml",
    "Circular Online": "https://www.circularonline.co.uk/feed/",
    
    # ---------------- Luxury ----------------
    "Business of Fashion": "https://www.businessoffashion.com/feed/",
    "Vogue Business": "https://www.voguebusiness.com/feed",
    
    # ---------------- Food Industry ----------------
    "FoodNavigator Asia": "https://www.foodnavigator-asia.com/rss",
    "Food Business News": "https://www.foodbusinessnews.net/rss",
    
    # ---------------- Tech & Innovation ----------------
    "TechCrunch": "https://techcrunch.com/feed/",
    "Rest of World": "https://restofworld.org/feed/latest/",
    "Wired": "https://www.wired.com/feed/rss",
    
    # ---------------- Design ----------------
    "Dezeen": "https://www.dezeen.com/feed/",
    "DesignBoom": "https://www.designboom.com/feed/",
    
    # ---------------- Packaging ----------------
    "Packaging Europe": "https://packagingeurope.com/feed/",
    "The Dieline": "https://thedieline.com/blog?format=rss",
    
    # ---------------- Agriculture ----------------
    "Down To Earth": "https://www.downtoearth.org.in/rss",
    "Mongabay India": "https://india.mongabay.com/feed/",
    
    # ---------------- Global Affairs ----------------
    "BBC Business": "http://feeds.bbci.co.uk/news/business/rss.xml",
    "The Guardian Business": "https://www.theguardian.com/business/rss",
    "CNN Business": "http://rss.cnn.com/rss/money_latest.rss",
    
    # ---------------- Consumer Goods ----------------
    "FMCG Gurus": "https://fmcggurus.com/feed/",
    "CPG Wire": "https://cpgwire.com/feed/"
    
}

# -----------------------------------------------------------------------
# 2. CONFIGURE YOUR KEYWORDS — this is your niche lens
# -----------------------------------------------------------------------
KEYWORDS = [
    # --- Core narrative: India creates, someone else captures the value ---
    "GI tag",                    # Geographical Indication disputes (Kolhapuri/Prada type stories)
    "cultural appropriation",
    "knockoff",
    "IP theft",
    "trademark dispute",
    "counterfeit",
    "who owns",                  # catches "who owns the brand/design/recipe" framing

    # --- Branding & premiumization (your recurring economic angle) ---
    "premiumization",
    "D2C brand",
    "heritage brand",
    "global icon",
    "market creation",
    "brand identity",
    "made in India",
    "Make in India",
    "export potential",
    "value chain",
    "cold-chain",
    "private label",

    # --- Heritage industries you've already covered — track for follow-ups ---
    "seafood export",
    "aquaculture",
    "mineral water",
    "heritage cookware",
    "Indian watches",
    "horology",
    "handloom",
    "textile export",
    "tattoo culture",
    "superfood",
    "Moringa",
    "GI-tagged",

    # --- Comparative "X country owns this category" stories ---
    "Norway salmon",
    "Japan matcha",
    "Swiss watch industry",
    "global demand",
    "category leader",

    # --- Luxury brands using Indian design (appropriation-story bait) ---
    "Prada",
    "Louis Vuitton",
    "Hermes",
    "Gucci",
    "kolhapuri",

    # --- Indian Heritage & Culture ---
    "heritage",
    "traditional",
    "handloom",
    "handicraft",
    "GI Tag",
    "Geographical Indication",
    "Ayurveda",
    "Khadi",
    "tribal",
    "artisan",

    # --- Indian Food & Regional Brands ---
    "mithai",
    "pickles",
    "spices",
    "tea",
    "coffee",
    "millets",
    "jaggery",
    "mahua",
    "ghee",
    "namkeen",
    
    # --- Indian Fashion & Lifestyle ---
    "saree",
    "kolhapuri",
    "banarasi",
    "pashmina",
    "kalamkari",
    "chikankari",
    "ajrakh",
    "bandhani",
    "khussa",
    "mojari",
    
    # --- Indian Consumer Brands ---
    "Bombay Sweet Shop",
    "Gully Labs",
    "Phool",
    "Blue Tokai",
    "Paper Boat",
    "Forest Essentials",
    "Nicobar",
    "Rare Rabbit",
    "Comet",
    "DailyObjects",
    
    # --- Luxury Brands Using Indian Design ---
    "Prada",
    "Louis Vuitton",
    "Hermes",
    "Gucci",
    "Dior",
    
    # --- Startup Keywords ---
    "startup",
    "D2C",
    "bootstrapped",
    "founder",
    "unicorn",
    "venture capital",
    "funding",
    "seed round",
    "Series A",
    "profitability",
    
    # --- Business Strategy ---
    "branding",
    "positioning",
    "premiumization",
    "distribution",
    "pricing",
    "community",
    "network effects",
    "moat",
    "category creation",
    "go-to-market",
    
    # --- Consumer Psychology ---
    "nostalgia",
    "identity",
    "status",
    "luxury",
    "aspiration",
    "consumer behavior",
    "tribe",
    "scarcity",
    "social proof",
    "pricing psychology",
    
    # --- India Economy ---
    "Make in India",
    "Atmanirbhar Bharat",
    "manufacturing",
    "exports",
    "MSME",
    "PLI Scheme",
    "GDP",
    "inflation",
    "rupee",
    "middle class",
    
    # --- Indian Business Houses ---
    "Tata",
    "Reliance",
    "Adani",
    "Mahindra",
    "Godrej",
    
    # --- Global Companies Affecting India ---
    "Nike",
    "Adidas",
    "Apple",
    "Starbucks",
    "IKEA",
    
    # --- Sustainability & Purpose ---
    "circular economy",
    "recycling",
    "upcycling",
    "climate tech",
    "plastic waste",
    "waste management",
    "carbon",
    "ESG",
    "ethical sourcing",
    "regenerative",
    
    # --- Creator Opportunity Keywords ---
    "case study",
    "business story",
    "brand strategy",
    "marketing campaign",
    "rebranding",
    "viral product",
    "cult brand",
    "purpose-driven",
    "Made in India",
    "Indian innovation"
    
]

# How many days back to consider an article "recent" (RSS often mixes dates)
LOOKBACK_DAYS = 2


def fetch_articles():
    """Pull entries from all feeds, tag with source."""
    articles = []
    cutoff = datetime.now() - timedelta(days=LOOKBACK_DAYS)

    for source, url in RSS_FEEDS.items():
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
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
