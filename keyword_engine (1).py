"""
keyword_engine.py — Deep Pockets keyword scoring engine
========================================================
Drop-in scoring module for deep_pockets_tracker.py

Design principles (learned from earlier tracker bugs):
1. Tier 3 = regex PHRASE FAMILIES, not literal strings. A family fires on
   any of its patterns, but counts ONCE — no score inflation from repeats.
2. Every literal keyword also counts once per article, no matter how many
   times it appears (fixes the ranking-inflation bug).
3. Some families need CO-OCCURRENCE: "largest producer" alone is generic
   news; "largest producer" + "no brand/identity" nearby is a story.
   Implemented with .{0,N} proximity windows and require-lists.
4. Surface rule: an article only surfaces if it has at least one Tier 1
   hit OR one Tier 3 family hit. Tier 2/4 alone can never rank
   (fixes "Technology"/"packaging" dominating the digest).
5. HTML is stripped before matching (fixes HTML-in-summaries bug).

Usage:
    from keyword_engine import score_article
    result = score_article(title, summary)
    if result["surfaces"]:
        rank_by(result["score"])
        show_reason(result["matched"])
"""

import re
import html as _html

# ---------------------------------------------------------------------------
# TIER 1 — Core niche signal (weight 3 each, literal, word-boundary)
# ---------------------------------------------------------------------------
TIER1_CORE = [
    "indian craft", "indian crafts", "craftsmanship", "artisan", "artisans",
    "handmade", "handcrafted", "traditional craft", "traditional crafts",
    "heritage brand", "craft revival", "gi tag", "gi tags",
    "geographical indication", "handloom", "embroidery", "natural dye",
    "natural dyes", "ajrakh", "kantha", "artisanal", "karigar",
    "block print", "block printing", "handwoven", "hand-woven",
]

# ---------------------------------------------------------------------------
# TIER 2 — Theme signal (weight 2 each, literal)
# ---------------------------------------------------------------------------
TIER2_THEME = [
    "cultural identity", "premiumization", "premiumisation", "luxury india",
    "authenticity", "sustainable fashion", "upcycling", "slow living",
    "self-expression", "brand storytelling", "made in india",
    "global recognition", "category creation", "heritage textiles",
    "dying craft", "dying crafts", "craft cluster",
]

