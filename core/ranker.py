from config import RETRIEVER_WEIGHT as KEYWORD_WEIGHT, FAISS_WEIGHT as VECTOR_WEIGHT, TOP_K


def merge_and_rank(
    vector_hits: list[dict],
    kw_scores: dict[int, float],
    products: list[dict],
    top_k: int = TOP_K,
) -> list[dict]:
    """
    Combine keyword and vector scores with configured weights.
    Adds any keyword-only hits that FAISS missed.
    Returns top_k results sorted by combined score descending.
    """
    scored: dict[str, dict] = {}

    # ── Seed with FAISS vector hits ───────────────────
    for hit in vector_hits:
        prod   = hit["product"]
        pid    = prod.get("Product ID", "")
        vec_s  = hit.get("vector_score", 0.0)
        kw_s   = hit.get("keyword_score", 0.0)
        combined = KEYWORD_WEIGHT * kw_s + VECTOR_WEIGHT * vec_s

        scored[pid] = {
            "product":       prod,
            "keyword_score": round(kw_s, 4),
            "vector_score":  round(vec_s, 4),
            "combined_score":round(combined, 4),
            "match_types":   _match_types(kw_s, vec_s),
        }

    # ── Add pure keyword hits FAISS may have missed ───
    for idx, kw_s in kw_scores.items():
        if kw_s == 0.0:
            continue
        prod = products[idx]
        pid  = prod.get("Product ID", "")
        if pid in scored:
            continue                           # already covered by FAISS
        combined = KEYWORD_WEIGHT * kw_s      # no vector score
        scored[pid] = {
            "product":        prod,
            "keyword_score":  round(kw_s, 4),
            "vector_score":   0.0,
            "combined_score": round(combined, 4),
            "match_types":    ["keyword"],
        }

    # ── Sort + slice ──────────────────────────────────
    ranked = sorted(scored.values(), key=lambda x: x["combined_score"], reverse=True)
    return ranked[:top_k]


def _match_types(kw_score: float, vec_score: float) -> list[str]:
    types = []
    if kw_score > 0.0:
        types.append("keyword")
    if vec_score > 0.15:
        types.append("vector")
    return types or ["semantic"]