"""
Lightweight fuzzy spell-corrector for appliance brands and category terms.
Uses difflib — no external dependencies.
"""
import re
from difflib import get_close_matches

# Known correct terms to match against
_BRANDS = [
    "haier", "dawlance", "kenwood", "samsung", "panasonic",
    "gree", "mitsubishi", "waves", "orient", "pel", "daikin",
    "sharp", "lg", "super asia",
]

_CATEGORIES = [
    "ac", "air conditioner", "fridge", "refrigerator",
    "washing machine", "washer", "microwave", "oven",
    "water dispenser", "dispenser",
]

_APPLIANCE_TERMS = [
    "inverter", "energy", "efficient", "capacity", "frost",
    "no frost", "automatic", "manual", "split", "window",
    "portable", "digital", "smart", "wifi", "turbo", "eco",
    "compressor", "warranty", "budget", "cheap", "price",
]

_VOCAB = _BRANDS + _CATEGORIES + _APPLIANCE_TERMS


def correct_query(query: str) -> tuple[str, list[str]]:
    """
    Attempt to fix misspelled words in query.
    Returns (corrected_query, list_of_corrections_made).

    Only corrects words that are NOT already valid vocab or numbers.
    Threshold: cutoff=0.75 so only clear typos get fixed (not random words).
    """
    words = query.split()
    corrected = []
    fixes = []

    for word in words:
        w_low = word.lower()
        # Skip numbers, short words, already-known words
        if w_low.isdigit() or len(w_low) <= 2 or w_low in _VOCAB:
            corrected.append(word)
            continue

        matches = get_close_matches(w_low, _VOCAB, n=1, cutoff=0.78)
        if matches and matches[0] != w_low:
            fixes.append(f"{word} → {matches[0]}")
            corrected.append(matches[0])
        else:
            corrected.append(word)

    return " ".join(corrected), fixes