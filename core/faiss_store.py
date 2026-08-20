import os
import pickle
import faiss
import numpy as np
from config import FAISS_INDEX_PATH, PRODUCTS_PKL_PATH, VECTOR_STORE_DIR, FAISS_TOP_K
from core.embedder import encode_texts


def _combined_text(p: dict) -> str:
    """
    Build the text string that gets embedded for each product.
    Brand + category + name repeated for higher weight.
    """
    return (
        f"{p['brand']} {p['brand']} "
        f"{p['category']} {p['category']} "
        f"{p['product_name']} {p['product_name']} "
        f"{p['capacity']} {p['energy_rating']} "
        f"{p['key_features']} {p['description']}"
    ).lower()


def build_and_save_index(products: list[dict]) -> faiss.Index:
    """Encode all products, build FAISS IndexFlatIP, save to disk."""
    os.makedirs(VECTOR_STORE_DIR, exist_ok=True)

    texts = [_combined_text(p) for p in products] # ---> converts all products into searchable text
    print(f"[faiss_store] Encoding {len(texts)} products ...")
    embeddings = encode_texts(texts) # ---> converts all text int vectors

    dim   = embeddings.shape[1] # ---> get emmbedding size
    index = faiss.IndexFlatIP(dim)     # cosine (vectors are L2-normalised)
    index.add(embeddings)

    faiss.write_index(index, FAISS_INDEX_PATH)
    with open(PRODUCTS_PKL_PATH, "wb") as f:
        pickle.dump(products, f)

    print(f"[faiss_store] Saved — {index.ntotal} vectors, dim={dim}")
    return index   # return Saved Datbase from disk that i stored


def load_index() -> tuple[faiss.Index, list[dict]]:
    """Load index + product list from disk."""
    index = faiss.read_index(FAISS_INDEX_PATH)
    with open(PRODUCTS_PKL_PATH, "rb") as f:
        products = pickle.load(f)
    print(f"[faiss_store] Loaded — {index.ntotal} vectors")
    return index, products


def index_is_valid() -> bool:
    try:
        return (
            os.path.exists(FAISS_INDEX_PATH) and
            os.path.exists(PRODUCTS_PKL_PATH) and
            os.path.getsize(FAISS_INDEX_PATH) > 0 and
            os.path.getsize(PRODUCTS_PKL_PATH) > 0
        )
    except OSError:
        return False


def vector_search(query_embedding: np.ndarray,
                  index: faiss.Index,
                  products: list[dict],
                  top_k: int = FAISS_TOP_K) -> list[dict]:
    """
    Search FAISS index.
    Returns list of {product, faiss_score} sorted descending.
    """
    distances, indices = index.search(query_embedding, top_k)
    results = []
    for dist, idx in zip(distances[0], indices[0]):
        if idx == -1:
            continue
        results.append({
            "product":     products[idx],
            "faiss_score": float(dist),   # cosine similarity 0–1
        })
    return results