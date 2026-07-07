"""Project (context-spine) routes.

Moved verbatim from daemon/app.py's create_app; closure-local state is
reached through ``d`` (see the deps object built in create_app).
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from sqlmodel import select
from typing import Any

from ..app import _agent_type, _session_view
from ..schemas import PROJECT_TASK_OUTPUTS, ProjectCreate, ProjectPatch, ProjectTaskBody
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

        lines = [f"Task: {text}", ""]
        if root is not None and root.is_dir():
            lines.insert(
                0,
                f"Work inside the project folder: {root}. Use absolute paths "
                "under it for every file you read or create.",
            )
        target_path: str | None = None
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
            target_path = str(root / f"{stem}.{output}")
            lines.append(
                f"Deliverable: write the result to exactly {target_path} using "
                "the write_document tool (markdown headings/lists/tables become "
                "real structure in docx/pdf/pptx/html; pass a list of rows for "
                "xlsx/csv). State the saved path in your final summary."
            )
        lines.append(
            "Work autonomously to completion — make reasonable choices instead "
            "of asking questions."
        )
        try:
            session = await d.orchestrator.create_session(
                "\n".join(lines),
                _agent_type("builder"),
                None,
                project_id=project.id,
            )
        except (PermissionError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        d._spawn_bg(session.id, d.orchestrator.run_session(session.id))
        view = _session_view(session)
        view["output"] = output
        if target_path:
            view["target_path"] = target_path
        return view
