"""Security fixes: FS-policy enforced at the agent-tool layer (not just HTTP),
and the OAuth callback no longer reflects an unescaped provider (XSS).
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from iron_jarvis.core import fs_policy
from iron_jarvis.daemon.app import create_app
from iron_jarvis.documents.tools import ReadDocumentTool
from iron_jarvis.tools.base import ToolContext


def _ctx(ws):
    return ToolContext(
        workspace=ws, session_id="t", agent_run_id="t",
        config=None, event_bus=None, engine=None,
    )


async def test_read_document_denies_protected_secrets_path(tmp_path):
    secrets = tmp_path / "vault-secrets"
    secrets.mkdir()
    key = secrets / ".secrets.key"
    key.write_text("FERNET-KEY-MATERIAL")
    fs_policy.register_protected_root(secrets)
    ws = tmp_path / "ws"
    ws.mkdir()
    res = await ReadDocumentTool().execute({"path": str(key)}, _ctx(ws))
    assert res.ok is False
    assert "FERNET-KEY-MATERIAL" not in (res.output or "")


async def test_read_document_respects_allowlist(tmp_path, monkeypatch):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("OUTSIDE-SECRET")
    monkeypatch.setenv("IRONJARVIS_FS_ALLOWLIST", str(allowed))
    ws = tmp_path / "ws"
    ws.mkdir()
    res = await ReadDocumentTool().execute({"path": str(outside)}, _ctx(ws))
    assert res.ok is False  # outside the allowlist
    ok_file = allowed / "ok.txt"
    ok_file.write_text("hello inside")
    res2 = await ReadDocumentTool().execute({"path": str(ok_file)}, _ctx(ws))
    assert res2.ok and "hello inside" in res2.output


def test_oauth_callback_escapes_tag_payload(tmp_path):
    client = TestClient(create_app(str(tmp_path)))
    # No slash in the payload (path segment can't contain '/').
    r = client.get("/oauth/<img src=x onerror=alert(1)>/callback")
    assert r.status_code == 200
    assert "<img src=x onerror=alert(1)>" not in r.text  # escaped, never raw
    assert "window.opener" in r.text  # legit postMessage script preserved
    assert "content-security-policy" in {k.lower() for k in r.headers}


def test_oauth_callback_no_quote_breakout(tmp_path):
    client = TestClient(create_app(str(tmp_path)))
    r = client.get("/oauth/'+alert(1)+'/callback")
    assert r.status_code == 200
    # The provider is encoded via JSON.parse("...") — a double-quoted JS string
    # literal, so the single-quote payload is inert (cannot break out). The old
    # vulnerable single-quoted object-literal injection pattern must be gone.
    assert "JSON.parse(" in r.text
    assert "'provider':'" not in r.text


def test_http_documents_read_denies_protected_key(tmp_path):
    # create_app builds the platform, which registers <home>/secrets as protected.
    client = TestClient(create_app(str(tmp_path)))
    key = tmp_path / ".ironjarvis" / "secrets" / ".secrets.key"
    key.parent.mkdir(parents=True, exist_ok=True)
    key.write_text("FERNET-MASTER-KEY")
    r = client.get("/documents/read", params={"path": str(key)})
    assert r.status_code == 403  # protected-roots enforced at the HTTP layer too
    assert "FERNET-MASTER-KEY" not in r.text


def test_http_documents_read_respects_allowlist(tmp_path, monkeypatch):
    outside = tmp_path / "outside.txt"
    outside.write_text("OUTSIDE")
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    monkeypatch.setenv("IRONJARVIS_FS_ALLOWLIST", str(allowed))
    client = TestClient(create_app(str(tmp_path)))
    r = client.get("/documents/read", params={"path": str(outside)})
    assert r.status_code == 403
