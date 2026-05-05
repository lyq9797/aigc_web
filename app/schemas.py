"""
Pydantic 数据模型与请求/响应契约 (Data Schemas & Contracts)

"""

from __future__ import annotations

import re
from typing import Any, Final

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

# ==========================================
# 1. 安全基线常量 (Security Baselines)
# ==========================================

# 集中管理长度限制，便于全局调整和安全审计
MAX_USERNAME_LENGTH: Final[int] = 50
MAX_PASSWORD_LENGTH: Final[int] = 128
MAX_DETECT_TEXT_LENGTH: Final[int] = 10_000

# 用户名正则：仅允许字母、数字、下划线和中划线，防御特殊字符引发的注入或 XSS
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

    # 使用 SecretStr 防止密码在日志、异常追踪（如 Sentry）中被明文记录
    password: SecretStr = Field(
        min_length=8,  # 行业标准建议密码最小长度为 8 位
        max_length=MAX_PASSWORD_LENGTH,
        description="用户密码（8-128位）"
    )

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: SecretStr) -> SecretStr:
        """
        此处仅做基础的非空和纯空格校验。
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

    # 启用 ORM 模式，允许直接从 SQLAlchemy 模型或 sqlite3.Row 对象初始化
    model_config = ConfigDict(from_attributes=True)