import os
import warnings
import logging
import numpy as np
from sentence_transformers import SentenceTransformer
from config import EMBEDDING_MODEL

# ── Silence ALL HuggingFace / transformers warnings ──────────────────────────
os.environ["HF_HUB_OFFLINE"]              = "1"
os.environ["TRANSFORMERS_OFFLINE"]        = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"]   = "1"
os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
os.environ["TOKENIZERS_PARALLELISM"]      = "false"

# Suppress Python warnings from transformers / sentence-transformers
warnings.filterwarnings("ignore", message=".*position_ids.*")
warnings.filterwarnings("ignore", message=".*UNEXPECTED.*")
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

# Suppress logging from transformers library
logging.getLogger("transformers").setLevel(logging.ERROR)
logging.getLogger("sentence_transformers").setLevel(logging.ERROR)
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)



_model: SentenceTransformer | None = None


def get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        print(f"[embedder] Loading from local cache: {EMBEDDING_MODEL} ...")
        _model = SentenceTransformer(EMBEDDING_MODEL, local_files_only=True)
        print("[embedder] Model ready.")
    return _model


def encode_texts(texts: list[str]) -> np.ndarray:
    """Encode list of strings → L2-normalised float32 array (N x D)."""
    return get_model().encode(
        texts,
        batch_size=64,
        show_progress_bar=False,
        normalize_embeddings=True,
        convert_to_numpy=True,
    ).astype("float32")


def encode_query(query: str) -> np.ndarray:
    """Single query → shape (1, D) float32."""
    return encode_texts([query])