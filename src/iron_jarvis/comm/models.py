"""Inbound-comm persistence model (two-way comm, made durable).

``InboundOffsetRecord`` is the durable last-seen polling offset per channel
*registration* (e.g. the Telegram ``getUpdates`` offset). Persisting it means a
daemon restart resumes from where it left off and never reprocesses an already
handled message.

Importing this module before ``init_db`` registers the table on
``SQLModel.metadata`` so it auto-creates with the rest of the schema.
"""

from __future__ import annotations

from datetime import datetime

from sqlmodel import Field, SQLModel

from ..core.ids import utcnow


class InboundOffsetRecord(SQLModel, table=True):
    """The durable inbound poll offset for one channel registration."""

    #: the channel's registration name in the notifier (e.g. ``"tg"``).
    channel: str = Field(primary_key=True)
    offset: int = 0
    updated_at: datetime = Field(default_factory=utcnow)
