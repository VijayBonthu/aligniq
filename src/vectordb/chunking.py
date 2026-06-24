"""Chunking for vector embeddings.

Tier 1 "report-as-wiki" change: the final report is structured markdown, so we
chunk it SECTION-AWARE and keep fenced blocks (```mermaid / ```code) ATOMIC.
This means a diagram is never split across chunks again, and each chunk carries
its section heading for context. Raw (heading-less) text still falls back to a
fence-aware recursive split, so the uploaded-document path is unaffected.

`chunk_text` keeps its original signature and returns `list[str]` — a drop-in
upgrade for every existing caller. `chunk_report` additionally returns per-chunk
metadata (section_id, heading_text, content_type) for the embedding store.
"""

from langchain_text_splitters import RecursiveCharacterTextSplitter

from utils.report_sections import parse_sections, iter_fenced_blocks, DIAGRAM_LANGS

# Prose pieces longer than this are recursively split; fenced blocks are never
# split regardless of size (a diagram/code block must stay whole to render/parse).
_MAX_PROSE_CHARS = 1500
_PROSE_OVERLAP = 150
_SEPARATORS = ["\n\n", "\n", " ", ""]


def _content_type_for_lang(lang: str) -> str:
    return "diagram" if lang in DIAGRAM_LANGS else "code"


def _looks_like_table(text: str) -> bool:
    """Heuristic: a markdown pipe-table has a header separator row of dashes."""
    return "|" in text and any(
        set(line.strip()) <= set("|-: ") and "-" in line and "|" in line
        for line in text.splitlines()
    )


def _split_body(raw: str):
    """Yield (text, content_type|None) segments of `raw`, with fenced blocks kept
    whole. content_type is None for prose (the caller decides prose vs table)."""
    last = 0
    for start, end, lang, full in iter_fenced_blocks(raw):
        if start > last:
            yield raw[last:start], None
        yield full, _content_type_for_lang(lang)
        last = end
    if last < len(raw):
        yield raw[last:], None


def _with_heading(heading_label: str, text: str) -> str:
    """Prepend the section heading for retrieval context, unless `text` already
    starts with a heading (the section's first prose piece already carries it)."""
    stripped = text.lstrip()
    if not heading_label or stripped.startswith("#"):
        return text
    return f"{heading_label}\n{text}"


def _prose_pieces(text: str):
    """Split an oversize prose segment; short segments pass through unchanged."""
    t = text.strip()
    if not t:
        return []
    if len(t) <= _MAX_PROSE_CHARS:
        return [t]
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=_MAX_PROSE_CHARS, chunk_overlap=_PROSE_OVERLAP, separators=_SEPARATORS,
    )
    return [p for p in splitter.split_text(t) if p.strip()]


def chunk_report(markdown: str) -> list[dict]:
    """Section-aware chunks for a markdown report.

    Returns a list of {"text", "section_id", "heading_text", "content_type"}.
    Each fenced block becomes one atomic chunk (content_type 'diagram'/'code');
    prose is split per section into 'prose'/'table' chunks. Falls back to a
    fence-aware whole-document split when the markdown has no H2/H3 headings.
    """
    if not markdown or not markdown.strip():
        return []

    chunks: list[dict] = []
    sections = parse_sections(markdown)

    if not sections:
        for text, ctype in _split_body(markdown):
            if ctype is None:
                for piece in _prose_pieces(text):
                    chunks.append({
                        "text": piece,
                        "section_id": "",
                        "heading_text": "",
                        "content_type": "table" if _looks_like_table(piece) else "prose",
                    })
            else:
                chunks.append({
                    "text": text.strip(),
                    "section_id": "",
                    "heading_text": "",
                    "content_type": ctype,
                })
        return chunks

    for s in sections:
        heading_label = f"{'#' * s.heading_level} {s.heading_text}".strip()
        for text, ctype in _split_body(s.raw_markdown):
            if ctype is None:
                for piece in _prose_pieces(text):
                    chunks.append({
                        "text": _with_heading(heading_label, piece),
                        "section_id": s.id,
                        "heading_text": s.heading_text,
                        "content_type": "table" if _looks_like_table(piece) else "prose",
                    })
            else:
                chunks.append({
                    "text": _with_heading(heading_label, text.strip()),
                    "section_id": s.id,
                    "heading_text": s.heading_text,
                    "content_type": ctype,
                })
    return chunks


async def chunk_text(text: str, chunk_size: int = 1000, chunk_overlap: int = 200) -> list[str]:
    """Backward-compatible chunker returning a flat list of chunk strings.

    Markdown with headings is chunked section-aware (fenced blocks atomic);
    heading-less text uses a fence-aware recursive split honoring chunk_size.
    """
    if not text or not text.strip():
        return []

    if parse_sections(text):
        return [c["text"] for c in chunk_report(text)]

    # Heading-less fallback: recursive split, but never break a fenced block.
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size, chunk_overlap=chunk_overlap, separators=_SEPARATORS,
    )
    out: list[str] = []
    for seg, ctype in _split_body(text):
        if ctype is None:
            out.extend(p for p in splitter.split_text(seg) if p.strip())
        elif seg.strip():
            out.append(seg.strip())
    return out
