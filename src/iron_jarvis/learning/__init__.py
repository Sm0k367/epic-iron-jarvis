"""Self-correcting learning loop (§29 — complements the Evaluation Engine).

Iron Jarvis gets better each time you use it: feedback and post-session
reflections are captured as durable *lessons*, and those lessons (plus explicit
preferences) are injected into the agent's system prompt on every future run.

Importing this package registers its SQLModel tables on the shared metadata, so
``init_db`` creates them. Build one :class:`LearningEngine` on the platform, then
expose :func:`learning_tools` to agents.
"""

from __future__ import annotations

from .engine import LearningEngine
from .models import FeedbackRecord, LessonRecord
from .tools import RecallLessonsTool, RememberPreferenceTool, learning_tools

__all__ = [
    "LearningEngine",
    "FeedbackRecord",
    "LessonRecord",
    "RememberPreferenceTool",
    "RecallLessonsTool",
    "learning_tools",
]
