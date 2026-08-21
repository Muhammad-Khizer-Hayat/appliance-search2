"""
Image -> search-query text, using Gemini's vision-capable model.
Reuses the same GEMINI_API_KEY already configured for embeddings.
"""
import base64
import requests
from config import GEMINI_API_KEY

_LIST_MODELS_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models"

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

# Cached per warm serverless instance so we don't call ListModels on every request
_cached_model_name: str | None = None


def _pick_vision_model() -> str:
    """
    Ask Gemini which models are currently available and pick a working
    flash-family model that supports generateContent. Avoids hardcoding a
    model name that Google might retire later.
    """
    global _cached_model_name
    if _cached_model_name:
        return _cached_model_name

    response = requests.get(
        _LIST_MODELS_ENDPOINT,
        headers={"x-goog-api-key": GEMINI_API_KEY},
        timeout=15,
    )
    response.raise_for_status()
    models = response.json().get("models", [])

    candidates = [
        m["name"].removeprefix("models/")
        for m in models
        if "generateContent" in m.get("supportedGenerationMethods", [])
    ]

    flash_candidates = [m for m in candidates if "flash" in m and "flash-lite" not in m]
    pick = (flash_candidates or candidates or [None])[0]

    if not pick:
        raise RuntimeError(
            "[vision] No Gemini model supporting generateContent was found "
            "for this API key."
        )

    _cached_model_name = pick
    print(f"[vision] Using Gemini model: {pick}")
    return pick


def describe_appliance_image(image_bytes: bytes, mime_type: str) -> str:
    """
    Sends the image to Gemini and returns a short search-query string.
    """
    if not GEMINI_API_KEY:
        raise RuntimeError(
            "[vision] GEMINI_API_KEY is not set."
        )

    if mime_type not in _ALLOWED_MIME:
        raise ValueError(
            f"Unsupported image type: {mime_type}. "
            "Use JPEG, PNG, or WEBP."
        )

    if len(image_bytes) > _MAX_BYTES:
        raise ValueError("Image too large (max 8MB).")

    # Use the confirmed stable vision model
    model_name = "gemini-3.6-flash"

    endpoint = (
        f"https://generativelanguage.googleapis.com/v1beta/"
        f"models/{model_name}:generateContent"
    )

    b64_data = base64.b64encode(image_bytes).decode("utf-8")

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "text": _PROMPT
                    },
                    {
                        "inline_data": {
                            "mime_type": mime_type,
                            "data": b64_data
                        }
                    }
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 256
        }
    }

    try:
        response = requests.post(
            endpoint,
            headers={
                "x-goog-api-key": GEMINI_API_KEY,
                "Content-Type": "application/json"
            },
            json=payload,
            timeout=60
        )

        # IMPORTANT: show Google's actual error
        if not response.ok:
            print("========== GEMINI ERROR ==========")
            print("Status:", response.status_code)
            print("URL:", endpoint)
            print("Response:", response.text)
            print("===================================")

        response.raise_for_status()

    except requests.exceptions.RequestException as exc:
        raise RuntimeError(
            f"[vision] Gemini API request failed: {exc}"
        )

    try:
        data = response.json()

        text = (
            data["candidates"][0]
            ["content"]["parts"][0]
            ["text"]
            .strip()
        )

    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise RuntimeError(
            f"[vision] Unexpected Gemini response: {data}"
        ) from exc

    if text.upper().startswith("NOT_AN_APPLIANCE"):
        raise ValueError("NOT_AN_APPLIANCE")

    return text