# ---------------------------------------------------------------------------
# TIER 3 — Discovery-trigger REGEX FAMILIES (weight 2 per family)
#
# Each family:
#   "patterns"  — list of regex; ANY match fires the family
#   "require"   — optional list of regex; at least one must ALSO match
#                 somewhere in the text (cheap co-occurrence gate)
#   "why"       — shown in the digest so you know what tripped
#
# Proximity windows use .{0,N} — N chosen generously because RSS
# summaries are short; tighten if you see false positives.
# ---------------------------------------------------------------------------
TIER3_FAMILIES = {

    "award_win": {
        "why": "International award/medal won (cheese, Red Dot, chocolate...)",
        "patterns": [
            r"\bworld\s+cheese\s+awards?\b",
            r"\bred\s*dot\s+(?:design\s+)?award\b",
            r"\bif\s+design\s+award\b",
            r"\bacademy\s+of\s+chocolate\b",
            r"\binternational\s+\w+\s+awards?\b",
            r"\b(?:wins?|won|bags?|bagged|clinch(?:es|ed)?)\s+(?:a\s+)?"
            r"(?:super\s*gold|gold|silver|bronze)\b",
            r"\b(?:gold|silver|super\s*gold)\s+medal\b",
            r"\baward[-\s]winning\s+indian\b",
        ],
        "require": None,
    },

    "record_sale": {
        "why": "Auction / price record for a craft or heritage object",
        "patterns": [
            r"\bauction\s+record\b",
            r"\brecord\s+price\b",
            r"\bmost\s+expensive\s+(?:indian|rug|carpet|sari|saree|painting|textile)\b",
            r"\bsold\s+for\s+(?:₹|rs\.?|inr)\s?\d[\d,.]*\s*(?:crore|cr|lakh)\b",
            r"\bfetch(?:es|ed)?\s+(?:₹|rs\.?|inr)\s?\d[\d,.]*\s*(?:crore|cr|lakh)\b",
            r"\bsold\s+for\s+\$\s?\d[\d,.]*\s*(?:million|mn|m)\b",
        ],
        "require": None,
    },

    "celebrity_validation": {
        "why": "Global figure / luxury house adopts an Indian craft",
        "patterns": [
            # verb ... craft-noun within a window
            r"\b(?:wore|wearing|wears|spotted\s+(?:in|wearing)|seen\s+(?:in|wearing)|"
            r"carri(?:es|ed)|donn(?:ed|ing)|dressed\s+in|styled\s+in)\b"
            r".{0,90}?"
            r"\b(?:ajrakh|kantha|khadi|banarasi|pashmina|bandhani|ikat|chikankari|"
            r"zardozi|phulkari|kalamkari|handloom|handwoven|sari|saree|dupatta|"
            r"indian\s+(?:craft|textile|weave|embroidery|designer))\b",
            # luxury house ... indian within a window
            r"\b(?:burberry|dior|herm[eè]s|gucci|louis\s+vuitton|prada|chanel|"
            r"loewe|bottega|valentino|balenciaga|ralph\s+lauren)\b"
            r".{0,120}?"
            r"\b(?:india|indian|kantha|ajrakh|khadi|chikankari|handloom|"
            r"embroider(?:y|ed)|artisan)\b",
            # runway / red-carpet events ... indian craft terms
            r"\b(?:met\s+gala|fashion\s+week|cannes|oscars?|red\s+carpet|runway)\b"
            r".{0,120}?"
            r"\b(?:indian|sari|saree|handloom|khadi|kantha|ajrakh|lehenga|"
            r"embroider(?:y|ed)|artisan|craft)\b",
        ],
        "require": None,
    },

    "producer_paradox": {
        "why": "World-scale producer with no brand/identity — your core contradiction",
        "patterns": [
            r"\b(?:world'?s?\s+)?(?:largest|biggest|top|no\.?\s*1|number\s+one|"
            r"second[-\s]largest|2nd[-\s]largest)\s+"
            r"(?:[\w-]+\s+){0,2}"      # e.g. "chilli", "human hair", "raw jute"
            r"(?:producer|exporter|grower|maker|manufacturer|supplier)s?\b",
        ],
        # generic "largest producer" is business-page noise;
        # only fire when the value-capture gap is in frame
        "require": [
            r"\b(?:no|without|lacks?|zero|missing)\s+(?:global\s+)?"
            r"(?:brand|identity|recognition)\b",
            r"\bunbranded\b",
            r"\braw\s+(?:material|form|exports?)\b",
            r"\bvalue\s+(?:addition|chain|capture)\b",
            r"\bcommodit(?:y|ised|ized)\b",
            r"\bwhy\s+(?:is\s+there\s+)?no\s+indian\b",
        ],
    },

    "quality_failure": {
        "why": "Adulteration / failed tests / bans — the fake-honey pattern",
        "patterns": [
            r"\badulterat(?:ed|ion)\b",
            r"\bfail(?:s|ed)?\s+(?:a\s+)?(?:purity|quality|safety|nmr|lab)\s+test",
            r"\bfssai\s+(?:action|notice|crackdown|ban)\b",
            r"\b(?:fake|counterfeit|spurious)\s+"
            r"(?:honey|saffron|ghee|spices?|khadi|silk|pashmina|products?)\b",
            r"\brecall(?:s|ed)?\s+.{0,40}\b(?:contaminat|adulterat)",
            r"\bbann?ed\s+(?:for|over|after)\s+.{0,40}\b(?:quality|safety|contaminat)",
        ],
        "require": None,
    },

    "policy_shift": {
        "why": "QCO / duty / GI grant / dedicated board — the toys & makhana pattern",
        "patterns": [
            r"\bquality\s+control\s+orders?\b",
            r"\bbis\s+certification\b",
            r"\bimport\s+dut(?:y|ies)\s+(?:raised|hiked|increased|cut|slashed)\b",
            r"\bgi\s+(?:tag|status|registration)\s+"
            r"(?:granted|awarded|received|approved|for)\b",
            r"\b(?:gets?|receives?|granted)\s+gi\s+tag\b",
            r"\bdedicated\s+(?:board|body|mission)\b",
            r"\b(?:new|own|separate)\s+hs\s+code\b",
            r"\bexport\s+(?:ban|floor\s+price|restriction)s?\b",
            r"\bproduction[-\s]linked\s+incentive\b|\bpli\s+scheme\b",
        ],
        "require": None,
    },

    "global_debut": {
        "why": "First shipment / overseas store / export debut",
        "patterns": [
            r"\bfirst\s+(?:commercial\s+)?(?:sea\s+)?(?:shipment|consignment)\b",
            r"\bapeda\s+facilitat(?:es|ed)\b",
            r"\bdebuts?\s+in\s+(?:paris|london|new\s+york|tokyo|dubai|milan)\b",
            r"\b(?:opens?|opened|launch(?:es|ed)?)\s+"
            r"(?:its\s+)?(?:first\s+)?(?:flagship\s+)?store\s+in\s+"
            r"(?:paris|london|new\s+york|tokyo|dubai|milan|singapore)\b",
            r"\benters?\s+(?:the\s+)?(?:us|uk|european|japanese|gulf)\s+market\b",
            r"\bexport(?:s|ed)?\s+(?:for\s+the\s+)?first\s+time\b",
        ],
        "require": None,
    },

    "hidden_supplier": {
        "why": "Private-label / uncredited Indian maker behind a global product",
        "patterns": [
            r"\bprivate\s+label\b",
            r"\bcontract\s+manufactur(?:er|ing)\b",
            r"\bwhite[-\s]label\b",
            r"\b(?:supplies?|supplier)\s+(?:to|for)\s+"
            r"(?:pottery\s+barn|macy'?s|bloomingdale'?s|ikea|zara|h&m|walmart|"
            r"target|west\s+elm|crate\s+(?:and|&)\s+barrel)\b",
            r"\bmade\s+in\s+india\s*,?\s+sold\s+(?:as|under)\b",
            r"\buncredited\b.{0,60}\b(?:artisan|maker|manufactur|weav)",
        ],
        "require": None,
    },
}

