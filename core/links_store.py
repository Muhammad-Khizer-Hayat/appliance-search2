"""
Manages shop links (Daraz, Amazon, custom) for each product.
All links stored in data/product_links.json — no extra DB needed.
"""
import os
import json
import threading

_LINKS_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "product_links.json")
_lock = threading.Lock()


def _load() -> dict:
    if not os.path.exists(_LINKS_PATH):
        return {}
    try:
        with open(_LINKS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save(data: dict) -> None:
    os.makedirs(os.path.dirname(_LINKS_PATH), exist_ok=True)
    with open(_LINKS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_all_links() -> dict:
    """Return full links dict {product_id: {daraz, amazon, custom, custom_label}}"""
    with _lock:
        return _load()


def get_product_links(product_id: str) -> dict:
    """Return links for a single product, or empty dict."""
    with _lock:
        return _load().get(product_id, {})


def set_product_links(product_id: str, daraz: str = "",
                      amazon: str = "", custom: str = "",
                      custom_label: str = "") -> dict:
    """Save/update links for a product. Pass empty string to clear a link."""
    with _lock:
        data = _load()
        entry = {
            "daraz":        daraz.strip(),
            "amazon":       amazon.strip(),
            "custom":       custom.strip(),
            "custom_label": custom_label.strip() or "Buy Now",
        }
        # Remove empty links
        entry = {k: v for k, v in entry.items() if v}
        if "custom" in entry and "custom_label" not in entry:
            entry["custom_label"] = "Buy Now"

        if entry and any(entry.get(k) for k in ["daraz", "amazon", "custom"]):
            data[product_id] = entry
        else:
            data.pop(product_id, None)
        _save(data)
        return entry


def delete_product_links(product_id: str) -> None:
    with _lock:
        data = _load()
        data.pop(product_id, None)
        _save(data)


def get_stats() -> dict:
    with _lock:
        data = _load()
        return {
            "total_linked": len(data),
            "daraz_count":  sum(1 for v in data.values() if v.get("daraz")),
            "amazon_count": sum(1 for v in data.values() if v.get("amazon")),
            "custom_count": sum(1 for v in data.values() if v.get("custom")),
        }