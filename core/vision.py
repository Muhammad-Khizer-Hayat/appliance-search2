"""
Image -> search-query text, using Gemini's vision-capable model.
Reuses the same GEMINI_API_KEY already configured for embeddings.
"""
import base64
import requests
from config import GEMINI_API_KEY

_VISION_MODEL = "gemini-2.5-flash"   # fast + free-tier friendly, supports images
_ENDPOINT = (
    f"https://generativelanguage.googleapis.com/v1beta/models/"
    f"{_VISION_MODEL}:generateContent"
)

_ALLOWED_MIME = {
    "image/jpeg", "image/jpg", "image/png", "image/webp",
}
_MAX_BYTES = 8 * 1024 * 1024  # 8MB safety cap

_PROMPT = (
    "You are helping a home-appliance search engine. Look at this image and "
    "identify the home appliance shown (air conditioner, refrigerator, "
    "washing machine, microwave oven, or water dispenser). "
    "Reply with ONLY a short search-style phrase (5-10 words) describing the "
    "appliance type and visible attributes — e.g. 'inverter split air "
    "conditioner white wall mounted' or 'double door no frost refrigerator "
    "silver'. If the image is not a home appliance, reply with exactly: "
    "NOT_AN_APPLIANCE"
)


def describe_appliance_image(image_bytes: bytes, mime_type: str) -> str:
    """
    Sends the image to Gemini, returns a short search-query string.
    Raises ValueError for bad input, RuntimeError for API failures.
    """
    if not GEMINI_API_KEY:
        raise RuntimeError(
            "[vision] GEMINI_API_KEY is not set. Add it to your .env file "
            "(and Vercel's Environment Variables when deployed)."
        )
    if mime_type not in _ALLOWED_MIME:
        raise ValueError(f"Unsupported image type: {mime_type}. Use JPEG, PNG, or WEBP.")
    if len(image_bytes) > _MAX_BYTES:
        raise ValueError("Image too large (max 8MB).")

    b64_data = base64.b64encode(image_bytes).decode("utf-8")

    payload = {
        "contents": [{
            "parts": [
                {"text": _PROMPT},
                {"inline_data": {"mime_type": mime_type, "data": b64_data}},
            ]
        }],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 60,
        },
    }

    try:
        response = requests.post(
            _ENDPOINT,
            params={"key": GEMINI_API_KEY},
            json=payload,
            timeout=30,
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as exc:
        raise RuntimeError(f"[vision] Gemini API request failed: {exc}")

    data = response.json()
    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError):
        raise RuntimeError(f"[vision] Unexpected Gemini response shape: {data}")

    if text.upper().startswith("NOT_AN_APPLIANCE"):
        raise ValueError("NOT_AN_APPLIANCE")

    return text
