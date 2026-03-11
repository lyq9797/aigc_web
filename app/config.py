import os
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "aigc_web.db"
SECRET_KEY = os.getenv("AIGC_WEB_SECRET", "change-this-in-production")
TOKEN_EXPIRE_HOURS = int(os.getenv("AIGC_TOKEN_EXPIRE_HOURS", "24"))

WORD_MODEL_PATH = Path(os.getenv("WORD_MODEL_PATH", r"deberta_CRF(new)_best.pt")).expanduser()
WORD_MODEL_NAME = os.getenv("WORD_MODEL_NAME", "microsoft/deberta-v3-base")
WORD_BOUNDARY_BACKEND_SCRIPT = Path(
    os.getenv("WORD_BOUNDARY_BACKEND_SCRIPT", r"work2\\deberta_CRF(new)_single_text.py")
).expanduser()

SENTENCE_BACKEND_SCRIPT = Path(
    os.getenv("SENTENCE_BACKEND_SCRIPT", r"work1\\test_single_text.py")
).expanduser()


def get_env_int(key: str, default: int) -> int:
    value = os.getenv(key)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        raise ValueError(f"Environment variable {key} must be an integer")


def validate_paths(*paths: Path) -> None:
    for path in paths:
        if path.exists() and not path.is_file():
            raise ValueError(f"Expected file path but got directory: {path}")
