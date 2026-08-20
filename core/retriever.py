import re
from core.data_loader import load_products

# ─── Compiled Patterns ────────────────────────────────────────────────────────

# Matches product IDs like ac001, wm016, rf003 (2 letters + digits)
ID_PATTERN = re.compile(r"^[a-z]{2}\d+$")

# Matches standalone model numbers like GRE-AC-1037, GREAC1037, GRE AC 1037
# Format: 2-5 letters + optional separator + 1-5 letters + optional separator + 3-6 digits
MODEL_PATTERN = re.compile(r"^[a-zA-Z]{2,5}[\s\-_.]*[a-zA-Z]{1,5}[\s\-_.]*\d{3,6}$")

# Maps short user terms to full database category names
CATEGORY_ALIASES = {
    "ac":           "Air Conditioner",
    "acs":          "Air Conditioner",
    "aircon":       "Air Conditioner",
    "fridge":       "Refrigerator",
    "fridges":      "Refrigerator",
    "refrigerator": "Refrigerator",
    "rf":           "Refrigerator",
    "washer":       "Washing Machine",
    "washers":      "Washing Machine",
    "wm":           "Washing Machine",
    "oven":         "Microwave Oven",
    "ovens":        "Microwave Oven",
    "microwave":    "Microwave Oven",
    "mw":           "Microwave Oven",
    "dispenser":    "Water Dispenser",
    "dispensers":   "Water Dispenser",
    "wd":           "Water Dispenser",
}

# Conversational filler words — removed during tokenisation only
FILLER_WORDS = {
    "i","me","my","we","our","you","your",
    "the","a","an","is","are","was","be","been",
    "in","of","for","and","or","to","do","did",
    "it","its","this","that","these","those",
    "please","plz","pls","ok","okay","hi","hello","hey","salam",
    "give","show","tell","find","get","need","want",
    "have","has","can","will","would","should",
    "any","all","some","with","about","detail",
    "details","detals","list","product","products",
    "which","what","how","suggest","recommend",
    "good","best","nice","new","top","great",
    "pk","pkr","rs","price","buy","cheap",
    "range","budget","under","above","between",
}


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _normalize(text: str) -> str:
    """Strip separators and lowercase — used for fuzzy matching."""
    return re.sub(r"[\s\-_./#&()+]", "", text).lower()


def _looks_like_model(text: str) -> bool:
    """True for GRE-AC-1037, GREAC1037, HAI-WM-2016 etc."""
    return bool(MODEL_PATTERN.match(text.strip()))


def _extract_model_from_query(query: str) -> str | None:
    """Find an embedded model number token in a longer query."""
    for token in query.split():
        if _looks_like_model(token):
            return token
    return None


def _build_product_normalized(p: dict) -> dict:
    """Pre-compute normalised versions of all searchable fields."""
    fields = ["product_id","product_name","brand","category","model_number",
              "capacity","key_features","description","color",
              "stock_status","energy_rating"]
    return {f: _normalize(str(p.get(f, ""))) for f in fields}


# ─── Scoring ──────────────────────────────────────────────────────────────────

def _score_model_query(norm_product: dict, query_norm: str) -> int:
    """
    Exact/normalised match for model number or product ID queries.
    200 pts for match, 0 for no match.
    """
    if query_norm == norm_product["model_number"]:
        return 200
    if query_norm == norm_product["product_id"]:
        return 200
    return 0


