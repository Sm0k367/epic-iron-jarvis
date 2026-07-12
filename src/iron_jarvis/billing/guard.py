"""Session preflight + post-run metering for credits and token budgets.

Used by daemon session routes. Never raises on meter failure (log + continue).
"""

from __future__ import annotations

from typing import Any

from ..core.logging import get_logger

log = get_logger("billing.guard")


def preflight_session(platform: Any, provider: str | None) -> None:
    """Raise HTTP-friendly exceptions as ValueError with code prefix.

    Raises:
        ValueError: ``402:`` insufficient credits, ``429:`` budget exceeded
    """
    billing = getattr(platform, "billing", None)
    if billing is None:
        return
    cfg = platform.config
    prov = provider or getattr(cfg, "default_provider", "mock") or "mock"

    ok, reason = billing.can_start_run(prov)
    if not ok:
        raise ValueError(f"402:{reason}")

    tok_ok, tok_reason = billing.check_token_budgets(
        max_tokens_per_day=int(getattr(cfg, "max_tokens_per_day", 0) or 0),
        max_usd_per_day=float(getattr(cfg, "max_usd_per_day", 0) or 0),
        max_runs_per_hour=int(getattr(cfg, "max_runs_per_hour", 0) or 0),
    )
    if not tok_ok:
        raise ValueError(f"429:{tok_reason}")


def meter_session(platform: Any, session: Any) -> dict[str, Any] | None:
    """Record usage / burn credits after a completed run. Best-effort."""
    billing = getattr(platform, "billing", None)
    if billing is None or session is None:
        return None
    try:
        return billing.record_session_usage(
            session_id=getattr(session, "id", "") or "",
            provider=getattr(session, "provider", "") or "",
            model=getattr(session, "model", "") or "",
            input_tokens=int(getattr(session, "input_tokens", 0) or 0),
            output_tokens=int(getattr(session, "output_tokens", 0) or 0),
        )
    except Exception:  # noqa: BLE001
        log.exception("billing meter failed for session %s", getattr(session, "id", "?"))
        return None


def raise_http(exc: ValueError) -> None:
    """Convert ``402:`` / ``429:`` ValueError into FastAPI HTTPException."""
    from fastapi import HTTPException

    msg = str(exc)
    if msg.startswith("402:"):
        raise HTTPException(status_code=402, detail=msg[4:].strip())
    if msg.startswith("429:"):
        raise HTTPException(status_code=429, detail=msg[4:].strip())
    raise HTTPException(status_code=400, detail=msg)
