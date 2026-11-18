"""Reading documents from files (.txt, .md, .pdf) with limits, before anything is parsed.

A file larger than ``MAX_FILE_BYTES`` is refused unread. A PDF is parsed with pypdf, at most ``MAX_PDF_PAGES``
pages, and the extracted text is cut at ``MAX_TEXT_CHARS`` (a document must also fit the server's 16 MiB
limit). Any parser failure becomes ImportRefused with a plain reason: a damaged or hostile file never escapes
as an unexpected error. pypdf still runs in this process, so a parser bug could still use time or memory up
to these limits (docs/THREAT_MODEL.md, threat 19).
"""
from __future__ import annotations

from pathlib import Path

from .core.errors import PQSSEError

MAX_FILE_BYTES = 50 * 1024 * 1024
MAX_PDF_PAGES = 2_000
MAX_TEXT_CHARS = 8 * 1024 * 1024
SUFFIXES = (".txt", ".md", ".pdf")


class ImportRefused(PQSSEError):
    """The file cannot be imported (too large, unknown type, damaged, or not readable)."""


def read_document_file(path: str | Path) -> tuple[str, str]:
    """Import a .txt, .md or .pdf file as (title, text)."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix not in SUFFIXES:
        raise ImportRefused(f"{path.name}: only .txt, .md and .pdf files can be imported")
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise ImportRefused(f"{path.name}: cannot be read ({exc.strerror or exc})") from exc
    if size > MAX_FILE_BYTES:
        raise ImportRefused(f"{path.name}: {size // (1024 * 1024)} MB is larger than the {MAX_FILE_BYTES // (1024 * 1024)} MB limit")
    if suffix == ".pdf":
        text = _pdf_text(path)
    else:
        try:
            text = path.read_bytes().decode("utf-8", errors="replace")
        except OSError as exc:
            raise ImportRefused(f"{path.name}: cannot be read ({exc.strerror or exc})") from exc
    return path.stem, text[:MAX_TEXT_CHARS].strip()


def _pdf_text(path: Path) -> str:
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        if len(reader.pages) > MAX_PDF_PAGES:
            raise ImportRefused(f"{path.name}: more than {MAX_PDF_PAGES} pages")
        parts: list[str] = []
        total = 0
        for page in reader.pages:
            chunk = page.extract_text() or ""
            parts.append(chunk)
            total += len(chunk)
            if total >= MAX_TEXT_CHARS:
                break
        return "\n".join(parts)
    except ImportRefused:
        raise
    except RecursionError as exc:
        raise ImportRefused(f"{path.name}: the PDF is nested too deeply to read") from exc
    except Exception as exc:  # noqa: BLE001 - pypdf raises many kinds of errors for damaged files
        raise ImportRefused(f"{path.name}: not a readable PDF ({type(exc).__name__})") from exc
