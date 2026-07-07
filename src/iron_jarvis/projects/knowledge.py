"""Project knowledge store — the substrate for Claude-Projects-style grounding.

Each item (a file's extracted text, or a pasted note) is embedded on write via
the SHARED embedder. :func:`ground` returns the text to inject into a project's
chats/tasks: the WHOLE knowledge base when it's small, or the query-relevant
items (cosine over the stored vectors) when it exceeds the context budget.
Everything degrades gracefully — no embedder, no query, or a mock embedder all
still yield useful (recency-ordered) grounding.
"""

from __future__ import annotations

import json
import math
from typing import Any

from sqlmodel import select

from ..core.db import session_scope
from ..core.models import ProjectKnowledge

#: Chars of an item we embed for retrieval (one representative vector/item).
_EMBED_CHARS = 4000
#: Default grounding budget injected into a prompt.
DEFAULT_GROUND_CHARS = 6000


def _embed(embedder, text: str) -> list[float]:
    if embedder is None or not text.strip():
        return []
    try:
        return list(embedder.embed(text[:_EMBED_CHARS]))
    except Exception:  # noqa: BLE001 — retrieval is best-effort; store text anyway
        return []


def _cosine(u: list[float], v: list[float]) -> float:
    if not u or not v or len(u) != len(v):
        return 0.0
    dot = sum(a * b for a, b in zip(u, v))
    nu = math.sqrt(sum(a * a for a in u))
    nv = math.sqrt(sum(b * b for b in v))
    return dot / (nu * nv) if nu and nv else 0.0


def add_knowledge(
    platform, project_id: str, name: str, text: str, *, kind: str = "note"
) -> ProjectKnowledge:
    """Store one knowledge item (embedded on write). Text is required."""
    text = (text or "").strip()
    if not text:
        raise ValueError("knowledge text is empty")
    embedder = getattr(platform, "embedder", None)
    rec = ProjectKnowledge(
        project_id=project_id,
        name=(name or "untitled").strip()[:200],
        kind=kind if kind in ("note", "file") else "note",
        text=text,
        size=len(text),
        embedding_json=json.dumps(_embed(embedder, text)),
    )
    with session_scope(platform.engine) as db:
        db.add(rec)
        db.commit()
        db.refresh(rec)
    return rec


def list_knowledge(platform, project_id: str) -> list[dict[str, Any]]:
    """Metadata for every knowledge item (newest first) — no text/vectors."""
    with session_scope(platform.engine) as db:
        rows = list(
            db.exec(
                select(ProjectKnowledge)
                .where(ProjectKnowledge.project_id == project_id)
                .order_by(ProjectKnowledge.created_at.desc())  # type: ignore[attr-defined]
            )
        )
    return [
        {
            "id": r.id,
            "name": r.name,
            "kind": r.kind,
            "size": r.size,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


def remove_knowledge(platform, project_id: str, knowledge_id: str) -> bool:
    """Delete one item. Returns False when it didn't exist (for a clean 404)."""
    with session_scope(platform.engine) as db:
        rec = db.get(ProjectKnowledge, knowledge_id)
        if rec is None or rec.project_id != project_id:
            return False
        db.delete(rec)
        db.commit()
    return True


def ground(
    platform,
    project_id: str,
    query: str = "",
    *,
    char_budget: int = DEFAULT_GROUND_CHARS,
) -> str:
    """The knowledge text to inject for this project. Small base → include it
    ALL; large base → the query-relevant items (cosine) up to ``char_budget``,
    falling back to newest-first when there's no usable query/embedder."""
    with session_scope(platform.engine) as db:
        rows = list(
            db.exec(
                select(ProjectKnowledge)
                .where(ProjectKnowledge.project_id == project_id)
                .order_by(ProjectKnowledge.created_at.desc())  # type: ignore[attr-defined]
            )
        )
    if not rows:
        return ""
    total = sum(r.size for r in rows)
    chosen: list[ProjectKnowledge]
    if total <= char_budget:
        chosen = list(reversed(rows))  # oldest→newest reads naturally
    else:
        embedder = getattr(platform, "embedder", None)
        qvec = _embed(embedder, query) if query.strip() else []
        if qvec:
            scored = []
            for r in rows:
                try:
                    vec = json.loads(r.embedding_json or "[]")
                except (ValueError, TypeError):
                    vec = []
                scored.append((_cosine(qvec, vec), r))
            scored.sort(key=lambda x: x[0], reverse=True)
            ordered = [r for _, r in scored]
        else:
            ordered = rows  # newest-first fallback
        chosen = []
        used = 0
        for r in ordered:
            if used and used + r.size > char_budget:
                continue
            chosen.append(r)
            used += r.size
            if used >= char_budget:
                break

    blocks = [f"## {r.name}\n{r.text}" for r in chosen]
    body = "\n\n".join(blocks)
    if len(body) > char_budget + 500:  # hard clamp (a single huge item)
        body = body[:char_budget].rstrip() + "\n…(truncated)"
    return body
