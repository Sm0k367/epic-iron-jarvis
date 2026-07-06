"""Creative routes: the gallery, media file serving, Pixio publish/upload.

The gallery lists media ARTIFACTS (pixio generations save into the store via
the artifact sink; screenshots and uploads live there too). File serving
carries proper content-types so the dashboard can render <img>/<video>/<audio>
directly (the token middleware already accepts ?token= for exactly this).
"""

from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from ..schemas import CreativePublishBody, CreativeUploadBody
from ...core.fs_policy import fs_read_ok
from ...creative.service import list_media, media_kind, mime_for

_MISSING_KEY = (
    "Pixio isn't connected — add your key on the Connections page (or a secret "
    "named 'pixio') to publish media."
)


def register(app: FastAPI, d) -> None:
    """Attach these routes to *app*; ``d`` is the create_app deps object."""

    def _pixio_key() -> str | None:
        try:
            key = d.platform.secrets.get("pixio")
        except Exception:  # noqa: BLE001 — vault miss = not configured
            key = None
        return key or os.environ.get("PIXIO_API_KEY") or None

    @app.get("/creative/items")
    def creative_items(limit: int = 200) -> dict[str, Any]:
        """The gallery: every media artifact, newest first."""
        items = list_media(d.platform, limit=limit)
        return {"items": items, "count": len(items)}

    @app.get("/creative/file/{name}")
    def creative_file(name: str, version: int | None = None):
        """Serve one gallery item's bytes with its real content-type.
        <img src>/<video src> can't send an Authorization header — the token
        middleware accepts ?token= (same pattern as the /events WebSocket)."""
        path = d.platform.artifacts.version_path(name, version)
        if path is None or not path.is_file():
            raise HTTPException(status_code=404, detail="no such media")
        if media_kind(path.name) is None:
            raise HTTPException(status_code=415, detail="not a media artifact")
        return FileResponse(path, media_type=mime_for(path.name))

    @app.get("/creative/file-by-path")
    def creative_file_by_path(path: str):
        """Serve a LOCAL media file (chat replies embed generated media by its
        absolute workspace path). Media extensions only + the fs policy guard —
        never a vault key or arbitrary file."""
        p = Path((path or "").strip())
        if not p.is_absolute():
            raise HTTPException(status_code=400, detail="absolute path required")
        if media_kind(p.name) is None:
            raise HTTPException(status_code=415, detail="not a media file")
        ok, reason = fs_read_ok(str(p))
        if not ok:
            raise HTTPException(status_code=403, detail=f"blocked: {reason}")
        if not p.is_file():
            raise HTTPException(status_code=404, detail="no such file")
        return FileResponse(p, media_type=mime_for(p.name))

    @app.post("/creative/publish")
    async def creative_publish(body: CreativePublishBody) -> dict[str, Any]:
        """Publish media to Pixio's CDN → a clean, PERMANENT, PUBLIC url usable
        directly in generation params. Source: gallery name, local path, or a
        remote url to mirror. Honest 424 when Pixio isn't connected."""
        import asyncio

        from ...tools.pixio import pixio_publish

        key = _pixio_key()
        if not key:
            raise HTTPException(status_code=424, detail=_MISSING_KEY)
        sources = [bool(body.name.strip()), bool(body.path.strip()), bool(body.url.strip())]
        if sum(sources) != 1:
            raise HTTPException(
                status_code=400, detail="give exactly one of name, path, or url"
            )
        endpoint = "images" if body.endpoint == "images" else "media"
        try:
            if body.url.strip():
                url = await asyncio.to_thread(
                    pixio_publish, key, url=body.url.strip(), endpoint=endpoint
                )
                return {"url": url}
            if body.name.strip():
                p = d.platform.artifacts.version_path(body.name.strip(), body.version)
                if p is None or not p.is_file():
                    raise HTTPException(status_code=404, detail="no such media")
            else:
                p = Path(body.path.strip())
                if not p.is_absolute() or not p.is_file():
                    raise HTTPException(status_code=404, detail="no such file")
                ok, reason = fs_read_ok(str(p))
                if not ok:
                    raise HTTPException(status_code=403, detail=f"blocked: {reason}")
            if media_kind(p.name) is None:
                raise HTTPException(
                    status_code=415,
                    detail="only image/video/audio may be published to the public CDN",
                )
            url = await asyncio.to_thread(
                pixio_publish,
                key,
                blob=p.read_bytes(),
                filename=p.name,
                mime=mime_for(p.name),
                endpoint=endpoint,
            )
            return {"url": url}
        except RuntimeError as exc:  # honest Pixio-side failure
            raise HTTPException(status_code=424, detail=str(exc))

    @app.post("/creative/upload")
    async def creative_upload(body: CreativeUploadBody) -> dict[str, Any]:
        """Add a media file to the gallery (durable, versioned); optionally
        also publish it to Pixio's CDN for a permanent public url."""
        name = Path(body.filename).name.strip()
        if not name or media_kind(name) is None:
            raise HTTPException(
                status_code=415, detail="only image/video/audio files belong in the gallery"
            )
        try:
            blob = base64.b64decode(body.content_b64, validate=False)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=f"invalid base64: {exc}")
        if not blob:
            raise HTTPException(status_code=400, detail="empty file")
        from .. import app as _app

        if len(blob) > _app._MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="file too large")
        artifact = d.platform.artifacts.save(
            f"upload-{Path(name).stem}", blob, kind=media_kind(name) or "file", filename=name
        )
        out: dict[str, Any] = {
            "name": artifact.name,
            "version": artifact.version,
            "media": media_kind(name),
            "size": artifact.size,
        }
        if body.publish:
            import asyncio

            from ...tools.pixio import pixio_publish

            key = _pixio_key()
            if not key:
                out["publish_error"] = _MISSING_KEY
                return out
            try:
                out["url"] = await asyncio.to_thread(
                    pixio_publish, key, blob=blob, filename=name, mime=mime_for(name)
                )
            except RuntimeError as exc:
                out["publish_error"] = str(exc)
        return out
