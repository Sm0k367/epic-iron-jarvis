"""Project (context-spine) routes.

Moved verbatim from daemon/app.py's create_app; closure-local state is
reached through ``d`` (see the deps object built in create_app).
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from sqlmodel import select
from typing import Any

from .. import app as _app
from ..app import _agent_type, _session_view
from ..schemas import (
    PROJECT_TASK_OUTPUTS,
    ProjectCreate,
    ProjectKnowledgeBody,
    ProjectPatch,
    ProjectTaskBody,
    ToolPlanBody,
)
from ...core.db import session_scope


def register(app: FastAPI, d) -> None:
    """Attach these routes to *app*; ``d`` is the create_app deps object."""
    @app.get("/projects")
    def list_projects() -> dict[str, Any]:
        from ...core.models import Project
        from ...core.models import Session as SessionModel

        active_id = getattr(d.platform.config, "active_project_id", None)
        with session_scope(d.platform.engine) as db:
            projects = list(db.exec(select(Project)))
            out = []
            for p in projects:
                ids = list(
                    db.exec(select(SessionModel.id).where(SessionModel.project_id == p.id))
                )
                out.append(
                    {
                        **p.model_dump(),
                        "session_count": len(ids),
                        "active": p.id == active_id,
                    }
                )
        out.sort(key=lambda x: str(x.get("created_at")), reverse=True)
        return {"projects": out}

    @app.post("/projects")
    def create_project(body: ProjectCreate) -> dict[str, Any]:
        from ...core.models import Project

        name = (body.name or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="project name is required")
        project = Project(name=name, brief=(body.brief or "").strip(), root=(body.root or "").strip())
        with session_scope(d.platform.engine) as db:
            db.add(project)
            db.commit()
            db.refresh(project)
        # First project with nothing active -> make it active, so the spine
        # starts working immediately (chat/Spotlight tag into it from now on).
        activated = False
        if not getattr(d.platform.config, "active_project_id", None):
            d.platform.config.active_project_id = project.id
            d._persist_config(["active_project_id"])
            activated = True
        return {**project.model_dump(), "active": activated}

    @app.get("/projects/{project_id}")
    def get_project(project_id: str) -> dict[str, Any]:
        from ...core.models import Project
        from ...core.models import Session as SessionModel

        with session_scope(d.platform.engine) as db:
            project = db.get(Project, project_id)
            if project is None:
                raise HTTPException(status_code=404, detail="no such project")
            sessions = list(
                db.exec(
                    select(SessionModel)
                    .where(SessionModel.project_id == project_id)
                    .order_by(SessionModel.created_at.desc())  # type: ignore[attr-defined]
                    .limit(20)
                )
            )
        return {
            "project": {
                **project.model_dump(),
                "active": project.id == getattr(d.platform.config, "active_project_id", None),
            },
            "sessions": [_session_view(s) for s in sessions],
        }

    @app.patch("/projects/{project_id}")
    def patch_project(project_id: str, body: ProjectPatch) -> dict[str, Any]:
        from ...core.models import Project

        if body.status is not None and body.status not in ("active", "archived"):
            raise HTTPException(status_code=400, detail="status must be active|archived")
        with session_scope(d.platform.engine) as db:
            project = db.get(Project, project_id)
            if project is None:
                raise HTTPException(status_code=404, detail="no such project")
            if body.name is not None and body.name.strip():
                project.name = body.name.strip()
            if body.brief is not None:
                project.brief = body.brief.strip()
            if body.root is not None:
                project.root = body.root.strip()
            if body.status is not None:
                project.status = body.status
            if body.instructions is not None:
                project.instructions = body.instructions.strip()
            if body.default_provider is not None:
                project.default_provider = body.default_provider.strip()
            if body.default_model is not None:
                project.default_model = body.default_model.strip()
            db.add(project)
            db.commit()
            db.refresh(project)
        # Archiving the ACTIVE project deactivates it (new work shouldn't tag
        # into something the user closed out).
        if project.status == "archived" and (
            getattr(d.platform.config, "active_project_id", None) == project_id
        ):
            d.platform.config.active_project_id = None
            d._persist_config(["active_project_id"])
        return project.model_dump()

    @app.delete("/projects/{project_id}")
    def delete_project(project_id: str) -> dict[str, Any]:
        """Remove a project from Iron Jarvis ONLY — the folder it pointed at
        and every file on disk are untouched (the root is just a reference).
        Sessions that were tagged to it keep their history; they simply lose
        the project association."""
        from ...core.models import Project
        from ...core.models import Session as SessionModel

        with session_scope(d.platform.engine) as db:
            proj = db.get(Project, project_id)
            if proj is None:
                raise HTTPException(status_code=404, detail="no such project")
            # Untag sessions (history preserved, association dropped).
            for s in db.exec(
                select(SessionModel).where(SessionModel.project_id == project_id)
            ):
                s.project_id = None
                db.add(s)
            db.delete(proj)
            db.commit()
        if getattr(d.platform.config, "active_project_id", None) == project_id:
            d.platform.config.active_project_id = None
            d._persist_config(["active_project_id"])
        return {"deleted": project_id, "files_touched": 0}

    @app.post("/projects/{project_id}/activate")
    def activate_project(project_id: str) -> dict[str, Any]:
        from ...core.models import Project

        with session_scope(d.platform.engine) as db:
            project = db.get(Project, project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="no such project")
        if project.status != "active":
            raise HTTPException(status_code=400, detail="unarchive the project first")
        d.platform.config.active_project_id = project_id
        d._persist_config(["active_project_id"])
        return {"active_project_id": project_id, "name": project.name}

    @app.post("/projects/deactivate")
    def deactivate_project() -> dict[str, Any]:
        d.platform.config.active_project_id = None
        d._persist_config(["active_project_id"])
        return {"active_project_id": None}

    @app.post("/projects/{project_id}/knowledge")
    def add_project_knowledge(project_id: str, body: ProjectKnowledgeBody) -> dict[str, Any]:
        """Add a knowledge item to a project — the Claude-Projects-style
        grounding substrate. A pasted note (``text``) is stored verbatim; a file
        (``content_b64``) is decoded, its text extracted server-side, and stored
        (kind='file'). Every item is embedded on write and injected into this
        project's chats/tasks. 400 if BOTH text and content_b64 are empty."""
        import base64
        import re
        from pathlib import Path

        from ...core.models import Project
        from ...documents.readers import extract_text
        from ...projects.knowledge import add_knowledge

        with session_scope(d.platform.engine) as db:
            if db.get(Project, project_id) is None:
                raise HTTPException(status_code=404, detail="no such project")

        b64 = (body.content_b64 or "").strip()
        note = (body.text or "").strip()
        if not b64 and not note:
            raise HTTPException(
                status_code=400, detail="text or content_b64 is required"
            )

        if b64:
            # Reject an oversized upload BEFORE decoding so we never buffer the
            # bytes (4/3 accounts for base64 expansion) — same guard as
            # /documents/upload and /ltm/ingest-document.
            approx_bytes = (len(b64) * 3) // 4
            if approx_bytes > _app._MAX_UPLOAD_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail=(
                        f"file too large (~{approx_bytes // (1024 * 1024)} MB); "
                        f"limit is {_app._MAX_UPLOAD_BYTES // (1024 * 1024)} MB"
                    ),
                )
            try:
                data = base64.b64decode(b64, validate=False)
            except Exception as exc:  # noqa: BLE001
                raise HTTPException(status_code=400, detail=f"invalid base64: {exc}")
            if not data:
                raise HTTPException(status_code=400, detail="empty file")
            # extract_text dispatches by suffix, so the decoded bytes need to live
            # in a real file with the original name/extension first.
            safe = (
                re.sub(r"[^A-Za-z0-9._-]", "_", body.filename or "").strip("._")
                or "upload"
            )
            uploads = d.platform.config.home / "uploads"
            uploads.mkdir(parents=True, exist_ok=True)
            target = uploads / safe
            target.write_bytes(data)
            try:
                extracted = (extract_text(target) or "").strip()
            except Exception as exc:  # noqa: BLE001 — report the real reason, don't fabricate
                raise HTTPException(
                    status_code=400, detail=f"could not read {safe}: {exc}"
                )
            if not extracted:
                raise HTTPException(
                    status_code=400, detail=f"no extractable text in {safe}"
                )
            item_text = extracted
            item_name = (body.name or body.filename or safe).strip() or safe
            kind = "file"
        else:
            item_text = note
            first_line = note.splitlines()[0] if note.splitlines() else note
            item_name = (body.name or first_line).strip() or "note"
            kind = "note"

        try:
            rec = add_knowledge(
                d.platform, project_id, item_name, item_text, kind=kind
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return {"id": rec.id, "name": rec.name, "kind": rec.kind, "size": rec.size}

    @app.get("/projects/{project_id}/knowledge")
    def list_project_knowledge(project_id: str) -> dict[str, Any]:
        """Metadata for every knowledge item in the project (newest first)."""
        from ...core.models import Project
        from ...projects.knowledge import list_knowledge

        with session_scope(d.platform.engine) as db:
            if db.get(Project, project_id) is None:
                raise HTTPException(status_code=404, detail="no such project")
        items = list_knowledge(d.platform, project_id)
        return {"knowledge": items, "count": len(items)}

    @app.delete("/projects/{project_id}/knowledge/{knowledge_id}")
    def delete_project_knowledge(
        project_id: str, knowledge_id: str
    ) -> dict[str, Any]:
        """Remove one knowledge item. 404 if it doesn't belong to the project."""
        from ...projects.knowledge import remove_knowledge

        if not remove_knowledge(d.platform, project_id, knowledge_id):
            raise HTTPException(status_code=404, detail="no such knowledge item")
        return {"deleted": knowledge_id}

    @app.post("/projects/{project_id}/task")
    async def run_project_task(project_id: str, body: ProjectTaskBody) -> dict[str, Any]:
        """Plain-text task INSIDE the project's folder, with a chosen
        deliverable: 'chat' = the answer lands in the session summary; any file
        output = the agent writes it into the folder with write_document
        (markdown structure becomes real docx/pdf/pptx/html structure; rows
        become real xlsx/csv cells). Returns the STARTED session (flat, like
        POST /sessions with wait:false) plus target_path for file outputs."""
        import re
        from pathlib import Path

        from ...core.models import Project
        from ...projects.knowledge import ground

        text = (body.text or "").strip()
        if not text:
            raise HTTPException(status_code=400, detail="text is required")
        output = (body.output or "chat").strip().lower()
        if output not in PROJECT_TASK_OUTPUTS:
            raise HTTPException(
                status_code=400,
                detail=f"output must be one of: {', '.join(PROJECT_TASK_OUTPUTS)}",
            )
        with session_scope(d.platform.engine) as db:
            project = db.get(Project, project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="no such project")
        root = Path(project.root) if project.root else None
        if output != "chat" and (root is None or not root.is_dir()):
            raise HTTPException(
                status_code=400,
                detail=(
                    "a file deliverable needs the project to have a folder — "
                    "set one on the Projects page first"
                ),
            )

        in_folder = root is not None and root.is_dir()
        lines = [f"Task: {text}", ""]
        if in_folder:
            # The session RUNS IN this folder (it's the workspace) — the agent
            # reads/writes it directly with plain filenames.
            lines.insert(
                0,
                "You are working directly inside the project folder — it is your "
                "current directory. Read and create files here with plain "
                "relative paths.",
            )
        # Per-project custom instructions ride at the FRONT — a standing directive
        # that applies to EVERY task in this project, before the task itself.
        instructions = (project.instructions or "").strip()
        if instructions:
            lines.insert(0, f"Project instructions (follow these): {instructions}")
        # Grounding: the project's knowledge base (whole base when small, else the
        # query-relevant items). Empty => no block (degrades gracefully).
        grounded = ground(d.platform, project.id, text)
        if grounded.strip():
            lines.append("Reference knowledge:\n" + grounded)
        target_path: str | None = None
        rel_name: str | None = None
        if output == "chat":
            lines.append(
                "Deliverable: a clear, complete written answer in your final "
                "summary — the summary IS the deliverable. Don't create files "
                "unless the task itself requires them."
            )
        else:
            stem = Path(body.filename or "").stem.strip()
            if not stem:
                stem = re.sub(r"[^A-Za-z0-9]+", "-", text[:40]).strip("-").lower() or "task"
            rel_name = f"{stem}.{output}"
            target_path = str(root / rel_name)
            lines.append(
                f"Deliverable: write the result to '{rel_name}' (in this folder) "
                "using the write_document tool — markdown headings/lists/tables "
                "become real structure in docx/pdf/pptx/html; pass a list of "
                "rows for xlsx/csv. State the saved file in your final summary."
            )
        lines.append(
            "Work autonomously to completion — make reasonable choices instead "
            "of asking questions."
        )
        # The task body carries no provider/model, so a project that pins its own
        # default_provider/default_model steers every task it runs (None = the
        # global default, i.e. the prior behavior).
        provider = (project.default_provider or "").strip() or None
        model = (project.default_model or "").strip() or None
        try:
            session = await d.orchestrator.create_session(
                "\n".join(lines),
                _agent_type("builder"),
                provider,
                model=model,
                project_id=project.id,
                allow_tools=body.allow_tools or None,
                workspace_root=str(root) if in_folder else None,
            )
        except (PermissionError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        d._spawn_bg(session.id, d.orchestrator.run_session(session.id))
        view = _session_view(session)
        view["output"] = output
        if target_path:
            view["target_path"] = target_path
        return view

    @app.post("/projects/{project_id}/task/plan")
    async def plan_project_task(project_id: str, body: ToolPlanBody) -> dict[str, Any]:
        """Ask the model which registry tools a plain-text task will likely
        need, so the UI can request permission for the WHOLE bundle at once
        instead of prompting per tool mid-run. Honest, best-effort: returns an
        empty plan (task still runnable) when no real model can answer."""
        import json as _json

        from ...core.models import Project
        from ...providers.adapters.base import LLMMessage

        text = (body.text or "").strip()
        if not text:
            raise HTTPException(status_code=400, detail="text is required")
        with session_scope(d.platform.engine) as db:
            if db.get(Project, project_id) is None:
                raise HTTPException(status_code=404, detail="no such project")

        # Only tools whose DEFAULT mode is 'ask' are worth bundling — allow
        # tools already run, deny tools never will. Map name -> perm_key so the
        # grant the UI sends back matches what the permission engine checks.
        specs = d.platform.registry.specs()
        askable: dict[str, dict[str, str]] = {}
        for spec in specs:
            name = spec.get("name")
            tool = d.platform.registry.get(name) if name else None
            if tool is None:
                continue
            pk = tool.perm_key()
            if d.platform.permissions.mode_for(pk).value != "ask":
                continue
            askable[name] = {"perm_key": pk, "description": spec.get("description", "")}
        if not askable:
            return {"tools": [], "note": "no permissioned tools needed"}

        adapter, used = d._failover_adapter("mock")
        if adapter is None:
            return {"tools": [], "note": "connect a model to auto-detect tool needs"}
        catalog = "\n".join(f"- {n}: {v['description'][:120]}" for n, v in askable.items())
        system = (
            "You choose which tools an agent will need for a task. Reply with "
            "ONLY a JSON array of the tool NAMES (from the catalog) the task "
            "will actually use — omit tools it won't. Be minimal but complete."
        )
        prompt = f"Task: {text}\n\nTool catalog:\n{catalog}"
        try:
            resp, _, _ = await d._one_shot_complete(
                used, adapter, system=system,
                messages=[LLMMessage(role="user", content=prompt)],
            )
            picked = _json.loads((resp.text or "").strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip())
            names = [str(n) for n in picked if str(n) in askable] if isinstance(picked, list) else []
        except Exception:  # noqa: BLE001 — a bad plan must never block the task
            names = []
        tools = [
            {"name": n, "perm_key": askable[n]["perm_key"], "why": askable[n]["description"][:100]}
            for n in dict.fromkeys(names)  # de-dupe, keep order
        ]
        return {"tools": tools}
