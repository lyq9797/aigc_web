import base64
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import HTTPException, status

from .config import SECRET_KEY, TOKEN_EXPIRE_HOURS

PASSWORD_HASH_ITERATIONS = 200_000
MIN_PASSWORD_LENGTH = 6
JWT_ALGORITHM = "HS256"
JWT_HEADER = {"alg": JWT_ALGORITHM, "typ": "JWT"}


class AuthError(HTTPException):
    pass


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("utf-8")


def _b64url_decode(raw: str) -> bytes:
    padded = raw + "=" * ((4 - len(raw) % 4) % 4)
    return base64.urlsafe_b64decode(padded.encode("utf-8"))


def raise_auth_error(detail: str, status_code: int = status.HTTP_401_UNAUTHORIZED) -> None:
    raise AuthError(status_code=status_code, detail=detail)


def validate_password_policy(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise_auth_error("密码长度不能少于 6 位", status.HTTP_400_BAD_REQUEST)


def hash_password(password: str) -> str:
    validate_password_policy(password)
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PASSWORD_HASH_ITERATIONS)
    return f"pbkdf2_sha256${_b64url_encode(salt)}${_b64url_encode(digest)}"


def verify_password(password: str, encoded_hash: str) -> bool:
    try:
        algo, salt_s, digest_s = encoded_hash.split("$", 2)
        if algo != "pbkdf2_sha256":
            return False
        salt = _b64url_decode(salt_s)
        expected = _b64url_decode(digest_s)
        got = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PASSWORD_HASH_ITERATIONS)
        return hmac.compare_digest(got, expected)
    except Exception:
        return False


def create_token(user_id: int, username: str) -> str:
    now = datetime.now(timezone.utc)
    exp = now + timedelta(hours=TOKEN_EXPIRE_HOURS)
    payload = {
        "sub": user_id,
        "username": username,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }

    header_b64 = _b64url_encode(json.dumps(JWT_HEADER, separators=(",", ":")).encode("utf-8"))
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
    signature = hmac.new(SECRET_KEY.encode("utf-8"), signing_input, hashlib.sha256).digest()
    signature_b64 = _b64url_encode(signature)
    return f"{header_b64}.{payload_b64}.{signature_b64}"


def decode_token(token: str) -> dict[str, Any]:
    try:
        header_b64, payload_b64, signature_b64 = token.split(".")
    except ValueError as exc:
        raise_auth_error("Invalid token format") from exc

    signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
    expected_sig = hmac.new(SECRET_KEY.encode("utf-8"), signing_input, hashlib.sha256).digest()
    got_sig = _b64url_decode(signature_b64)
    if not hmac.compare_digest(expected_sig, got_sig):
        raise_auth_error("Invalid token signature")

    try:
        header = json.loads(_b64url_decode(header_b64).decode("utf-8"))
        payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise_auth_error("Invalid token payload") from exc

    if header.get("alg") != JWT_ALGORITHM:
        raise_auth_error("Unexpected token algorithm")

    now_ts = int(datetime.now(timezone.utc).timestamp())
    if int(payload.get("exp", 0)) < now_ts:
        raise_auth_error("Token expired")

    if payload.get("sub") is None:
        raise_auth_error("Token subject missing")

    return payload


def parse_bearer_token(auth_header: Optional[str]) -> str:
    if not auth_header:
        raise_auth_error("Missing Authorization header")
    if not auth_header.startswith("Bearer "):
        raise_auth_error("Expected Bearer token")
    return auth_header[7:].strip()
