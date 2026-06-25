"""First-run detection + the combined readiness report.

``is_first_run`` answers "is this a brand-new install?" so the dashboard can show
a welcome overlay. ``readiness`` bundles the machine diagnostic (:func:`doctor`)
and the getting-started checklist into one payload the daemon/CLI can render.
"""

from __future__ import annotations

from .checklist import _provider_connected, _has_any, getting_started
from .doctor import doctor


def is_first_run(platform) -> bool:
    """True for a brand-new install: zero sessions AND no real provider connected.

    A fresh checkout with only the offline mock model and no history is a first
    run; running any session or wiring a real model flips it to False.
    """
    from ..core.models import Session

    has_sessions = _has_any(platform.engine, Session)
    return not has_sessions and not _provider_connected(platform)


def readiness(platform) -> dict:
    """One payload combining diagnostics, the checklist, version, and first-run.

    Shape::

        {
          "version": str,
          "first_run": bool,
          "doctor": {ok, checks},
          "checklist": [ {key, title, detail, done, action}, ... ],
          "next_step": {step dict} | None,   # first incomplete step
        }
    """
    from .. import __version__

    diagnostic = doctor()
    steps = getting_started(platform)
    next_step = next((s for s in steps if not s["done"]), None)
    return {
        "version": __version__,
        "first_run": is_first_run(platform),
        "doctor": diagnostic,
        "checklist": steps,
        "next_step": next_step,
    }