# ---------------------------------------------------------------------------
# TIER 4 — Context only (weight 1, can NEVER surface an article alone)
# ---------------------------------------------------------------------------
TIER4_CONTEXT = [
    "d2c brand", "d2c brands", "consumer preference", "gen z india",
    "packaging design", "export growth", "premium water", "mechanical watch",
    "hot sauce", "artisanal cheese", "cold chain", "premium brand",
    "direct-to-consumer",
]

WEIGHTS = {"tier1": 3, "tier2": 2, "tier3": 2, "tier4": 1}

# ---------------------------------------------------------------------------
# Compilation (done once at import)
# ---------------------------------------------------------------------------
_FLAGS = re.IGNORECASE | re.DOTALL

def _compile_literals(terms):
    """Literal phrases -> word-boundary regexes. Spaces match any whitespace."""
    out = []
    for t in terms:
        pat = r"\b" + re.escape(t).replace(r"\ ", r"\s+") + r"\b"
        out.append((t, re.compile(pat, _FLAGS)))
    return out

_T1 = _compile_literals(TIER1_CORE)
_T2 = _compile_literals(TIER2_THEME)
_T4 = _compile_literals(TIER4_CONTEXT)

_T3 = {}
for fam, spec in TIER3_FAMILIES.items():
    _T3[fam] = {
        "why": spec["why"],
        "patterns": [re.compile(p, _FLAGS) for p in spec["patterns"]],
        "require": ([re.compile(p, _FLAGS) for p in spec["require"]]
                    if spec["require"] else None),
    }

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def clean_text(raw: str) -> str:
    """Strip HTML tags/entities and collapse whitespace (feedparser summaries
    often arrive as HTML — matching against raw HTML silently fails)."""
    if not raw:
        return ""
    txt = _html.unescape(raw)
    txt = _TAG_RE.sub(" ", txt)
    return _WS_RE.sub(" ", txt).strip()


