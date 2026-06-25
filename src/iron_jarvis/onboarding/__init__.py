"""Onboarding + doctor — get anyone from zero to value.

Three entry points the daemon, CLI, and dashboard share:

* :func:`doctor` — a SAFE, read-only machine self-diagnostic.
* :func:`getting_started` — the live "first 4 steps to value" checklist.
* :func:`is_first_run` / :func:`readiness` — brand-new-install detection and the
  combined report (doctor + checklist + version) for the first-run overlay.
"""

from __future__ import annotations

from .checklist import getting_started
from .doctor import doctor
from .readiness import is_first_run, readiness

__all__ = ["doctor", "getting_started", "is_first_run", "readiness"]
