"""
Pydantic 数据模型与请求/响应契约 (Data Schemas & Contracts)

【安全检测全局说明】
1. 本模块是系统防御恶意输入的第一道防线（边界校验）。
2. 所有接收外部输入的字符串字段必须严格限制 `max_length`，防御缓冲区溢出或哈希/算法 DoS 攻击。
3. 敏感字段（如密码）必须使用 `SecretStr` 类型，防止在异常堆栈或日志中意外明文泄露。
4. 推荐在生产环境中结合 `pydantic-settings` 将硬编码的限制值（如 MAX_TEXT_LENGTH）提取为环境变量。
"""

from __future__ import annotations

import re
from typing import Any, Final

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

# ==========================================
# 1. 安全基线常量 (Security Baselines)
# ==========================================

# 【安全说明】集中管理长度限制，便于全局调整和安全审计
MAX_USERNAME_LENGTH: Final[int] = 50
MAX_PASSWORD_LENGTH: Final[int] = 128
MAX_DETECT_TEXT_LENGTH: Final[int] = 10_000

# 【安全说明】用户名正则：仅允许字母、数字、下划线和中划线，防御特殊字符引发的注入或 XSS
USERNAME_PATTERN: Final[str] = r"^[a-zA-Z0-9_-]+$"


# ==========================================
# 2. 认证相关模型 (Authentication Schemas)
# ==========================================

class RegisterRequest(BaseModel):
    """用户注册请求模型"""

    username: str = Field(
        min_length=3,
        max_length=MAX_USERNAME_LENGTH,
        pattern=USERNAME_PATTERN,
        description="用户名（3-50位，仅限字母、数字、下划线和中划线）"
    )

    # 【安全核心】使用 SecretStr 防止密码在日志、异常追踪（如 Sentry）中被明文记录
    password: SecretStr = Field(
        min_length=8,  # 行业标准建议密码最小长度为 8 位
        max_length=MAX_PASSWORD_LENGTH,
        description="用户密码（8-128位）"
    )

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: SecretStr) -> SecretStr:
        """
        【安全检测说明 - 弱口令防御】
        此处仅做基础的非空和纯空格校验。
        生产环境强烈建议引入 `zxcvbn` 库或自定义正则，强制要求包含大小写字母、数字及特殊符号。
        """
        raw_password = v.get_secret_value()
        if not raw_password.strip():
            raise ValueError("密码不能全为空格")
        return v


class LoginRequest(BaseModel):
    """用户登录请求模型"""

    username: str = Field(
        max_length=MAX_USERNAME_LENGTH,
        description="用户名"
    )

    # 【安全核心 - 哈希 DoS 防御】
    # 必须限制密码最大长度！如果不限制，攻击者提交 10MB 的密码字符串，
    # 会导致后端的 bcrypt/argon2 哈希计算瞬间耗尽 CPU 资源 (DoS 攻击)。
    password: SecretStr = Field(
        max_length=MAX_PASSWORD_LENGTH,
        description="用户密码"
    )


class AuthResponse(BaseModel):
    """认证成功响应模型"""

    token: str = Field(..., description="JWT 访问令牌")
    username: str = Field(..., description="用户名")


# ==========================================
# 3. 核心业务模型 (Core Business Schemas)
# ==========================================

class DetectRequest(BaseModel):
    """AIGC 文本检测请求模型"""

    # 【安全核心 - 算法 DoS 防御】
    # 必须限制 max_length！AI/NLP 模型的推理时间通常随文本长度呈非线性增长。
    # 不限制长度会导致攻击者提交百万字长文，卡死 GPU/CPU 推理进程。
    text: str = Field(
        min_length=1,
        max_length=MAX_DETECT_TEXT_LENGTH,
        description=f"待检测文本（1-{MAX_DETECT_TEXT_LENGTH} 字符）"
    )

    @field_validator("text")
    @classmethod
    def strip_and_validate_text(cls, v: str) -> str:
        """清理首尾空白字符并校验有效性"""
        cleaned_text = v.strip()
        if not cleaned_text:
            raise ValueError("检测文本去除空白字符后不能为空")
        return cleaned_text


class HistoryItem(BaseModel):
    """历史检测记录响应模型"""

    id: int = Field(..., description="记录唯一标识")
    input_text: str = Field(..., description="用户输入的原始文本")
    result: dict[str, Any] = Field(..., description="AI 模型返回的检测结果 JSON")
    created_at: str = Field(..., description="记录创建时间 (ISO 8601 格式)")

    # 【规范说明】启用 ORM 模式，允许直接从 SQLAlchemy 模型或 sqlite3.Row 对象初始化
    model_config = ConfigDict(from_attributes=True)
# ============================================
# 补充说明：schemas.py 代码注释维护
# 提交日期标识：2026.4.14
# 脚本执行时间：2026-05-28 12:35:02
# ============================================

# ============================================
# 补充说明：schemas.py 代码注释维护
# 提交日期标识：2026.4.15
# 脚本执行时间：2026-05-28 12:35:57
# ============================================

# ============================================
# 补充说明：schemas.py 代码注释维护
# 提交日期标识：2026.4.16
# 脚本执行时间：2026-05-28 12:37:30
# ============================================


