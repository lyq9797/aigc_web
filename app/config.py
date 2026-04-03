import os
from dataclasses import dataclass
from pathlib import Path


def _get_env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"环境变量 {name} 必须为整数") from exc


def _path_from_env(name: str, default: str) -> Path:
    return Path(os.getenv(name, default)).expanduser()


@dataclass(frozen=True)
class Settings:
    base_dir: Path = Path(__file__).resolve().parent.parent
    db_path: Path = Path(__file__).resolve().parent.parent / "aigc_web.db"
    secret_key: str = os.getenv("AIGC_WEB_SECRET", "change-this-in-production")
    token_expire_hours: int = _get_env_int("AIGC_TOKEN_EXPIRE_HOURS", 24)
    word_model_path: Path = _path_from_env("WORD_MODEL_PATH", r"deberta_CRF(new)_best.pt")
    word_model_name: str = os.getenv("WORD_MODEL_NAME", "microsoft/deberta-v3-base")
    word_boundary_backend_script: Path = _path_from_env(
        "WORD_BOUNDARY_BACKEND_SCRIPT",
        r"work2\\deberta_CRF(new)_single_text.py",
    )
    sentence_backend_script: Path = _path_from_env(
        "SENTENCE_BACKEND_SCRIPT",
        r"work1\\test_single_text.py",
    )

    def validate(self) -> None:
        if self.secret_key == "change-this-in-production":
            raise ValueError("请在生产环境中设置 AIGC_WEB_SECRET")
        if self.token_expire_hours <= 0:
            raise ValueError("AIGC_TOKEN_EXPIRE_HOURS 必须为正整数")


settings = Settings()
settings.validate()
