"""Documents module — read and write real-world file types.

Gives Iron Jarvis the ability to read AND write PDF, Word (.docx), Excel
(.xlsx), PowerPoint (.pptx), CSV, plus .txt/.md/code, so agents can work with a
user's actual documents.

Public surface:

* :func:`extract_text` — text out of any supported file.
* :func:`write_document` — a real file in by suffix/kind.
* :data:`SUPPORTED_READ` / :data:`SUPPORTED_WRITE` — advertised suffixes.
* :func:`document_tools` — the read/write/extract Tools for the registry.
"""

from __future__ import annotations

from .readers import SUPPORTED_READ, extract_text
from .tools import (
    ExtractPdfTool,
    ReadDocumentTool,
    WriteDocumentTool,
    document_tools,
)
from .writers import SUPPORTED_WRITE, write_document

__all__ = [
    "extract_text",
    "write_document",
    "SUPPORTED_READ",
    "SUPPORTED_WRITE",
    "document_tools",
    "ReadDocumentTool",
    "WriteDocumentTool",
    "ExtractPdfTool",
]
