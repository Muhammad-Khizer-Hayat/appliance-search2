"""
One-time / occasional script: rebuilds vector_store/faiss_index.bin
and vector_store/products.pkl using the Gemini embedding API.

Run this whenever:
  - You switch embedding providers (like right now — MiniLM -> Gemini)
  - Your product catalog (data/home_appliances_database.xlsx) changes

Usage:
    python scripts/rebuild_index.py
"""
import sys
import os

# Allow running this script directly from the scripts/ folder
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.data_loader import load_products
from core.faiss_store import build_and_save_index
from config import GEMINI_API_KEY


def main():
    if not GEMINI_API_KEY:
        print(
            "\n[rebuild_index] ERROR: GEMINI_API_KEY is not set.\n"
            "Add it to your .env file first, e.g.:\n"
            "    GEMINI_API_KEY=AIza...your_key_here\n"
        )
        sys.exit(1)

    print("[rebuild_index] Loading products from dataset...")
    products = load_products()

    print(f"[rebuild_index] Rebuilding FAISS index for {len(products)} products "
          f"using Gemini embeddings — this calls the API, so it needs internet access.")
    build_and_save_index(products)

    print("[rebuild_index] Done. vector_store/faiss_index.bin and "
          "vector_store/products.pkl have been regenerated.")


if __name__ == "__main__":
    main()