def _score_keyword_query(product: dict, norm_product: dict,
                         raw_tokens: list, norm_tokens: list) -> int:
    """
    Keyword scoring:
        Product ID exact match     → 100 pts
        Token in product_name      →  15 pts
        Token in any other field   →   1 pt
        Pure numbers               →   0 pts (noise)
        ID-like token, no match    →   0 pts (avoid false positives)
    """
    score = 0
    raw_haystack = " ".join([
        str(product.get(f, "")) for f in [
            "product_name","brand","category","model_number",
            "capacity","key_features","description",
            "color","stock_status","energy_rating",
        ]
    ]).lower()

    for raw_t, norm_t in zip(raw_tokens, norm_tokens):
        if raw_t.isdigit():
            continue
        if raw_t == product.get("product_id","").lower():
            score += 100
            continue
        if ID_PATTERN.match(raw_t):
            continue
        if norm_t and norm_t in norm_product["product_name"]:
            score += 15
            continue
        if raw_t in raw_haystack:
            score += 1

    return score


# ─── Filters ──────────────────────────────────────────────────────────────────

def _parse_capacity_filter(query: str) -> str | None:
    """
    Extract capacity: '1.5 ton' → '15ton', '2ton' → '2ton'
    Returns None if no capacity found.
    """
    m = re.search(r'\b(\d+(?:\.\d+)?)\s*ton\b', query, re.IGNORECASE)
    return _normalize(m.group(0)) if m else None


def _parse_price_filter(query: str) -> tuple:
    """
    Extract price constraints:
        'between 50000 and 100000' → (50000, 100000)
        'between 10k to 50k'       → (10000, 50000)
        'under 80000' / 'under 80k'→ (None, 80000)
        'above 30000' / 'above 30k'→ (30000, None)
        'budget 70000'             → (None, 70000)
        '1 to 10000'               → (1, 10000)
    Returns (lo, hi) — either can be None.
    """
    q = query.lower().replace(",", "")

    def _to_int(s: str) -> int:
        """Convert '10k' → 10000, '10K' → 10000, '10000' → 10000."""
        s = s.strip()
        if s.endswith('k'):
            return int(float(s[:-1]) * 1000)
        return int(s)

    # Number pattern: digits optionally followed by 'k'
    _N = r"(\d+(?:\.\d+)?k?)"

    # Common filler words people naturally use between a price keyword
    # and the actual number — e.g. "under the 12000", "above a budget of 50k",
    # "under rs 80000", "under my budget of 30k".
    _FILL = r"(?:\s+(?:the|a|my|is|of|for|rs\.?|pkr))*"

    # 'between X and Y'  or  'between X to Y'
    between = re.search(rf"between{_FILL}\s+{_N}\s+(?:and|to){_FILL}\s+{_N}", q)
    if between:
        lo, hi = _to_int(between.group(1)), _to_int(between.group(2))
        return min(lo, hi), max(lo, hi)

    # 'from X to Y'  or  'X to Y'
    to_range = re.search(rf"(?:from\s+)?{_N}\s+to\s+{_N}", q)
    if to_range:
        lo, hi = _to_int(to_range.group(1)), _to_int(to_range.group(2))
        return min(lo, hi), max(lo, hi)

    above  = re.search(rf"above{_FILL}\s+{_N}",  q)
    under  = re.search(rf"under{_FILL}\s+{_N}",  q)
    budget = re.search(rf"(?:price|budget|range){_FILL}\s+{_N}", q)

    lo = _to_int(above.group(1))  if above  else None
    hi = _to_int(under.group(1))  if under  else (_to_int(budget.group(1)) if budget else None)

    return lo, hi


# ─── Main Retrieve ─────────────────────────────────────────────────────────────

