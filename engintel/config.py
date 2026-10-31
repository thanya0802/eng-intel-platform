"""Central config. Every path/env var lives here so the GCP swap is one file."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("ENGINTEL_DATA_DIR", ROOT / "data"))
RAW_DIR = DATA_DIR / "raw"                 # stands in for gs://<project>-eng-raw
STRUCTURED_DIR = DATA_DIR / "structured"   # CSV drops for the daily structured ingest
INDEX_DIR = DATA_DIR / "index"
DB_PATH = Path(os.getenv("ENGINTEL_DB", DATA_DIR / "warehouse.db"))  # stands in for BigQuery eng_intel

PARSER_VERSION = "pdfplumber-v1"
CHUNK_TARGET_WORDS = 160      # ~200 tokens; synthetic docs are short. Use ~500 for real NTRS PDFs.
CHUNK_OVERLAP_WORDS = 30
MAX_DELIVERY_ATTEMPTS = 5     # mirrors the Pub/Sub dead_letter_policy
CHECKPOINT_EVERY = 5

EMBEDDER = os.getenv("EMBEDDER", "lsa")     # lsa (offline) | sbert
RERANK = os.getenv("RERANK", "0") == "1"   # cross-encoder rerank (needs sentence-transformers)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
USE_LLM = bool(GEMINI_API_KEY) and os.getenv("USE_LLM", "1") == "1"
