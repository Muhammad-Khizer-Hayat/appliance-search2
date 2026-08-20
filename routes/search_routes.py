import time
import json
import traceback
from collections import defaultdict
from flask import Blueprint, request, jsonify, current_app, Response, stream_with_context

from core.search_engine import search
from core.groq_client import generate_answer_stream, generate_compare_stream
from core.query_classifier import QueryType
from core.cache import cache_get, cache_set, cache_stats
from core.query_logger import log_query, get_stats
from core.spell_correct import correct_query
from core.links_store import get_all_links

search_bp = Blueprint("search", __name__)

# ── Simple in-process rate limiter ─────────────────────
_rate_buckets: dict = defaultdict(list)
_RATE_LIMIT   = 30   # requests
_RATE_WINDOW  = 60   # seconds

def _is_rate_limited(ip: str) -> bool:
    now    = time.time()
    _rate_buckets[ip] = [t for t in _rate_buckets[ip] if now - t < _RATE_WINDOW]
    if len(_rate_buckets[ip]) >= _RATE_LIMIT:
        return True
    _rate_buckets[ip].append(now)
    return False


# ── Route 1: Fast hybrid search ────────────────────────
@search_bp.route("/api/search", methods=["POST"])
def api_search():
    ip = request.remote_addr or "unknown"
    if _is_rate_limited(ip):
        return jsonify({"error": "Rate limit exceeded. Please wait a moment."}), 429

    try:
        data  = request.get_json(silent=True) or {}
        query = (data.get("query") or "").strip()

        if not query:
            return jsonify({"error": "Query is required"}), 400
        if len(query) > 300:
            return jsonify({"error": "Query too long"}), 400

        # Spell correction
        corrected_query, fixes = correct_query(query)
        was_corrected = len(fixes) > 0

        # Cache lookup
        cache_key  = corrected_query.lower().strip()
        cached_hit = cache_get(cache_key)
        if cached_hit:
            log_query(query, cached_hit["query_type"],
                      cached_hit["result_count"], 0,
                      from_cache=True, corrected=corrected_query if was_corrected else "")
            payload = dict(cached_hit)
            payload["from_cache"]       = True
            payload["spell_correction"] = fixes
            return jsonify(payload)

        # Live search
        products = current_app.products
        index    = current_app.faiss_index

        t0         = time.perf_counter()
        result     = search(raw_query=corrected_query, products=products, index=index)
        elapsed_ms = round((time.perf_counter() - t0) * 1000)
        elapsed_display = elapsed_ms if elapsed_ms > 0 else "<1"

        all_links  = get_all_links()
        serialised = []
        for p in result["results"]:
            qtype    = result.get("query_type", "")
            is_exact = qtype in (QueryType.PRODUCT_ID, QueryType.MODEL_NUM)
            combined  = p.get("_combined_score",  1.0 if is_exact else 0.0)
            retriever = p.get("_retriever_score", 1.0 if is_exact else 0.0)
            faiss     = p.get("_faiss_score",     0.0)

            serialised.append({
                "product_id":      p.get("product_id",      ""),
                "name":            p.get("product_name",    ""),
                "brand":           p.get("brand",           ""),
                "category":        p.get("category",        ""),
                "model":           p.get("model_number",    ""),
                "capacity":        p.get("capacity",        ""),
                "energy_rating":   p.get("energy_rating",   ""),
                "price":           int(p.get("price_pkr",       0)),
                "warranty":        int(p.get("warranty_years",  0)),
                "color":           p.get("color",           ""),
                "features":        p.get("key_features",    ""),
                "stock_status":    p.get("stock_status",    ""),
                "description":     p.get("description",     ""),
                "retriever_score": round(retriever, 4),
                "faiss_score":     round(faiss,     4),
                "combined_score":  round(combined,  4),
                "shop_links":      all_links.get(p.get("product_id", ""), {}),
            })

        payload = {
            "query":            corrected_query,
            "original_query":   query,
            "query_type":       result["query_type"],
            "message":          result["message"],
            "result_count":     len(serialised),
            "keyword_hits":     result.get("keyword_hits", 0),
            "vector_hits":      result.get("vector_hits",  0),
            "elapsed_ms":       elapsed_display,
            "results":          serialised,
            "from_cache":       False,
            "spell_correction": fixes,
        }

        if result["query_type"] not in (QueryType.GREETING, QueryType.OFF_TOPIC, QueryType.UNCLEAR):
            cache_set(cache_key, payload)

        log_query(query, result["query_type"], len(serialised), elapsed_ms,
                  corrected=corrected_query if was_corrected else "")

        return jsonify(payload)

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e), "detail": traceback.format_exc()}), 500


# ── Route 2: Streaming Groq AI answer ──────────────────
@search_bp.route("/api/ai-answer", methods=["POST"])
def api_ai_answer():
    try:
        data       = request.get_json(silent=True) or {}
        query      = (data.get("query")      or "").strip()
        query_type = (data.get("query_type") or "appliance").strip()
        results    =  data.get("results",    [])

        if query_type in (QueryType.GREETING, QueryType.OFF_TOPIC, QueryType.UNCLEAR):
            return jsonify({"answer": ""}), 200
        if not query or not results:
            return jsonify({"answer": ""}), 200

        def generate():
            try:
                for chunk in generate_answer_stream(query, results, query_type):
                    yield f"data: {json.dumps({'chunk': chunk})}\n\n"
            except Exception as e:
                print(f"[ai-answer] stream error: {e}")
                traceback.print_exc()
            finally:
                yield "data: [DONE]\n\n"

        return Response(
            stream_with_context(generate()),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# ── Route 3: Compare products (streaming) ──────────────
@search_bp.route("/api/compare", methods=["POST"])
def api_compare():
    try:
        data     = request.get_json(silent=True) or {}
        products = data.get("products", [])
        query    = (data.get("query") or "").strip()

        if len(products) < 2:
            return jsonify({"error": "Select at least 2 products to compare."}), 400
        if len(products) > 3:
            return jsonify({"error": "Compare supports up to 3 products."}), 400

        def generate():
            try:
                for chunk in generate_compare_stream(products, query):
                    yield f"data: {json.dumps({'chunk': chunk})}\n\n"
            except Exception as e:
                print(f"[compare] stream error: {e}")
                traceback.print_exc()
            finally:
                yield "data: [DONE]\n\n"

        return Response(
            stream_with_context(generate()),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# ── Route 4: Analytics ─────────────────────────────────
@search_bp.route("/api/stats", methods=["GET"])
def api_analytics():
    return jsonify({
        "cache":   cache_stats(),
        "queries": get_stats(limit=10),
    })