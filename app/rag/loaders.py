"""
app/rag/loaders.py
-------------------
Format-specific loaders that turn raw policy documents (Markdown, HTML, PDF,
TXT) into a common in-memory representation: a `RawDocument` with a document
ID, title, source format, and plain-text body with light structural markers
("# " headings) preserved so the chunker can do heading-aware splitting.

Supporting at least two source formats is a project requirement; this module
supports all four formats used in the Solarium policy corpus so the RAG
pipeline is agnostic to how a given policy happens to be published.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from bs4 import BeautifulSoup

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover - pypdf is a required dependency
    PdfReader = None


@dataclass
class RawDocument:
    """A single ingested source document, normalized to plain text."""
    doc_id: str          # stable ID derived from filename, e.g. "SOL-HR-101"
    title: str            # human-readable title
    source_format: str    # "markdown" | "html" | "pdf" | "text"
    source_path: str      # original file path (for traceability / audit)
    text: str              # normalized plain text, headings kept as "# Heading"


_DOC_ID_RE = re.compile(r"(SOL-[A-Z]+-\d+)")


def _infer_doc_id(filename: str, fallback_text: str) -> str:
    """
    Solarium policy files embed a canonical Document ID (e.g. SOL-HR-101) in
    their header block. Prefer that over the filename so citations match the
    ID employees see in the actual policy documents.
    """
    m = _DOC_ID_RE.search(fallback_text[:1000])
    if m:
        return m.group(1)
    m = _DOC_ID_RE.search(filename)
    if m:
        return m.group(1)
    return Path(filename).stem


def _is_banner_line(s: str) -> bool:
    """True for decorative separator lines like '====...====' or '----...'"""
    stripped = s.strip()
    return bool(stripped) and len(set(stripped)) == 1 and stripped[0] in "=-*_#"


def _infer_title(lines: list[str], filename: str) -> str:
    """Best-effort title extraction: first non-empty, non-banner line that
    isn't the 'SOLARIUM INC.' banner or the Document ID metadata line.
    Also handles the single-line 'SOLARIUM INC. — Title' banner style used
    in the plain-text FAQ document."""
    for line in lines:
        s = line.strip()
        if not s or _is_banner_line(s):
            continue
        if s.upper().startswith("SOLARIUM INC"):
            if "—" in s:
                return s.split("—", 1)[1].strip()
            continue
        if s.startswith("Document ID:") or s.startswith("<!--") or s.startswith("Owner:"):
            continue
        return s
    return Path(filename).stem.replace("-", " ")


def load_markdown(path: Path) -> RawDocument:
    raw = path.read_text(encoding="utf-8")
    lines = raw.splitlines()
    doc_id = _infer_doc_id(path.name, raw)
    title = _infer_title(lines, path.name)
    # Markdown already uses "#"/"##" headings; keep as-is for the chunker.
    return RawDocument(doc_id, title, "markdown", str(path), raw)


def load_text(path: Path) -> RawDocument:
    raw = path.read_text(encoding="utf-8")
    lines = raw.splitlines()
    doc_id = _infer_doc_id(path.name, raw)
    title = _infer_title(lines, path.name)
    # Promote ALL-CAPS section banners (e.g. "SECTION 1 — PTO...") to
    # markdown-style headings so downstream chunking can treat TXT the same
    # way as markdown.
    normalized_lines = []
    for line in lines:
        if re.match(r"^SECTION\s+\d+\s*[—-]", line.strip()):
            normalized_lines.append("## " + line.strip())
        else:
            normalized_lines.append(line)
    return RawDocument(doc_id, title, "text", str(path), "\n".join(normalized_lines))


def load_html(path: Path) -> RawDocument:
    raw = path.read_text(encoding="utf-8")
    soup = BeautifulSoup(raw, "html.parser")

    # Use the full visible text (including the header <div class="meta">
    # block, which p/h1-only walking below would miss) to reliably find the
    # "Document ID: SOL-XXX-###" string near the top of the page.
    header_text = soup.get_text(" ", strip=True)[:1500]
    doc_id = _infer_doc_id(path.name, header_text)

    # Title: prefer <title>, else first <h1>
    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else None
    if not title:
        h1 = soup.find("h1")
        title = h1.get_text(strip=True) if h1 else path.stem

    # Walk the body and rebuild a markdown-ish plain text stream so the same
    # heading-aware chunker works across formats.
    out_lines: list[str] = []
    body = soup.body or soup
    for el in body.descendants:
        if getattr(el, "name", None) in ("h1", "h2"):
            out_lines.append(f"\n## {el.get_text(strip=True)}\n")
        elif getattr(el, "name", None) == "h3":
            out_lines.append(f"\n### {el.get_text(strip=True)}\n")
        elif getattr(el, "name", None) == "tr":
            cells = [c.get_text(strip=True) for c in el.find_all(["td", "th"])]
            if cells:
                out_lines.append("| " + " | ".join(cells) + " |")
        elif getattr(el, "name", None) == "li":
            out_lines.append("- " + el.get_text(strip=True))
        elif getattr(el, "name", None) == "p":
            txt = el.get_text(strip=True)
            if txt:
                out_lines.append(txt)

    text = "\n".join(out_lines)
    return RawDocument(doc_id, title, "html", str(path), text)


def load_pdf(path: Path) -> RawDocument:
    if PdfReader is None:  # pragma: no cover
        raise RuntimeError("pypdf is required to load PDF policy documents")
    reader = PdfReader(str(path))
    pages_text = []
    for page_num, page in enumerate(reader.pages, start=1):
        page_text = page.extract_text() or ""
        pages_text.append(f"\n<!-- page {page_num} -->\n" + page_text)
    text = "\n".join(pages_text)
    # PDF bullet glyphs sometimes extract as non-printable control chars
    # (e.g. DEL, 0x7f) depending on the font's character mapping. Replace
    # any stray control characters with a plain hyphen bullet so snippets
    # shown to end users never contain garbled symbols.
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "-", text)

    # The PDF pipeline (see ../../scripts) renders "## Heading" markdown
    # source into styled PDF headings; reverse that by promoting short,
    # title-cased lines that look like section headers back into "## "
    # markers so chunking stays heading-aware for PDFs too.
    lines = text.splitlines()
    rebuilt = []
    heading_pattern = re.compile(r"^\d+\.\s+[A-Z][A-Za-z0-9 ,/&'()-]{3,60}$")
    for line in lines:
        s = line.strip()
        if heading_pattern.match(s):
            rebuilt.append("## " + s)
        else:
            rebuilt.append(line)
    text = "\n".join(rebuilt)

    doc_id = _infer_doc_id(path.name, text)
    # PDF text extraction order can interleave header/footer canvas text
    # (page numbers, "Internal Use Only" footer) with body text, so title
    # detection is more conservative here than for the other formats: skip
    # short numeric/footer-looking lines and require a reasonably long,
    # letter-containing candidate.
    def _looks_like_title(s: str) -> bool:
        if not s or "SOLARIUM" in s.upper():
            return False
        if s.startswith(("Document ID", "<!--", "Page", "Solarium Inc.")):
            return False
        if "Internal Use Only" in s:
            return False
        return len(s) >= 8 and any(ch.isalpha() for ch in s)

    title_line = next((l.strip() for l in lines[:15] if _looks_like_title(l.strip())), path.stem)
    return RawDocument(doc_id, title_line, "pdf", str(path), text)


LOADERS = {
    ".md": load_markdown,
    ".markdown": load_markdown,
    ".txt": load_text,
    ".html": load_html,
    ".htm": load_html,
    ".pdf": load_pdf,
}


def load_corpus(corpus_dir: str | Path) -> list[RawDocument]:
    """Load every supported file in `corpus_dir` into RawDocument objects."""
    corpus_dir = Path(corpus_dir)
    docs: list[RawDocument] = []
    for path in sorted(corpus_dir.iterdir()):
        if path.suffix.lower() in LOADERS:
            loader = LOADERS[path.suffix.lower()]
            try:
                docs.append(loader(path))
            except Exception as exc:  # pragma: no cover - defensive
                print(f"[rag.loaders] WARNING: failed to load {path.name}: {exc}")
    return docs
