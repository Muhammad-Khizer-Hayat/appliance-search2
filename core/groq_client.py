import os
import warnings
import logging

warnings.filterwarnings("ignore")
logging.getLogger("groq").setLevel(logging.ERROR)

from groq import Groq
from config import GROQ_API_KEY, GROQ_MODEL, GROQ_MAX_TOKENS
from core.query_classifier import QueryType

_client: Groq | None = None


def get_client() -> Groq:
    global _client
    if _client is None:
        _client = Groq(api_key=GROQ_API_KEY)
    return _client


def _get(r, *keys, default=""):
    """Get value from dict trying multiple key names — handles both
    serialised (from JS: 'name','price') and raw product ('product_name','price_pkr')."""
    for k in keys:
        v = r.get(k)
        if v is not None and v != "":
            return v
    return default


def _build_search_prompt(query: str, results: list[dict]) -> str:
    lines = []
    for i, r in enumerate(results[:5], 1):
        name     = _get(r, "name", "product_name")
        brand    = _get(r, "brand")
        category = _get(r, "category")
        capacity = _get(r, "capacity")
        energy   = _get(r, "energy_rating")
        price    = int(_get(r, "price", "price_pkr", default=0))
        warranty = int(_get(r, "warranty", "warranty_years", default=0))
        features = _get(r, "features", "key_features")
        stock    = _get(r, "stock_status")

        lines.append(
            f"{i}. {brand} — {name}\n"
            f"   Category: {category} | Capacity: {capacity} | "
            f"Energy: {energy} | Price: PKR {price:,} | Warranty: {warranty}yr\n"
            f"   Features: {str(features)[:120]}\n"
            f"   Stock: {stock}"
        )

    return (
        f"Customer searching for: \"{query}\"\n\n"
        f"Top matching home appliances:\n\n" + "\n".join(lines) +
        "\n\nWrite a helpful 2-3 sentence shopping recommendation. "
        "Mention the best pick and why. Note energy rating or price advantages. "
        "Keep it friendly and concise."
    )


def _build_detail_prompt(r: dict) -> str:
    name     = _get(r, "name", "product_name")
    brand    = _get(r, "brand")
    category = _get(r, "category")
    model    = _get(r, "model", "model_number")
    capacity = _get(r, "capacity")
    energy   = _get(r, "energy_rating")
    price    = int(_get(r, "price", "price_pkr", default=0))
    warranty = int(_get(r, "warranty", "warranty_years", default=0))
    features = _get(r, "features", "key_features")
    desc     = _get(r, "description")
    stock    = _get(r, "stock_status")

    return (
        f"Give a helpful 3-4 sentence summary for this home appliance:\n\n"
        f"Product:  {brand} {name}\n"
        f"Category: {category} | Model: {model}\n"
        f"Capacity: {capacity} | Energy Rating: {energy}\n"
        f"Price: PKR {price:,} | Warranty: {warranty} year(s)\n"
        f"Features: {features}\n"
        f"Description: {desc}\n"
        f"Stock: {stock}\n\n"
        "Include: what it's best suited for, standout features, value for money. "
        "Keep it practical and friendly."
    )


_SYSTEM = (
    "You are a home appliance shopping assistant for a Pakistani retailer. "
    "You ONLY answer questions about the home appliance products provided to you. "
    "You NEVER answer questions about yourself, your name, your creator, or any topic "
    "outside of home appliances. "
    "If the question is not about the provided products, respond ONLY with: "
    "'I can only help with home appliance searches. Try searching for a product like Haier AC or Dawlance fridge.' "
    "Brands in dataset: Haier, Dawlance, Kenwood, LG, Samsung, Panasonic, Gree, "
    "Mitsubishi, Waves, Super Asia, Orient, PEL, Daikin, Sharp. "
    "Prices are in PKR. Base your answer strictly on the product data given. Max 3 sentences."
)


def generate_answer_stream(query: str, results: list, query_type: str):
    """
    Generator — yields text chunks from Groq streaming API.
    Accepts results in any format (serialised from JS or raw product dicts).
    """
    if not GROQ_API_KEY:
        print("[groq_client] No API key set — skipping AI answer")
        return

    if not results:
        return

    # Single result → detailed product summary, multiple → shopping recommendation
    if len(results) == 1:
        prompt = _build_detail_prompt(results[0])
    else:
        prompt = _build_search_prompt(query, results)

    print(f"[groq_client] Streaming answer for: '{query}' ({len(results)} results)")

    try:
        stream = get_client().chat.completions.create(
            model=GROQ_MODEL,
            max_tokens=GROQ_MAX_TOKENS,
            temperature=0.7,
            stream=True,
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user",   "content": prompt},
            ],
        )
        for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta

    except Exception as e:
        print(f"[groq_client] Error: {e}")
        yield "AI recommendation unavailable at the moment."

def _build_compare_prompt(products: list[dict], query: str) -> str:
    lines = []
    for i, r in enumerate(products, 1):
        name     = _get(r, "name", "product_name")
        brand    = _get(r, "brand")
        capacity = _get(r, "capacity")
        energy   = _get(r, "energy_rating")
        price    = int(_get(r, "price", "price_pkr", default=0))
        warranty = int(_get(r, "warranty", "warranty_years", default=0))
        features = _get(r, "features", "key_features")
        stock    = _get(r, "stock_status")
        lines.append(
            f"Product {i}: {brand} {name}\n"
            f"  Price: PKR {price:,} | Capacity: {capacity} | Energy: {energy} | "
            f"Warranty: {warranty}yr | Stock: {stock}\n"
            f"  Features: {str(features)[:150]}"
        )

    context = "\n\n".join(lines)
    user_q  = f' (user asked: "{query}")' if query else ""
    return (
        f"Compare these {len(products)} home appliances side-by-side{user_q}:\n\n"
        f"{context}\n\n"
        "Write a concise 4-5 sentence comparison. "
        "Highlight key differences in price, energy efficiency, capacity, and features. "
        "Conclude with a clear recommendation for which type of buyer each product suits best. "
        "Keep it practical and friendly."
    )


def generate_compare_stream(products: list[dict], query: str = ""):
    """Generator — yields text chunks for side-by-side product comparison."""
    if not GROQ_API_KEY or not products:
        return

    prompt = _build_compare_prompt(products, query)
    print(f"[groq_client] Compare stream for {len(products)} products")

    try:
        stream = get_client().chat.completions.create(
            model=GROQ_MODEL,
            max_tokens=GROQ_MAX_TOKENS,
            temperature=0.6,
            stream=True,
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user",   "content": prompt},
            ],
        )
        for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta

    except Exception as e:
        print(f"[groq_client] Compare error: {e}")
        yield "Comparison unavailable at the moment."