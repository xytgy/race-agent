from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class TextPage:
    content: str
    page_no: int | None = None


@dataclass(frozen=True)
class TextChunk:
    content: str
    chunk_index: int
    page_no: int | None
    section: str | None
    char_start: int
    char_end: int


def chunk_text(text: str, chunk_size: int = 800, chunk_overlap: int = 100) -> list[str]:
    if chunk_size <= chunk_overlap:
        raise ValueError("chunk_size must be greater than chunk_overlap")
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(text[start:end])
        start += chunk_size - chunk_overlap
    return chunks


def _section_for_offset(text: str, offset: int) -> str | None:
    """Return the closest markdown-style heading before offset."""
    section = None
    for match in re.finditer(r"(?m)^\s{0,3}#{1,6}\s+(.+?)\s*$", text[:offset]):
        section = match.group(1).strip()
    return section


def chunk_pages(
    pages: list[TextPage],
    chunk_size: int = 800,
    chunk_overlap: int = 100,
) -> list[TextChunk]:
    if chunk_size <= chunk_overlap:
        raise ValueError("chunk_size must be greater than chunk_overlap")

    chunks: list[TextChunk] = []
    for page in pages:
        text = page.content or ""
        start = 0
        while start < len(text):
            end = min(start + chunk_size, len(text))
            content = text[start:end].strip()
            if content:
                chunks.append(
                    TextChunk(
                        content=content,
                        chunk_index=len(chunks) + 1,
                        page_no=page.page_no,
                        section=_section_for_offset(text, end),
                        char_start=start,
                        char_end=end,
                    )
                )
            if end >= len(text):
                break
            start += chunk_size - chunk_overlap
    return chunks
