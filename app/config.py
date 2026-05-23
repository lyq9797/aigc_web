import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "aigc_web.db"
SECRET_KEY = os.getenv("AIGC_WEB_SECRET", "change-this-in-production")
TOKEN_EXPIRE_HOURS = int(os.getenv("AIGC_TOKEN_EXPIRE_HOURS", "24"))

# External model paths (can be changed via env vars)
WORD_MODEL_PATH = os.getenv(
    "WORD_MODEL_PATH",
    r"deberta_CRF(new)_best.pt",
)
WORD_MODEL_NAME = os.getenv("WORD_MODEL_NAME", "microsoft/deberta-v3-base")
WORD_BOUNDARY_BACKEND_SCRIPT = os.getenv(
    "WORD_BOUNDARY_BACKEND_SCRIPT",
    r"work2\\deberta_CRF(new)_single_text.py",
)

# Sentence-level backend placeholder path (referenced for compatibility notes)
SENTENCE_BACKEND_SCRIPT = os.getenv(
    "SENTENCE_BACKEND_SCRIPT",
    r"work1\\test_single_text.py",
)