def retrieve(query: str, products: list[dict],
             category: str | None = None, top_k: int = 10) -> list[dict]:
    """
    Three-mode search engine:

    Mode A — Exact model/ID match
             'GRE-AC-1037', 'AC001', 'give me HAI-WM-2016'
             → returns 1 exact product

    Mode B — Keyword scoring
             'Haier inverter AC under 80000', '1.5 ton dawlance fridge'
             → returns up to top_k ranked products

    Mode C — Filter-only
             'under 50000', '1.5 ton', category tab click
             → returns filtered products sorted by price

    Never returns random products — returns [] if nothing matches.
    """

    # Step 1: Category hard filter
    if category:
        products = [p for p in products if p["category"] == category]

    # Step 2: Price hard filter
    lo, hi = _parse_price_filter(query)
    if lo is not None:
        products = [p for p in products if p["price_pkr"] >= lo]
    if hi is not None:
        products = [p for p in products if p["price_pkr"] <= hi]

    has_price_kw = bool(re.search(r'\b(under|above|between)\b', query, re.IGNORECASE))

    # Step 3: Mode A — standalone model number
    if _looks_like_model(query) and not has_price_kw:
        query_norm    = _normalize(query)
        norm_products = [_build_product_normalized(p) for p in products]
        scored = sorted(
            [(p, _score_model_query(np, query_norm)) for p, np in zip(products, norm_products)],
            key=lambda x: x[1], reverse=True
        )
        return [p for p, sc in scored if sc > 0][:top_k]

    # Step 4: Mode A — embedded model in query
    embedded_model = _extract_model_from_query(query)
    if embedded_model and not has_price_kw:
        model_norm    = _normalize(embedded_model)
        norm_products = [_build_product_normalized(p) for p in products]
        scored = sorted(
            [(p, _score_model_query(np, model_norm)) for p, np in zip(products, norm_products)],
            key=lambda x: x[1], reverse=True
        )
        results = [p for p, sc in scored if sc > 0][:top_k]
        if results:
            return results

    # Step 5: Capacity hard filter
    capacity_norm = _parse_capacity_filter(query)
    if capacity_norm:
        products = [
            p for p in products
            if _normalize(str(p.get("capacity", ""))) == capacity_norm
        ]

    # Step 6: Clean query for tokenisation
    clean = re.sub(r'\b\d+(?:\.\d+)?\s*ton\b', '', query, flags=re.IGNORECASE)
    clean = re.sub(r"(under|above|between|and|price|budget|range)\s+\d+", "", clean.lower())

    # Step 7: Tokenise
    raw_tokens = [
        t for t in re.findall(r"\w+", clean)
        if len(t) >= 2
        and not t.isdigit()
        and t.lower() not in FILLER_WORDS
    ]

    # Step 8: Category alias detection in tokens
    if not category:
        for token in raw_tokens:
            alias = CATEGORY_ALIASES.get(token.lower())
            if alias:
                products  = [p for p in products if p["category"] == alias]
                raw_tokens = [t for t in raw_tokens if t.lower() != token.lower()]
                break

    # Step 9: Mode C — filter-only (no meaningful tokens left)
    if not raw_tokens:
        if capacity_norm or lo is not None or hi is not None or category:
            return sorted(products, key=lambda p: p["price_pkr"])[:top_k]
        return []

    # Step 10: Mode B — keyword scoring
    norm_tokens   = [_normalize(t) for t in raw_tokens]
    norm_products = [_build_product_normalized(p) for p in products]

    scored = sorted(
        [(p, _score_keyword_query(p, np, raw_tokens, norm_tokens))
         for p, np in zip(products, norm_products)],
        key=lambda x: x[1], reverse=True
    )

    min_score = 1 if len(raw_tokens) == 1 else 2
    return [p for p, sc in scored if sc >= min_score][:top_k]


# ─── Context Builder for Groq ─────────────────────────────────────────────────

def build_context(products: list[dict]) -> str:
    if not products:
        return "No matching products found in the database."
    lines = []
    for p in products:
        lines.append(
            f"[{p['product_id']}] {p['product_name']} | "
            f"Brand: {p['brand']} | Model: {p['model_number']} | "
            f"Price: PKR {p['price_pkr']:,} | Capacity: {p['capacity']} | "
            f"Energy: {p['energy_rating']} | Warranty: {p['warranty_years']}yr | "
            f"Stock: {p['stock_status']} | Features: {p['key_features']} | "
            f"Description: {p['description']}"
        )
    return "\n".join(lines)