def score_article(title: str, summary: str = "") -> dict:
    """
    Score one article. Returns:
      score      int   — weighted total
      surfaces   bool  — True only if >=1 Tier1 hit or >=1 Tier3 family
      matched    dict  — {"tier1": [...], "tier2": [...],
                          "tier3": [{"family","why","evidence"}], "tier4": [...]}
    Each literal term and each Tier-3 family counts at most ONCE.
    Title matches get a small bonus (+1) because headline presence is a
    stronger signal than a passing mention in the body.
    """
    t_title = clean_text(title)
    t_all = (t_title + " " + clean_text(summary)).strip()

    matched = {"tier1": [], "tier2": [], "tier3": [], "tier4": []}
    score = 0

    for tier_key, compiled, w in (
        ("tier1", _T1, WEIGHTS["tier1"]),
        ("tier2", _T2, WEIGHTS["tier2"]),
        ("tier4", _T4, WEIGHTS["tier4"]),
    ):
        for term, rx in compiled:
            if rx.search(t_all):                      # counts once, ever
                matched[tier_key].append(term)
                score += w
                if rx.search(t_title):
                    score += 1                        # headline bonus

    for fam, spec in _T3.items():
        hit = None
        for rx in spec["patterns"]:
            m = rx.search(t_all)
            if m:
                hit = m
                break
        if not hit:
            continue
        if spec["require"] is not None:
            if not any(r.search(t_all) for r in spec["require"]):
                continue                              # co-occurrence gate failed
        evidence = _WS_RE.sub(" ", hit.group(0))[:110]
        matched["tier3"].append(
            {"family": fam, "why": spec["why"], "evidence": evidence}
        )
        score += WEIGHTS["tier3"]
        if any(rx.search(t_title) for rx in spec["patterns"]):
            score += 1                                # headline bonus

    surfaces = bool(matched["tier1"] or matched["tier3"])
    return {"score": score, "surfaces": surfaces, "matched": matched}


def explain(result: dict) -> str:
    """One-line digest explanation: why did this article rank?"""
    bits = []
    for e in result["matched"]["tier3"]:
        bits.append(f"[{e['family']}] \u201c{e['evidence']}\u201d")
    if result["matched"]["tier1"]:
        bits.append("core: " + ", ".join(result["matched"]["tier1"][:4]))
    if not bits and result["matched"]["tier2"]:
        bits.append("theme: " + ", ".join(result["matched"]["tier2"][:3]))
    return " | ".join(bits) if bits else "context only"


# ---------------------------------------------------------------------------
# Self-test — run `python keyword_engine.py`
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    SAMPLES = [
        # (should_surface, title, summary)
        (True,  "Two Indian cheese brands win Super Gold at World Cheese Awards",
                "Eleftheria and Nordic Farm impressed international judges."),
        (True,  "Christopher Nolan spotted wearing an Ajrakh tie at premiere",
                "The Kutch block print is having a global fashion moment."),
        (True,  "300-year-old Indian rug sold for ₹70 crore at auction",
                "A record price for Indian carpet craftsmanship."),
        (True,  "Top honey brands fail NMR purity test, adulteration found",
                "Lab reports reveal syrup mixing in leading brands."),
        (True,  "Noise ALT series bags Red Dot Design Award 2026",
                "The design-first wearables line wins international recognition."),
        (True,  "India is world's largest chilli producer — so why is there "
                "no Indian Tabasco?",
                "Despite scale, exports remain raw material without a brand."),
        (True,  "Burberry's new collection features Bengal's Kantha embroidery",
                "Artisans from West Bengal supplied the hand-stitched panels."),
        (True,  "Makhana gets own HS code, dedicated board announced",
                "Budget allocates ₹100 crore; first sea shipment to Australia "
                "facilitated by APEDA."),
        (True,  "Gurugram exporter runs private label bedding for Pottery Barn",
                "The quiet supplier behind American luxury linen."),
        # negatives — must NOT surface
        (False, "How IPL is destroying Test cricket",
                "The business of franchise leagues and broadcast money."),
        (False, "Indian D2C brand raises $40M Series B",
                "The consumer preference shift toward online-first brands "
                "drives export growth hopes."),
        (False, "India remains world's largest milk producer",
                "Dairy output rose 4% this year, government data shows."),
        (False, "Best packaging design trends for startups in 2026",
                "Gen Z India wants premium brand experiences."),
    ]

    passed = 0
    for want, title, summ in SAMPLES:
        r = score_article(title, summ)
        ok = r["surfaces"] == want
        passed += ok
        mark = "PASS" if ok else "FAIL"
        print(f"[{mark}] surfaces={r['surfaces']!s:5} score={r['score']:2d}  "
              f"{title[:58]}")
        if r["surfaces"]:
            print(f"        -> {explain(r)}")
    print(f"\n{passed}/{len(SAMPLES)} checks passed")
