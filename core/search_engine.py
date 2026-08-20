import re
from core.query_classifier import classify, QueryType
from core.retriever import retrieve, build_context
from core.embedder import encode_query
from core.faiss_store import vector_search
from config import TOP_K, FAISS_TOP_K, RETRIEVER_WEIGHT, FAISS_WEIGHT

# Valid ID ranges
_ID_RANGES = {"AC": 60, "WM": 40, "RF": 40, "MW": 30, "WD": 20}


def _normalise(text: str) -> str:
    return re.sub(r'[\s\-_./#&()+]', '', text).lower()


def _lookup_by_product_id(pid: str, products: list[dict]):
    """Exact match by Product ID (case-insensitive)."""
    return next((p for p in products
                 if p.get("product_id", "").upper() == pid.upper()), None)


def _lookup_by_model(model_norm: str, products: list[dict]):
    """Exact match by normalised model number."""
    return next((p for p in products
                 if _normalise(p.get("model_number", "")) == model_norm), None)


def _detect_category(retriever_results: list[dict]) -> str | None:
    """
    FIX 1 — Category bleed prevention.
    If the retriever locked onto a single category, return it.
    Used to filter FAISS hits so stray products (e.g. a fridge in
    a microwave search) never enter the merger.
    """
    if not retriever_results:
        return None
    categories = {p["category"] for p in retriever_results}
    return next(iter(categories)) if len(categories) == 1 else None


def _hybrid_search(raw_query: str, products: list[dict], index) -> tuple:
    """
    Keyword + FAISS hybrid search.
    Returns (results, kw_hits, vec_hits).

    FIX 1: FAISS hits are filtered to the retriever's detected category
            so cross-category products never enter the merger.
    FIX 2: Minimum combined score threshold raised to 0.05 to prevent
            near-zero-score products appearing in results.
    FIX 5: FAISS hits are filtered by price range so vector search
            cannot bypass the price filter applied by the retriever.
    """
    from core.retriever import _parse_price_filter
    retriever_results = retrieve(raw_query, products, top_k=FAISS_TOP_K)

    query_vec  = encode_query(raw_query)
    faiss_hits = vector_search(query_vec, index, products, top_k=FAISS_TOP_K)

    # FIX 1: filter FAISS hits to matched category
    locked_category = _detect_category(retriever_results)
    if locked_category:
        faiss_hits = [
            h for h in faiss_hits
            if h["product"]["category"] == locked_category
        ]

    # FIX 5: apply price filter to FAISS hits so out-of-range products
    # cannot sneak in through the vector search side
    lo, hi = _parse_price_filter(raw_query)
    if lo is not None:
        faiss_hits = [h for h in faiss_hits if h["product"]["price_pkr"] >= lo]
    if hi is not None:
        faiss_hits = [h for h in faiss_hits if h["product"]["price_pkr"] <= hi]

    faiss_scores = {
        hit["product"]["product_id"]: hit["faiss_score"]
        for hit in faiss_hits
    }

    max_r = len(retriever_results) or 1
    retriever_scores = {
        p["product_id"]: 1.0 - (i / max_r) * 0.5
        for i, p in enumerate(retriever_results)
    }

    all_pids = set(retriever_scores) | set(faiss_scores)
    pid_map  = {p["product_id"]: p for p in products}
    scored   = []

    for pid in all_pids:
        if pid not in pid_map:
            continue
        r_score  = retriever_scores.get(pid, 0.0)
        f_score  = faiss_scores.get(pid, 0.0)
        combined = RETRIEVER_WEIGHT * r_score + FAISS_WEIGHT * f_score
        scored.append((pid_map[pid], combined, r_score, f_score))

    scored.sort(key=lambda x: x[1], reverse=True)

    # FIX 2: raised minimum threshold from 0.0 to 0.05
    final = [
        {**p,
         "_retriever_score": round(r, 4),
         "_faiss_score":     round(f, 4),
         "_combined_score":  round(c, 4)}
        for p, c, r, f in scored[:TOP_K] if c > 0.05
    ]
    return final, len(retriever_results), len(faiss_hits)


