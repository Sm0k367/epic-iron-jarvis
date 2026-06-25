"""Connection persistence model.

``ConnectionRecord`` tracks the *connection state* of a provider — which method
it uses, whether it is connected, the account it is connected as, and the
*name* of the vault entry holding its credential. It deliberately stores **no**
secret values; the API key or OAuth token lives only in the encrypted
:class:`~iron_jarvis.secrets.manager.SecretsManager`, referenced here by
``secret_name``.

Importing this module registers the table on the shared SQLModel metadata, so it
must be imported BEFORE ``init_db`` runs (the platform handles import order).
"""

from __future__ import annotations

from datetime import datetime

from sqlmodel import Field, SQLModel

from ..core.ids import new_id, utcnow


class ConnectionRecord(SQLModel, table=True):
    """Per-provider connection state (no secret values are ever stored here)."""

    id: str = Field(default_factory=lambda: new_id("conn"), primary_key=True)
    provider: str = Field(unique=True, index=True)
    method: str = ""  # api_key | oauth | browser
    status: str = "disconnected"  # connected | disconnected | needs_auth
    scopes_json: str = "[]"  # granted OAuth scopes (JSON list), never secrets
    account: str = ""  # e.g. the connected email address
    secret_name: str = ""  # name of the vault entry holding the credential
    connected_at: datetime | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
