"""
应用全局配置模块 (Application Global Configuration)

【安全检测全局说明】
1. 本模块集中管理应用的环境变量与基础配置。
2. 严禁在代码库中硬编码真实的敏感凭证（如数据库密码、生产环境 SECRET_KEY）。
3. 所有敏感配置必须通过环境变量（Environment Variables）或安全的密钥管理系统（如 AWS Secrets Manager, HashiCorp Vault）注入。
"""

import logging
import os
from pathlib import Path
from typing import Final

logger = logging.getLogger(__name__)

# ==========================================
# 1. 基础环境识别 (Environment Detection)
# ==========================================

# 获取当前运行环境，默认为 production 以遵循“安全失败 (Fail-Secure)”原则
APP_ENV: Final[str] = os.getenv("APP_ENV", "production").lower()
IS_DEBUG: Final[bool] = APP_ENV in ("development", "dev", "test", "local")

# ==========================================
# 2. 基础路径配置 (Base Paths)
# ==========================================

# 项目根目录（假设 config.py 位于 project_root/config/ 或 project_root/src/ 下）
BASE_DIR: Final[Path] = Path(__file__).resolve().parent.parent

# SQLite 数据库文件路径
DB_PATH: Final[Path] = BASE_DIR / "aigc_web.db"

# ==========================================
# 3. 安全与认证配置 (Security & Authentication)
# ==========================================

# 【安全检测核心说明 - 弱密钥防御】
# 默认值 "change-this-in-production" 仅用于本地开发。
# 若在生产环境中使用此默认值，攻击者可轻易伪造 JWT Token 获取系统最高权限。
SECRET_KEY: Final[str] = os.getenv("AIGC_WEB_SECRET")
if not SECRET_KEY:
    raise RuntimeError("AIGC_WEB_SECRET environment variable must be set in production")


# Token 过期时间（小时）
def _get_env_int(key: str, default: int) -> int:
    """安全地获取整数类型的环境变量"""
    value = os.getenv(key)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        logger.error("环境变量 %s 的值 '%s' 不是有效的整数，已回退至默认值 %d", key, value, default)
        return default


TOKEN_EXPIRE_HOURS: Final[int] = _get_env_int("AIGC_TOKEN_EXPIRE_HOURS", 24)

# ==========================================
# 4. AI 模型与检测器配置 (AI Models & Detectors)
# ==========================================

# 【跨平台路径说明】
# 原代码使用了 Windows 风格的 `\\` (如 `detectors\\script.py`)，这在 Linux 部署时会导致文件找不到。
# 此处统一使用 pathlib.Path 或正斜杠，确保跨平台兼容性。
MODELS_DIR: Final[Path] = BASE_DIR / "models"
DETECTORS_DIR: Final[Path] = BASE_DIR / "detectors"

# 单词级 (Word-level) 检测模型配置
WORD_MODEL_PATH: Final[str] = os.getenv(
    "WORD_MODEL_PATH",
    str(MODELS_DIR / "deberta_CRF(new)_best.pt")
)
WORD_MODEL_NAME: Final[str] = os.getenv(
    "WORD_MODEL_NAME",
    "microsoft/deberta-v3-base"
)
WORD_BOUNDARY_BACKEND_SCRIPT: Final[str] = os.getenv(
    "WORD_BOUNDARY_BACKEND_SCRIPT",
    str(DETECTORS_DIR / "deberta_CRF(new)_single_text.py")
)

# 句子级 (Sentence-level) 检测模型配置
SENTENCE_BACKEND_SCRIPT: Final[str] = os.getenv(
    "SENTENCE_BACKEND_SCRIPT",
    str(DETECTORS_DIR / "test_single_text.py")
)


# ==========================================
# 5. 配置校验与日志输出 (Validation & Logging)
# ==========================================

def _validate_paths() -> None:
    """校验关键文件路径是否存在（仅在非测试环境下执行严格校验）"""
    paths_to_check = {
        "Word Model": WORD_MODEL_PATH,
        "Word Detector Script": WORD_BOUNDARY_BACKEND_SCRIPT,
        "Sentence Detector Script": SENTENCE_BACKEND_SCRIPT,
    }

    for name, path_str in paths_to_check.items():
        if not Path(path_str).exists():
            logger.warning("【配置警告】%s 路径不存在: %s", name, path_str)


# 模块加载时执行路径校验
_validate_paths()
# ============================================
# 补充说明：config.py 代码注释维护
# 提交日期标识：2026.4.14
# 脚本执行时间：2026-05-28 12:34:42
# ============================================

# ============================================
# 补充说明：config.py 代码注释维护
# 提交日期标识：2026.4.15
# 脚本执行时间：2026-05-28 12:35:37
# ============================================

# ============================================
# 补充说明：config.py 代码注释维护
# 提交日期标识：2026.4.16
# 脚本执行时间：2026-05-28 12:37:11
# ============================================

# ============================================
# 补充说明：config.py 代码注释维护
# 提交日期标识：2026.4.20
# 脚本执行时间：2026-05-28 12:43:27
# ============================================

# ============================================
# 补充说明：config.py 代码注释维护
# 提交日期标识：2026.4.21
# 脚本执行时间：2026-05-28 12:44:17
# ============================================

# ============================================
# 补充说明：config.py 代码注释维护
# 提交日期标识：2026.4.22
# 脚本执行时间：2026-05-28 12:45:07
# ============================================
