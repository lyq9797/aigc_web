import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


# =========================
# Helper Functions
# =========================

def _get_env_int(name: str, default: int) -> int:
    """从环境变量获取整数值，解析失败时抛出异常"""
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"环境变量 {name} 必须为整数") from exc


def _get_env_str(name: str, default: str) -> str:
    """从环境变量获取字符串值"""
    return os.getenv(name, default)


def _path_from_env(name: str, default: str) -> Path:
    """从环境变量获取路径，自动展开波浪号"""
    return Path(os.getenv(name, default)).expanduser().resolve()


# =========================
# Settings Class
# =========================

@dataclass(frozen=True)
class Settings:
    """应用配置类，支持环境变量覆盖"""

    # =====================
    # 路径配置
    # =====================
    base_dir: Path = Path(__file__).resolve().parent.parent
    db_path: Path = base_dir / "aigc_web.db"

    # =====================
    # 安全配置
    # =====================
    secret_key: str = _get_env_str("AIGC_WEB_SECRET", "change-this-in-production")
    token_expire_hours: int = _get_env_int("AIGC_TOKEN_EXPIRE_HOURS", 24)

    # =====================
    # 词边界检测模型
    # =====================
    word_model_path: Path = _path_from_env("WORD_MODEL_PATH", "deberta_CRF(new)_best.pt")
    word_model_name: str = _get_env_str("WORD_MODEL_NAME", "microsoft/deberta-v3-base")
    word_boundary_backend_script: Path = _path_from_env(
        "WORD_BOUNDARY_BACKEND_SCRIPT",
        "work2/deberta_CRF(new)_single_text.py",
    )

    # =====================
    # 句子分割模型
    # =====================
    sentence_backend_script: Path = _path_from_env(
        "SENTENCE_BACKEND_SCRIPT",
        "work1/test_single_text.py",
    )

    # =====================
    # 运行模式
    # =====================
    debug: bool = os.getenv("AIGC_DEBUG", "false").lower() == "true"

    def validate(self) -> None:
        """验证配置有效性"""
        errors = []

        if self.secret_key == "change-this-in-production":
            errors.append("请在生产环境中设置 AIGC_WEB_SECRET")

        if self.token_expire_hours <= 0:
            errors.append("AIGC_TOKEN_EXPIRE_HOURS 必须为正整数")

        if self.debug:
            print("⚠️ 警告: 系统运行在调试模式，请勿用于生产环境")

        if errors:
            raise ValueError("; ".join(errors))

    def to_dict(self) -> dict:
        """导出配置（脱敏）"""
        return {
            "base_dir": str(self.base_dir),
            "db_path": str(self.db_path),
            "token_expire_hours": self.token_expire_hours,
            "word_model_path": str(self.word_model_path),
            "word_model_name": self.word_model_name,
            "debug": self.debug,
        }


# =========================
# Global Instance
# =========================

settings = Settings()
settings.validate()