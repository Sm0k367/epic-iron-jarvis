"""Agent-facing semantic ``recall`` tool (§22 retrieval — Total Recall).

``recall`` is the single "remember anything" entry point: it runs a genuine
*semantic* search (real local embeddings when available, the deterministic
offline embedder otherwise — see :func:`build_embedder`) across BOTH the indexed
file roots and long-term memory, and returns ranked snippets. It mirrors
``file_search`` (root-scoped, fail-closed on protected paths) but blends in
long-term-memory hits so an agent can recall from notes/brain/Obsidian too.
"""

from __future__ import annotations

from typing import Any

from ..core.fs_policy import fs_path_allowed, is_protected_path
from ..tools.base import Tool, ToolContext, ToolResult


class RecallTool(Tool):
    """Semantic recall across indexed file roots and long-term memory."""

    name = "recall"
    description = (
        "Semantic recall: find the most relevant snippets by MEANING (not just "
        "substring) across the indexed file roots and long-term memory (brain / "
        "Obsidian / Notion). Returns ranked snippets with their source. Use this "
        "when you need to remember context, prior work, or notes — broader and "
        "smarter than a grep. Stays within configured roots and never reads "
        "protected paths."
    )
    permission_key = "recall"
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "k": {"type": "integer", "minimum": 1},
        },
        "required": ["query"],
    }

    def __init__(self, filesearch: Any, ltm: Any = None) -> None:
        self.filesearch = filesearch
        self.ltm = ltm

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        query = args.get("query", "")
        k = int(args.get("k", 5))

        file_results: list[dict[str, Any]] = []
        try:
            raw = self.filesearch.search(query, mode="semantic", limit=k)
        except Exception as exc:  # never crash the runtime on a recall
            raw = []
            file_error = f"{type(exc).__name__}: {exc}"
        else:
            file_error = None
        for r in raw:
            path = r.get("path", "")
            # Same fail-closed FS policy as file_search: skip protected/excluded.
            if is_protected_path(path) or not fs_path_allowed(path):
                continue
            file_results.append(
                {
                    "source": "file",
                    "ref": path,
                    "line": r.get("line"),
                    "snippet": r.get("text", ""),
                    "score": r.get("score"),
                }
            )

        ltm_results: list[dict[str, Any]] = []
        if self.ltm is not None:
            try:
                for h in self.ltm.search(query, k=k):
                    ltm_results.append(
                        {
                            "source": h.get("source", "ltm"),
                            "ref": h.get("ref", ""),
                            "title": h.get("title", ""),
                            "snippet": h.get("snippet", ""),
                            "score": None,
                        }
                    )
            except Exception:  # a failing connector must not break recall
                pass

        # Ranked: semantic file hits (ordered by cosine score) first, then the
        # long-term-memory hits, capped to the requested k.
        results = (file_results + ltm_results)[:k]

        lines: list[str] = []
        for r in results:
            ref = r.get("ref", "")
            if r.get("line") is not None:
                head = f"{ref}:{r['line']}"
            elif r.get("title"):
                head = f"[{r['source']}] {r['title']}"
            else:
                head = f"[{r['source']}] {ref}"
            lines.append(f"{head}: {r.get('snippet', '')}")

        data: dict[str, Any] = {
            "results": results,
            "file_results": file_results,
            "ltm_results": ltm_results,
            "count": len(results),
        }
        if file_error:
            data["file_error"] = file_error
        return ToolResult(ok=True, output="\n".join(lines), data=data)


def recall_tools(filesearch: Any, ltm: Any = None) -> list[Tool]:
    """Build the recall tool bound to the shared filesearch + ltm instances."""
    return [RecallTool(filesearch, ltm)]
