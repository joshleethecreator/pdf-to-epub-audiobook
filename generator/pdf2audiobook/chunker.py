"""Split paragraphs into small, sentence-aligned segments for TTS.

Each segment becomes one WAV file on disk, so a crash or a closed laptop loses at
most one segment of work. Segments are also the unit the mobile reader highlights.
"""

from __future__ import annotations

import re

SENTENCE_RE = re.compile(r'(?<=[.!?…])["”’)\]]*\s+(?=["“‘(\[]?[A-Z0-9])')
ABBREV_RE = re.compile(r"\b(?:Mr|Mrs|Ms|Dr|Prof|Sr|Jr|St|vs|etc|e\.g|i\.e|Fig|No|Vol|pp?)\.$", re.I)


def split_sentences(text: str) -> list[str]:
    parts = SENTENCE_RE.split(text.strip())
    out: list[str] = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        if out and ABBREV_RE.search(out[-1]):
            out[-1] += " " + p  # "Dr. Smith" is not a sentence break
        else:
            out.append(p)
    return out


def _split_long(sentence: str, max_chars: int) -> list[str]:
    if len(sentence) <= max_chars:
        return [sentence]
    pieces, cur = [], ""
    # Prefer breaking after clause punctuation, then at any space.
    for clause in re.split(r"(?<=[,;:—–])\s+", sentence):
        while len(clause) > max_chars:
            cut = clause.rfind(" ", 0, max_chars)
            cut = cut if cut > max_chars // 3 else max_chars
            head, clause = clause[:cut].strip(), clause[cut:].strip()
            if cur:
                pieces.append(cur)
                cur = ""
            pieces.append(head)
        if cur and len(cur) + 1 + len(clause) > max_chars:
            pieces.append(cur)
            cur = clause
        else:
            cur = f"{cur} {clause}".strip()
    if cur:
        pieces.append(cur)
    return pieces


def chunk_paragraph(text: str, target_chars: int = 220, max_chars: int = 400) -> list[str]:
    """Group whole sentences into segments of roughly ``target_chars``."""
    segments: list[str] = []
    cur = ""
    for sentence in split_sentences(text):
        for piece in _split_long(sentence, max_chars):
            if cur and len(cur) + 1 + len(piece) > target_chars:
                segments.append(cur)
                cur = piece
            else:
                cur = f"{cur} {piece}".strip()
    if cur:
        segments.append(cur)
    return segments
