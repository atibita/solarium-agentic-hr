"""
app/rag/chunking.py
--------------------
Heading-aware chunking with token-window fallback.

Design rationale (documented in design-and-evaluation.md):
  Policy documents are already organized into numbered sections ("## 1.
  Purpose", "## 2. Accrual", ...). Splitting on those headings keeps each
  chunk topically coherent (e.g. "PTO carryover" never gets split mid-rule),
  which materially improves citation precision versus fixed-size windows.
  Sections that are still too long (e.g. a dense table-heavy section) are
  further split using a token-window with overlap, so no chunk exceeds the
  configured max size and retrieval recall isn't hurt by an oversized chunk
  diluting the embedding.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .loaders import RawDocument

HEADING_RE = re.compile(r"^(#{2,3})\s+(.*)$")


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    doc_title: str
    source_format: str
    source_path: str
    section: str
    text: str


def _split_into_sections(text: str) -> list[tuple[str, str]]:
    """Split raw text on '## '/'### ' headings. Returns (section_title, body)
    pairs. Content before the first heading is kept under 'Introduction'."""
    lines = text.splitlines()
    sections: list[tuple[str, list[str]]] = []
    current_title = "Introduction"
    current_body: list[str] = []

    for line in lines:
        m = HEADING_RE.match(line.strip())
        if m:
            if current_body:
                sections.append((current_title, current_body))
            current_title = m.group(2).strip()
            current_body = []
        else:
            current_body.append(line)
    if current_body:
        sections.append((current_title, current_body))

    return [(title, "\n".join(body).strip()) for title, body in sections if "\n".join(body).strip()]


def _word_window_split(text: str, max_words: int, overlap_words: int) -> list[str]:
    """Fallback token(word)-window splitter with overlap, used when a single
    section is still larger than `max_words`."""
    words = text.split()
    if len(words) <= max_words:
        return [text]
    chunks = []
    start = 0
    step = max(max_words - overlap_words, 1)
    while start < len(words):
        window = words[start:start + max_words]
        chunks.append(" ".join(window))
        if start + max_words >= len(words):
            break
        start += step
    return chunks


def chunk_document(doc: RawDocument, max_words: int = 220, overlap_words: int = 40) -> list[Chunk]:
    """Heading-aware chunking with a token-window fallback for long sections."""
    sections = _split_into_sections(doc.text)
    chunks: list[Chunk] = []
    idx = 0
    for section_title, body in sections:
        pieces = _word_window_split(body, max_words=max_words, overlap_words=overlap_words)
        for piece in pieces:
            idx += 1
            chunk_id = f"{doc.doc_id}::chunk-{idx:03d}"
            chunks.append(Chunk(
                chunk_id=chunk_id,
                doc_id=doc.doc_id,
                doc_title=doc.title,
                source_format=doc.source_format,
                source_path=doc.source_path,
                section=section_title,
                text=piece,
            ))
    return chunks


def chunk_corpus(docs: list[RawDocument], max_words: int = 220, overlap_words: int = 40) -> list[Chunk]:
    all_chunks: list[Chunk] = []
    for doc in docs:
        all_chunks.extend(chunk_document(doc, max_words=max_words, overlap_words=overlap_words))
    return all_chunks
