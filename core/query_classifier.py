import re

# ── Greeting patterns ─────────────────────────────────
_GREETINGS_RE = re.compile(
    r'^(hi+|hello+|hey+|helo+|hii+|good\s*(morning|evening|night|afternoon)'
    r'|how are you|how r u|whats up|what\'s up'
    r'|salam|assalam|assalamualaikum|walaikum'
    r'|howdy|greetings|sup|yo|hai'
    r'|what is your name|what\'s your name|who are you|what are you'
    r'|are you an ai|are you a bot|who made you|who created you'
    r'|what can you do|help me|tell me about yourself)\W*$',
    re.IGNORECASE
)

# ── Off-topic patterns ────────────────────────────────
_OFF_TOPIC_RE = re.compile(
    r'\b(python|java|javascript|c\+\+|coding|programming|algorithm'
    r'|history|geography|politics|sport|cricket|football|hockey'
    r'|movie|film|music|song|recipe|food|cook|bake|restaurant'
    r'|weather|news|joke|poem|story|essay|novel'
    r'|capital of|president|prime minister'
    r'|how to program|software|hardware|laptop'
    r'|biology|chemistry|physics|math|calculus'
    r'|who is [a-z]'
    r'|your name|your creator|made you|built you'
    r'|chatgpt|openai|anthropic|gemini|claude)\b',
    re.IGNORECASE
)

# ── Appliance keywords ────────────────────────────────
_APPLIANCE_KW = {
    "ac","air","conditioner","cooling","fridge","refrigerator",
    "freezer","frost","washing","washer","laundry","microwave",
    "oven","dispenser","water","haier","dawlance","kenwood","lg",
    "samsung","panasonic","gree","mitsubishi","waves","orient",
    "pel","daikin","sharp","inverter","energy","star","ton","kg",
    "automatic","manual","heat","wifi","smart","turbo","eco",
    "budget","price","cheap","warranty","split","window","portable",
    "1.5","2.5","double","single","under","above","between",
    # additional useful terms
    "capacity","watt","litre","liter","door","frost","no-frost",
    "digital","timer","remote","compressor","brand","model",
    "super asia","waves","pel","pak","orient","refrigeration",
}

# ── Valid product ID prefixes & max numbers ───────────
_ID_RANGES = {
    "AC": 60, "WM": 40, "RF": 40, "MW": 30, "WD": 20
}

# ── Model number pattern ──────────────────────────────
_MODEL_NORM_RE = re.compile(
    r'^[a-z]{2,5}[a-z]{1,5}\d{3,6}$'
)


class QueryType:
    PRODUCT_ID = "product_id"
    MODEL_NUM  = "model_num"
    APPLIANCE  = "appliance"
    GREETING   = "greeting"
    OFF_TOPIC  = "off_topic"
    UNCLEAR    = "unclear"


def _normalise(text: str) -> str:
    """Remove all separators and lowercase."""
    return re.sub(r'[\s\-_./#&()+]', '', text).lower()


def _try_product_id(query: str):
    """
    Try to parse query as a product ID.
    Valid formats  : AC001, AC21, AC1, AC01  (prefix + 1–3 digits)
    Invalid formats: AC0021, AC00021         (prefix + 4+ digits)

    The key rule: only 1–3 digit characters are allowed after the prefix.
    This prevents AC0021 from silently collapsing to AC021.
    """
    q = query.strip().upper().replace(' ', '').replace('-', '')
    m = re.match(r'^(AC|WM|RF|MW|WD)(\d{1,3})$', q)
    if not m:
        return None
    prefix = m.group(1)
    number = int(m.group(2))
    if number == 0:          # AC000 is not a valid product
        return None
    return f"{prefix}{number:03d}", number, prefix


def classify(query: str) -> dict:
    """
    Classifies the query into one of six types.
    Returns dict:
    {
        "type":       QueryType.X,
        "product_id": "AC023" | None,
        "model_norm": "greac1001" | None
    }

    Order of checks:
    1. Empty
    2. Greeting / identity questions
    3. Product ID
    4. Model number
    5. Off-topic
    6. No appliance keyword at all → UNCLEAR  ← KEY FIX
    7. Normal appliance search
    """
    q = query.strip()

    # 1. Empty query
    if not q:
        return {"type": QueryType.UNCLEAR, "product_id": None, "model_norm": None}

    # 2. Greeting / identity
    if _GREETINGS_RE.match(q):
        return {"type": QueryType.GREETING, "product_id": None, "model_norm": None}

    # 3. Product ID — try the whole query first
    pid_result = _try_product_id(q)
    if pid_result:
        pid, number, prefix = pid_result
        return {"type": QueryType.PRODUCT_ID, "product_id": pid, "model_norm": None}

    # 4. Model number — normalise entire query and check pattern
    q_norm = _normalise(q)
    if _MODEL_NORM_RE.match(q_norm):
        return {"type": QueryType.MODEL_NUM, "product_id": None, "model_norm": q_norm}

    # Also check each token for embedded model number
    for token in q.split():
        t_norm = _normalise(token)
        if _MODEL_NORM_RE.match(t_norm) and len(t_norm) >= 7:
            return {"type": QueryType.MODEL_NUM, "product_id": None, "model_norm": t_norm}

    # 5. Off-topic
    if _OFF_TOPIC_RE.search(q):
        return {"type": QueryType.OFF_TOPIC, "product_id": None, "model_norm": None}

    # 6. KEY FIX: any query with zero appliance keywords → UNCLEAR
    #    Uses word-boundary token matching (not substring) so "ac0021" does NOT
    #    match the keyword "ac" — only a standalone word "ac" counts.
    #    e.g. "what is your name", "ac0021", "who are you" all caught here.
    q_tokens = set(re.findall(r'\b\w+\b', q.lower()))
    has_kw = any(kw in q_tokens for kw in _APPLIANCE_KW)
    if not has_kw:
        return {"type": QueryType.UNCLEAR, "product_id": None, "model_norm": None}

    # 7. Normal appliance search
    return {"type": QueryType.APPLIANCE, "product_id": None, "model_norm": None}