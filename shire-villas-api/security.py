import secrets

from fastapi import Header, HTTPException, status

from app.config import settings


def require_team_key(x_team_key: str | None = Header(default=None)) -> None:
    """
    Protects internal/team endpoints.

    The public landing page, visitor tracking and qualification endpoints do not
    use this dependency. Dashboard, lead lists, edits, exports and activity feeds do.
    """
    expected = settings.TEAM_API_KEY

    # Local development is allowed without a key only when no key is configured.
    if not expected and not settings.is_production:
        return

    if not x_team_key or not secrets.compare_digest(x_team_key, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing team API key.",
        )
