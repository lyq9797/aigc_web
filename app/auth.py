"""
Authentication and JWT utility module.

提供：
- 密码策略校验
- PBKDF2密码哈希
- 密码验证
- JWT生成
- JWT解析与验证
- Bearer Token解析
"""

import base64
import hashlib
import hmac
import json
import secrets
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import HTTPException, status

from .config import SECRET_KEY, TOKEN_EXPIRE_HOURS


# =========================
# Security Configuration
# =========================

PASSWORD_HASH_ITERATIONS = 200_000
MIN_PASSWORD_LENGTH = 6

PASSWORD_ALGORITHM = "pbkdf2_sha256"

JWT_ALGORITHM = "HS256"
JWT_TYPE = "JWT"

BEARER_PREFIX = "Bearer"

JWT_HEADER = {
    "alg": JWT_ALGORITHM,
    "typ": JWT_TYPE,
}


# =========================
# Data Models
# =========================

@dataclass(frozen=True)
class TokenPayload:
    """
    JWT Payload 数据结构。

    Attributes:
        sub: 用户ID
        username: 用户名
        iat: Token签发时间（Unix时间戳）
        exp: Token过期时间（Unix时间戳）
    """

    sub: int
    username: str
    iat: int
    exp: int


# =========================
# Internal Helpers
# =========================

def _raise_auth_error(
    detail: str,
    status_code: int = status.HTTP_401_UNAUTHORIZED,
) -> None:
    """
    统一抛出认证相关异常。

    Args:
        detail: 错误描述
        status_code: HTTP状态码
    """
    raise HTTPException(
        status_code=status_code,
        detail=detail,
    )


def _b64url_encode(raw: bytes) -> str:
    """
    Base64 URL安全编码。

    Args:
        raw: 原始字节数据

    Returns:
        编码后的字符串
    """
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("utf-8")


def _b64url_decode(raw: str) -> bytes:
    """
    Base64 URL安全解码。

    Args:
        raw: Base64字符串

    Returns:
        解码后的字节数据
    """
    padded = raw + "=" * ((4 - len(raw) % 4) % 4)
    return base64.urlsafe_b64decode(padded.encode("utf-8"))


def _sign_token(signing_input: bytes) -> bytes:
    """
    使用 HMAC-SHA256 生成JWT签名。

    Args:
        signing_input: JWT签名内容

    Returns:
        签名字节串
    """
    return hmac.new(
        SECRET_KEY.encode("utf-8"),
        signing_input,
        hashlib.sha256,
    ).digest()


# =========================
# Password Functions
# =========================

def validate_password_policy(password: str) -> None:
    """
    校验密码策略。

    Args:
        password: 用户密码

    Raises:
        HTTPException: 密码不符合要求
    """
    if len(password) < MIN_PASSWORD_LENGTH:
        _raise_auth_error(
            f"密码长度不能少于 {MIN_PASSWORD_LENGTH} 位",
            status.HTTP_400_BAD_REQUEST,
        )


def hash_password(password: str) -> str:
    """
    使用PBKDF2-HMAC-SHA256生成密码哈希。

    Args:
        password: 原始密码

    Returns:
        编码后的密码哈希字符串
    """
    validate_password_policy(password)

    salt = secrets.token_bytes(16)

    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PASSWORD_HASH_ITERATIONS,
    )

    return (
        f"{PASSWORD_ALGORITHM}"
        f"${_b64url_encode(salt)}"
        f"${_b64url_encode(digest)}"
    )


def verify_password(password: str, encoded_hash: str) -> bool:
    """
    验证密码是否正确。

    Args:
        password: 用户输入密码
        encoded_hash: 存储的密码哈希

    Returns:
        True表示验证通过，否则False
    """
    try:
        algo, salt_s, digest_s = encoded_hash.split("$", 2)

        if algo != PASSWORD_ALGORITHM:
            return False

        salt = _b64url_decode(salt_s)
        expected_digest = _b64url_decode(digest_s)

        actual_digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            PASSWORD_HASH_ITERATIONS,
        )

        return hmac.compare_digest(
            actual_digest,
            expected_digest,
        )

    except Exception:
        return False


# =========================
# JWT Functions
# =========================

def create_token(user_id: int, username: str) -> str:
    """
    创建JWT访问令牌。

    Args:
        user_id: 用户ID
        username: 用户名

    Returns:
        JWT字符串
    """
    now = datetime.now(timezone.utc)

    payload = TokenPayload(
        sub=user_id,
        username=username,
        iat=int(now.timestamp()),
        exp=int(
            (
                now
                + timedelta(hours=TOKEN_EXPIRE_HOURS)
            ).timestamp()
        ),
    )

    header_b64 = _b64url_encode(
        json.dumps(
            JWT_HEADER,
            separators=(",", ":"),
        ).encode("utf-8")
    )

    payload_b64 = _b64url_encode(
        json.dumps(
            asdict(payload),
            separators=(",", ":"),
        ).encode("utf-8")
    )

    signing_input = (
        f"{header_b64}.{payload_b64}"
    ).encode("utf-8")

    signature_b64 = _b64url_encode(
        _sign_token(signing_input)
    )

    return (
        f"{header_b64}."
        f"{payload_b64}."
        f"{signature_b64}"
    )


def decode_token(token: str) -> dict[str, Any]:
    """
    验证并解析JWT。

    验证内容：
        1. Token格式
        2. JWT签名
        3. Header合法性
        4. Token过期时间
        5. Subject字段

    Args:
        token: JWT字符串

    Returns:
        Token Payload字典
    """
    try:
        header_b64, payload_b64, signature_b64 = token.split(".")
    except ValueError as exc:
        _raise_auth_error("Invalid token format") from exc

    signing_input = (
        f"{header_b64}.{payload_b64}"
    ).encode("utf-8")

    expected_sig = _sign_token(signing_input)

    actual_sig = _b64url_decode(signature_b64)

    if not hmac.compare_digest(
        expected_sig,
        actual_sig,
    ):
        _raise_auth_error("Invalid token signature")

    try:
        header = json.loads(
            _b64url_decode(header_b64).decode("utf-8")
        )

        payload = json.loads(
            _b64url_decode(payload_b64).decode("utf-8")
        )

    except json.JSONDecodeError as exc:
        _raise_auth_error("Invalid token payload") from exc

    if (
        header.get("alg") != JWT_ALGORITHM
        or header.get("typ") != JWT_TYPE
    ):
        _raise_auth_error("Invalid token header")

    now_ts = int(
        datetime.now(
            timezone.utc
        ).timestamp()
    )

    if int(payload.get("exp", 0)) < now_ts:
        _raise_auth_error("Token expired")

    if payload.get("sub") is None:
        _raise_auth_error("Token subject missing")

    token_payload = TokenPayload(
        sub=int(payload["sub"]),
        username=str(payload["username"]),
        iat=int(payload["iat"]),
        exp=int(payload["exp"]),
    )

    return asdict(token_payload)


# =========================
# Authorization Header
# =========================

def parse_bearer_token(
    auth_header: Optional[str],
) -> str:
    """
    从Authorization Header中提取Bearer Token。

    Args:
        auth_header: Authorization请求头

    Returns:
        JWT字符串

    Raises:
        HTTPException: Header格式错误
    """
    if not auth_header:
        _raise_auth_error(
            "Missing Authorization header"
        )

    scheme, _, token = auth_header.partition(" ")

    if scheme.lower() != BEARER_PREFIX.lower():
        _raise_auth_error(
            "Expected Bearer token"
        )

    token = token.strip()

    if not token:
        _raise_auth_error(
            "Missing token"
        )

    return token