def search(raw_query: str, products: list[dict], index=None) -> dict:
    clf        = classify(raw_query)
    qtype      = clf["type"]
    product_id = clf["product_id"]
    model_norm = clf["model_norm"]

    # FIX 3: sanitise query for safe display (strip HTML-like chars)
    safe_query = re.sub(r'[<>]', '', raw_query).strip()

    print(f"[search] '{safe_query}' → type={qtype}  pid={product_id}  model={model_norm}")

    # ── GREETING ──────────────────────────────────────
    if qtype == QueryType.GREETING:
        return _resp(safe_query, qtype,
            "👋 Hello! I'm your home appliance assistant. "
            "I only answer questions about products in our dataset. "
            "Try **'Haier inverter AC 1.5 ton'**, **'Dawlance fridge under 80000'**, "
            "a product ID like **'AC001'**, or model number like **'GRE-AC-1001'**.",
            [])

    # ── OFF-TOPIC ─────────────────────────────────────
    if qtype == QueryType.OFF_TOPIC:
        return _resp(safe_query, qtype,
            "🏠 I only help with home appliance searches from our dataset. "
            "Try **'Samsung refrigerator'**, **'LG washing machine'**, "
            "or **'Gree AC 1.5 ton'**.",
            [])

    # ── UNCLEAR ───────────────────────────────────────
    if qtype == QueryType.UNCLEAR:
        return _resp(safe_query, qtype,
            "🔍 I couldn't find any appliance-related keywords in your query. "
            "Try **'inverter AC 1.5 ton'**, **'Dawlance fridge no frost'**, "
            "a product ID like **'AC001'**, or model like **'GRE-AC-1001'**.",
            [])

    # ── PRODUCT ID LOOKUP ─────────────────────────────
    if qtype == QueryType.PRODUCT_ID:
        m = re.match(r'^([A-Z]+)(\d+)$', product_id.upper())
        if m:
            prefix = m.group(1)
            number = int(m.group(2))
            max_n  = _ID_RANGES.get(prefix, 0)
            if number > max_n:
                valid_range = f"{prefix}001–{prefix}{max_n:03d}"
                return _resp(safe_query, qtype,
                    f"❌ **{product_id}** is out of range. "
                    f"Valid IDs for **{prefix}**: **{valid_range}**. "
                    f"Please check and try again.",
                    [])

        product = _lookup_by_product_id(product_id, products)
        if product:
            return _resp(safe_query, qtype, None, [product], kw=1, vec=0)
        else:
            return _resp(safe_query, qtype,
                f"❌ Product ID **{product_id}** not found in the dataset. "
                f"Please check the ID and try again.",
                [])

    # ── MODEL NUMBER LOOKUP ───────────────────────────
    if qtype == QueryType.MODEL_NUM:
        product = _lookup_by_model(model_norm, products)
        if product:
            return _resp(safe_query, qtype, None, [product], kw=1, vec=0)
        else:
            readable = raw_query.strip().upper()
            return _resp(safe_query, qtype,
                f"❌ Model number **{readable}** not found in the dataset. "
                f"Please check the model number and try again. "
                f"Example valid models: **GRE-AC-1001**, **HAI-WM-2016**, **DAW-RF-3005**.",
                [])

    # ── APPLIANCE HYBRID SEARCH ───────────────────────
    if index is not None:
        results, kw_hits, vec_hits = _hybrid_search(safe_query, products, index)
    else:
        results  = retrieve(safe_query, products)
        kw_hits  = len(results)
        vec_hits = 0

    print(f"[search] → {len(results)} results")

    # FIX 4: no results → suggest related categories based on query tokens
    if not results:
        suggestion = _suggest_category(safe_query)
        # Give a price-range hint if a price filter was used
        from core.retriever import _parse_price_filter
        lo, hi = _parse_price_filter(safe_query)
        if lo is not None and hi is not None:
            price_hint = "No products found between **PKR " + f"{lo:,}" + "** and **PKR " + f"{hi:,}" + "**. "
        elif hi is not None:
            cheapest = _cheapest_price(products, safe_query)
            if cheapest is not None:
                price_hint = ("No products found under **PKR " + f"{hi:,}" + "**. "
                              "Our lowest price is around **PKR " + f"{cheapest:,}" + "**. ")
            else:
                price_hint = "No products found under **PKR " + f"{hi:,}" + "**. "
        elif lo is not None:
            price_hint = "No products found above **PKR " + f"{lo:,}" + "**. "
        else:
            price_hint = "No appliances found matching **'" + safe_query + "'**. "
        return _resp(safe_query, qtype,
            "😕 " + price_hint + suggestion +
            "Try a brand like **'Haier'**, category like **'AC'** or **'fridge'**, "
            "price like **'under 80000'**, or a product ID like **'AC001'**.",
            [])

    return _resp(safe_query, qtype, None, results, kw_hits, vec_hits)


_CATEGORY_KEYWORDS = {
    "Air Conditioner": ["ac", "air", "cool", "ton", "inverter"],
    "Refrigerator":    ["fridge", "refrigerator", "freezer", "frost"],
    "Washing Machine": ["wash", "laundry", "washer", "kg"],
    "Microwave Oven":  ["microwave", "oven", "grill"],
    "Water Dispenser": ["dispenser", "water"],
}


def _cheapest_price(products: list[dict], query: str) -> int | None:
    """
    Returns the cheapest price in the category the query seems to be
    about (if detectable), else the cheapest price across all products.
    Used to give an accurate 'lowest price' hint instead of a hardcoded
    stale number.
    """
    q = query.lower()
    detected_category = None
    for category, keywords in _CATEGORY_KEYWORDS.items():
        if any(w in q for w in keywords):
            detected_category = category
            break

    pool = products
    if detected_category:
        scoped = [p for p in products if p["category"] == detected_category]
        if scoped:
            pool = scoped

    prices = [p["price_pkr"] for p in pool if p.get("price_pkr", 0) > 0]
    return min(prices) if prices else None


def _suggest_category(query: str) -> str:
    """
    FIX 4 helper: gives a context-aware hint when no results are found.
    Detects which category the user probably meant.
    """
    q = query.lower()
    if any(w in q for w in ["ac", "air", "cool", "ton", "inverter"]):
        return "For ACs, try **'Haier 1.5 ton inverter'** or search by ID **'AC001'**. "
    if any(w in q for w in ["fridge", "refrigerator", "freezer", "frost"]):
        return "For fridges, try **'Dawlance no frost fridge'** or **'RF001'**. "
    if any(w in q for w in ["wash", "laundry", "washer", "kg"]):
        return "For washing machines, try **'LG 8kg automatic'** or **'WM001'**. "
    if any(w in q for w in ["microwave", "oven", "grill"]):
        return "For microwaves, try **'Samsung 25L microwave'** or **'MW001'**. "
    if any(w in q for w in ["dispenser", "water"]):
        return "For dispensers, try **'Dawlance water dispenser'** or **'WD001'**. "
    return ""


def _resp(query, qtype, message, results, kw=0, vec=0):
    return {
        "query":        query,
        "query_type":   qtype,
        "message":      message,
        "results":      results,
        "result_count": len(results),
        "keyword_hits": kw,
        "vector_hits":  vec,
        "context":      build_context(results),
    }