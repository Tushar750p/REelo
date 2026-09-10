"""Persistent media storage for REelo.

Cloudinary is optional during local development. When CLOUDINARY_URL is set,
new videos are uploaded to Cloudinary and their secure delivery URL is stored
in the database so the media survives Render restarts and redeploys.
"""
from __future__ import annotations

import os
from pathlib import Path


def cloudinary_enabled() -> bool:
    return bool(os.getenv("CLOUDINARY_URL"))


def upload_video(path: Path, public_id: str) -> str | None:
    if not cloudinary_enabled():
        return None

    import cloudinary
    import cloudinary.uploader

    cloudinary.config(secure=True)
    result = cloudinary.uploader.upload(
        str(path),
        resource_type="video",
        public_id=f"reelo/videos/{public_id}",
        overwrite=False,
        invalidate=True,
    )
    return result.get("secure_url")
