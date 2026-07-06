"""Creative gallery service — list and resolve the media Iron Jarvis has made.

The gallery is a VIEW over the artifact store: pixio generations save into it
via the artifact sink (tools/pixio.py), computer-use screenshots were already
there, and uploads land there too. One durable place, already wired to the
``artifact.generated`` live event.
"""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any

from sqlmodel import select

from ..core.db import session_scope

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".svg"}
VIDEO_EXTS = {".mp4", ".webm", ".mov", ".m4v", ".avi", ".mkv"}
AUDIO_EXTS = {".mp3", ".wav", ".ogg", ".m4a", ".flac", ".aac", ".opus"}

#: Artifact ``kind`` values that count as media even without a media extension.
_MEDIA_KINDS = {"image", "video", "audio", "screenshot"}


def media_kind(name: str) -> str | None:
    """'image' | 'video' | 'audio' from a filename's extension, else None."""
    ext = Path(str(name)).suffix.lower()
    if ext in IMAGE_EXTS:
        return "image"
    if ext in VIDEO_EXTS:
        return "video"
    if ext in AUDIO_EXTS:
        return "audio"
    return None


def mime_for(name: str) -> str:
    guessed, _ = mimetypes.guess_type(str(name))
    return guessed or "application/octet-stream"


def list_media(platform, *, limit: int = 200) -> list[dict[str, Any]]:
    """Every media artifact, newest first: pixio generations, screenshots,
    uploads — anything in the store that IS media (by kind or extension)."""
    from ..artifacts.models import ArtifactRecord

    limit = max(1, min(int(limit), 1000))
    with session_scope(platform.engine) as db:
        rows = list(
            db.exec(
                select(ArtifactRecord).order_by(
                    ArtifactRecord.created_at.desc()  # type: ignore[attr-defined]
                )
            )
        )
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for r in rows:
        if len(items) >= limit:
            break
        kind = media_kind(r.path) or (
            "image" if r.kind == "screenshot" else r.kind if r.kind in _MEDIA_KINDS else None
        )
        if kind is None:
            continue
        if r.name in seen:  # one card per artifact name — the store versions it
            continue
        seen.add(r.name)
        items.append(
            {
                "name": r.name,
                "version": r.version,
                "media": kind,
                "kind": r.kind,
                "filename": Path(r.path).name,
                "size": r.size,
                "session_id": r.session_id,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "url": f"/creative/file/{r.name}",
            }
        )
    return items
