from __future__ import annotations

from typing import Any

import cloudinary
import cloudinary.utils

from app.config import settings


def configured() -> bool:
    return bool(
        settings.CLOUDINARY_CLOUD_NAME
        and settings.CLOUDINARY_API_KEY
        and settings.CLOUDINARY_API_SECRET
    )


def configure() -> None:
    cloudinary.config(
        cloud_name=settings.CLOUDINARY_CLOUD_NAME,
        api_key=settings.CLOUDINARY_API_KEY,
        api_secret=settings.CLOUDINARY_API_SECRET,
        secure=True,
    )


def sign_upload(params_to_sign: dict[str, Any]) -> str:
    """Generate a Cloudinary upload signature on the server only."""
    if not configured():
        raise RuntimeError("Cloudinary is not configured")
    configure()

    # Never trust client attempts to inject credentials into the signed payload.
    blocked = {"api_key", "api_secret", "cloud_name", "file", "signature"}
    clean = {
        key: value
        for key, value in params_to_sign.items()
        if key not in blocked and value not in (None, "", [], {})
    }
    return cloudinary.utils.api_sign_request(
        clean,
        settings.CLOUDINARY_API_SECRET,
    )
