import base64
import hashlib
import hmac
import json
import secrets
import time

from fastapi import Header, HTTPException, status

from app.config import settings


SESSION_TTL_SECONDS = 12 * 60 * 60


def _clean(value: str | None) -> str:
    return (value or "").strip()


def _b64_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def verify_team_key(candidate: str | None) -> bool:
    expected = _clean(settings.TEAM_API_KEY)
    supplied = _clean(candidate)
    return bool(expected and supplied and secrets.compare_digest(supplied, expected))


def create_session_token() -> str:
    now = int(time.time())
    payload = {
        "sub": "shire-team",
        "iat": now,
        "exp": now + SESSION_TTL_SECONDS,
    }
    body = _b64_encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    )
    signature = hmac.new(
        _clean(settings.SECRET_KEY).encode("utf-8"),
        body.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return body + "." + _b64_encode(signature)


def verify_session_token(token: str | None) -> bool:
    if not token or "." not in token:
        return False

    try:
        body, signature = token.split(".", 1)
        expected_signature = hmac.new(
            _clean(settings.SECRET_KEY).encode("utf-8"),
            body.encode("ascii"),
            hashlib.sha256,
        ).digest()

        if not hmac.compare_digest(
            _b64_decode(signature),
            expected_signature,
        ):
            return False

        payload = json.loads(_b64_decode(body))
        return (
            payload.get("sub") == "shire-team"
            and int(payload.get("exp", 0)) > int(time.time())
        )
    except Exception:
        return False


def require_team_key(
    authorization: str | None = Header(default=None),
    x_team_key: str | None = Header(default=None),
) -> None:
    """
    Team authentication.

    Preferred: Authorization: Bearer <signed session token>
    Backward-compatible: X-Team-Key: <TEAM_API_KEY>
    """
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        if verify_session_token(token):
            return

    if verify_team_key(x_team_key):
        return

    if not settings.TEAM_API_KEY and not settings.is_production:
        return

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required.",
    )
