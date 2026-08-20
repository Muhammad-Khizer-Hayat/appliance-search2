import os
from dotenv import load_dotenv

load_dotenv()

# ── Groq ──────────────────────────────────────────────
GROQ_API_KEY    = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL      = "openai/gpt-oss-20b"
GROQ_MAX_TOKENS = 512
 
# ── Flask ─────────────────────────────────────────────
FLASK_DEBUG = os.getenv("FLASK_DEBUG", "True") == "True"
FLASK_PORT  = int(os.getenv("FLASK_PORT", 5000))

# ── Paths ─────────────────────────────────────────────
BASE_DIR          = os.path.dirname(os.path.abspath(__file__))
DATA_PATH         = os.path.join(BASE_DIR, "data", "home_appliances_database.xlsx")
VECTOR_STORE_DIR  = os.path.join(BASE_DIR, "vector_store")
FAISS_INDEX_PATH  = os.path.join(VECTOR_STORE_DIR, "faiss_index.bin")
PRODUCTS_PKL_PATH = os.path.join(VECTOR_STORE_DIR, "products.pkl")

# ── Embedding ─────────────────────────────────────────
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

# ── Search weights ────────────────────────────────────
# How much each source contributes to the final hybrid score
RETRIEVER_WEIGHT = 0.50    # smart keyword/filter retriever
FAISS_WEIGHT     = 0.50    # semantic vector similarity

TOP_K       = 10   # final results returned to UI
FAISS_TOP_K = 30   # candidates pulled from FAISS before re-ranking