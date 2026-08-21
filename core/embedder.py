import time
import numpy as np
import requests
from config import GEMINI_API_KEY, GEMINI_EMBEDDING_MODEL, GEMINI_EMBEDDING_DIM

_BATCH_ENDPOINT = (
    f"https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_EMBEDDING_MODEL}:batchEmbedContents"
)
_SINGLE_ENDPOINT = (
    f"https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_EMBEDDING_MODEL}:embedContent"
)

_BATCH_SIZE = 100          # Gemini batchEmbedContents accepts up to 100 per call
_MAX_RETRIES = 3
_RETRY_DELAY_SECONDS = 2


def _post_with_retry(url: str, payload: dict) -> dict:
    """POST to Gemini with a couple of retries for transient errors/rate limits."""
    last_error = None
    for attempt in range(_MAX_RETRIES):
        try:
            response = requests.post(
                url,
                headers={"x-goog-api-key": GEMINI_API_KEY},
                json=payload,
                timeout=30,
            )
            if response.status_code == 429:
                # Rate limited -- back off and retry
                time.sleep(_RETRY_DELAY_SECONDS * (attempt + 1))
                continue
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as exc:
            last_error = exc
            time.sleep(_RETRY_DELAY_SECONDS)
    raise RuntimeError(f"[embedder] Gemini API request failed after retries: {last_error}")


def _normalize(vec: np.ndarray) -> np.ndarray:
    """L2-normalise a single vector (so FAISS IndexFlatIP acts like cosine similarity)."""
    norm = np.linalg.norm(vec)
    if norm == 0:
        return vec
    return vec / norm


def _require_key():
    if not GEMINI_API_KEY:
        raise RuntimeError(
            "[embedder] GEMINI_API_KEY is not set. Add it to your .env file "
            "(and to your Vercel project's Environment Variables when deploying)."
        )


def encode_texts(texts: list[str]) -> np.ndarray:
    """
    Encode a list of strings -> L2-normalised float32 array (N x D).
    Uses Gemini's batchEmbedContents so the whole product catalog
    can be embedded in a handful of API calls instead of one per item.
    """
    _require_key()

    all_vectors: list[list[float]] = []

    for start in range(0, len(texts), _BATCH_SIZE):
        chunk = texts[start:start + _BATCH_SIZE]
        payload = {
            "requests": [
                {
                    "model": f"models/{GEMINI_EMBEDDING_MODEL}",
                    "content": {"parts": [{"text": t}]},
                    "outputDimensionality": GEMINI_EMBEDDING_DIM,
                }
                for t in chunk
            ]
        }
        data = _post_with_retry(_BATCH_ENDPOINT, payload)
        embeddings = data.get("embeddings", [])
        if len(embeddings) != len(chunk):
            raise RuntimeError(
                f"[embedder] Expected {len(chunk)} embeddings, got {len(embeddings)}"
            )
        for item in embeddings:
            all_vectors.append(item["values"])

        print(f"[embedder] Encoded {min(start + _BATCH_SIZE, len(texts))}/{len(texts)}")

    arr = np.array(all_vectors, dtype="float32")
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    norms[norms == 0] = 1
    arr = arr / norms
    return arr.astype("float32")


def encode_query(query: str) -> np.ndarray:
    """Single query -> shape (1, D) float32, L2-normalised."""
    _require_key()

    payload = {
        "content": {"parts": [{"text": query}]},
        "outputDimensionality": GEMINI_EMBEDDING_DIM,
    }
    data = _post_with_retry(_SINGLE_ENDPOINT, payload)
    vec = np.array(data["embedding"]["values"], dtype="float32")
    vec = _normalize(vec)
    return vec.reshape(1, -1)