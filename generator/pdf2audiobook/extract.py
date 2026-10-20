"""PDF -> clean paragraphs -> chapters.

Chapter detection, in order of preference:
  1. "toc"      - the PDF's own bookmarks/outline (most reliable when present)
  2. "headings" - lines that look like chapter headings ("Chapter 3", "PART II",
                  "Prologue", ...) or text set noticeably larger than body text
  3. "pages"    - fallback: fixed-size parts of N pages each
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

HEADING_WORDS = (
    "chapter", "part", "book", "prologue", "epilogue", "introduction", "preface",
    "foreword", "afterword", "appendix", "conclusion", "interlude", "acknowledgements",
    "acknowledgments",
)
HEADING_RE = re.compile(
    r"^(?:(?:%s)\b.{0,70}|[IVXLC]{1,7}\.?|\d{1,3}\.?)$" % "|".join(HEADING_WORDS),
    re.IGNORECASE,
)
SENTENCE_END = tuple('.!?:;"\'”’)…')


@dataclass
class Para:
    text: str
    page: int
    size: float  # dominant font size
    y0: float = 0.0  # vertical position as a fraction of page height
    y1: float = 1.0
    top: bool = False  # first block on its page

    @property
    def near_edge(self) -> bool:
        return self.y0 < 0.1 or self.y1 > 0.9


@dataclass
class Chapter:
    title: str
    paragraphs: list[str] = field(default_factory=list)

    @property
    def words(self) -> int:
        return sum(len(p.split()) for p in self.paragraphs)


@dataclass
class Book:
    title: str
    author: str
    chapters: list[Chapter]
    method: str


def _norm(s: str) -> str:
    return re.sub(r"\d+", "#", re.sub(r"\s+", " ", s.strip().lower()))


def _clean_block_text(lines: list[str]) -> str:
    out = ""
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if out.endswith("-") and line[:1].islower():
            out = out[:-1] + line  # re-join hyphenated word across lines
        elif out:
            out += " " + line
        else:
            out = line
    out = out.replace("­", "").replace("ﬁ", "fi").replace("ﬂ", "fl")
    return re.sub(r"\s+", " ", out).strip()


def _read_paragraphs(doc: pymupdf.Document) -> list[Para]:
    pages: list[list[Para]] = []
    for pno, page in enumerate(doc):
        paras = []
        height = page.rect.height
        for block in page.get_text("dict", sort=True)["blocks"]:
            if block.get("type") != 0:
                continue
            lines, sizes = [], Counter()
            for line in block["lines"]:
                txt = "".join(span["text"] for span in line["spans"])
                for span in line["spans"]:
                    sizes[round(span["size"], 1)] += len(span["text"].strip())
                lines.append(txt)
            text = _clean_block_text(lines)
            if not text:
                continue
            size = sizes.most_common(1)[0][0] if sizes else 0
            paras.append(Para(text, pno, size, block["bbox"][1] / height, block["bbox"][3] / height))
        if paras:
            paras[0].top = True
        pages.append(paras)

    # Drop running headers/footers: short blocks near the page edge that repeat
    # across many pages (digits normalised so "Page 12" == "Page 13").
    n_pages = len(pages)
    edge = Counter()
    for paras in pages:
        for p in {_norm(p.text) for p in paras if p.near_edge and len(p.text) < 120}:
            edge[p] += 1
    repeated = {t for t, c in edge.items() if n_pages >= 4 and c >= max(3, n_pages * 0.25)}

    result: list[Para] = []
    for paras in pages:
        kept = []
        for p in paras:
            if p.near_edge and (_norm(p.text) in repeated or re.fullmatch(r"[\divxlc\-–— ]+", p.text, re.I)):
                continue
            kept.append(p)
        if kept:
            kept[0].top = True
        result.extend(kept)

    # Merge paragraphs that were split by a page break mid-sentence.
    merged: list[Para] = []
    for p in result:
        prev = merged[-1] if merged else None
        if (
            prev
            and p.page == prev.page + 1
            and p.top
            and not prev.text.endswith(SENTENCE_END)
            and p.text[:1].islower()
        ):
            if prev.text.endswith("-"):
                prev.text = prev.text[:-1] + p.text
            else:
                prev.text += " " + p.text
            continue
        merged.append(p)
    return merged


def _body_size(paras: list[Para]) -> float:
    c = Counter()
    for p in paras:
        c[p.size] += len(p.text)
    return c.most_common(1)[0][0] if c else 0


def _split_at(paras: list[Para], starts: list[tuple[int, str]]) -> list[Chapter]:
    """starts: (paragraph index, title) sorted by index."""
    chapters = []
    if starts and starts[0][0] > 0:
        front = [p.text for p in paras[: starts[0][0]]]
        if sum(len(t.split()) for t in front) > 150:  # keep meaningful front matter
            chapters.append(Chapter("Front Matter", front))
    for i, (idx, title) in enumerate(starts):
        end = starts[i + 1][0] if i + 1 < len(starts) else len(paras)
        body = [p.text for p in paras[idx:end]]
        # Don't read the heading twice: drop the leading block(s) that are the title.
        while body and _norm(body[0]) in _norm(title) and len(body[0]) <= len(title) + 5:
            body.pop(0)
        chapters.append(Chapter(title, body))
    return [c for c in chapters if c.paragraphs]  # drop title pages / empty part dividers


def _by_toc(doc: pymupdf.Document, paras: list[Para]) -> list[Chapter] | None:
    toc = doc.get_toc(simple=True)
    if not toc:
        return None
    levels = Counter(lvl for lvl, _, _ in toc)
    # Use the top level unless it has too few entries (e.g. a single "Book" node).
    level = min(levels)
    if levels[level] < 3 and level + 1 in levels and levels[level + 1] >= 3:
        level += 1
    entries = [(t.strip(), pg - 1) for lvl, t, pg in toc if lvl == level and pg >= 1 and t.strip()]
    if len(entries) < 2:
        return None

    starts: list[tuple[int, str]] = []
    for title, page in entries:
        candidates = [i for i, p in enumerate(paras) if p.page == page]
        if not candidates:
            later = [i for i, p in enumerate(paras) if p.page > page]
            if not later:
                continue
            candidates = later[:1]
        idx = candidates[0]
        # Prefer the block on that page whose text matches the bookmark title.
        for i in candidates[:8]:
            if _norm(title)[:30] in _norm(paras[i].text) or _norm(paras[i].text) in _norm(title):
                idx = i
                break
        if starts and idx <= starts[-1][0]:
            continue
        starts.append((idx, title))
    return _split_at(paras, starts) if len(starts) >= 2 else None


def _by_headings(paras: list[Para]) -> list[Chapter] | None:
    body = _body_size(paras)
    starts: list[tuple[int, str]] = []
    i = 0
    while i < len(paras):
        p = paras[i]
        short = len(p.text) <= 80
        looks = short and HEADING_RE.match(p.text)
        big = short and body and p.size >= body * 1.35 and len(p.text.split()) <= 12
        if looks or (big and p.top):
            title = p.text
            # "CHAPTER 3" followed by a separate subtitle block ("The Storm")
            nxt = paras[i + 1] if i + 1 < len(paras) else None
            if nxt and nxt.page == p.page and len(nxt.text) <= 60 and (nxt.size > body * 1.1 or nxt.text.istitle()) \
                    and not nxt.text.endswith((".", ",")):
                title = f"{p.text}: {nxt.text}"
                starts.append((i, title))
                paras[i + 1].text = title  # so _split_at drops it as the heading
                i += 2
                continue
            starts.append((i, title))
        i += 1
    # Reject absurd results (every line a heading) or nothing found.
    if len(starts) < 2 or len(starts) > len(paras) / 3:
        return None
    return _split_at(paras, starts)


def _by_pages(paras: list[Para], pages_per_part: int) -> list[Chapter]:
    chapters: dict[int, Chapter] = {}
    for p in paras:
        n = p.page // pages_per_part
        chapters.setdefault(n, Chapter(f"Part {len(chapters) + 1}")).paragraphs.append(p.text)
    return list(chapters.values())


def extract_book(pdf: Path, method: str = "auto", pages_per_part: int = 20,
                 title: str | None = None, author: str | None = None) -> Book:
    doc = pymupdf.open(pdf)
    meta = doc.metadata or {}
    paras = _read_paragraphs(doc)
    if not paras:
        raise SystemExit(
            f"No text found in {pdf}. It is probably a scanned PDF - run it through OCR first "
            "(e.g. `ocrmypdf input.pdf output.pdf`)."
        )

    chapters, used = None, method
    order = ["toc", "headings"] if method == "auto" else [method]
    for m in order:
        if m == "toc":
            chapters = _by_toc(doc, paras)
        elif m == "headings":
            chapters = _by_headings(paras)
        elif m == "pages":
            chapters = _by_pages(paras, pages_per_part)
        if chapters:
            used = m
            break
    if not chapters:
        chapters, used = _by_pages(paras, pages_per_part), "pages"

    return Book(
        title=title or (meta.get("title") or "").strip() or pdf.stem.replace("_", " "),
        author=author or (meta.get("author") or "").strip() or "Unknown",
        chapters=chapters,
        method=used,
    )
