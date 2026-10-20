"""The resumable PDF -> audiobook pipeline.

Everything lives in a work folder (default: ./work/<book-name>/):

  book.json            extracted chapters + TTS segments (edit it to fix chapter titles!)
  settings.json        voice / speed of the last run (used by `build`)
  cover.jpg            first page of the PDF
  audio/ab/ab12....wav one WAV per segment, written atomically and named by a hash
                       of (voice, speed, text)

Re-running the same command skips every segment that already has a WAV, so you
can stop at any time (Ctrl+C, closing the laptop, a crash) and pick up again.
Because files are keyed by their text, editing book.json only re-synthesizes the
segments you actually changed.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path

import pymupdf

from . import audio
from .chunker import chunk_paragraph
from .epub import write_epub
from .extract import extract_book
from .tts import make_engine

PAUSE_AFTER_TITLE = 1.2
PAUSE_PARAGRAPH = 0.6
PAUSE_SENTENCE = 0.25
BOOK_FORMAT_VERSION = 1


def slugify(s: str) -> str:
    s = re.sub(r"[^\w\s-]", "", s).strip()
    return re.sub(r"[\s_-]+", "-", s)[:60] or "book"


def _write_json(path: Path, data) -> None:
    tmp = path.with_suffix(".json.part")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def prepare(pdf: Path, work: Path, method: str = "auto", pages_per_part: int = 20,
            title: str | None = None, author: str | None = None, force: bool = False) -> dict:
    """Extract chapters and split them into segments. Reuses book.json if it exists."""
    book_path = work / "book.json"
    if book_path.exists() and not force:
        return _read_json(book_path)

    book = extract_book(pdf, method, pages_per_part, title, author)
    chapters = []
    for ch in book.chapters:
        paragraphs = [chunk_paragraph(p) for p in ch.paragraphs]
        chapters.append({"title": ch.title, "paragraphs": [p for p in paragraphs if p]})
    data = {
        "version": BOOK_FORMAT_VERSION,
        "title": book.title,
        "author": book.author,
        "source": pdf.name,
        "chapter_method": book.method,
        "chapters": chapters,
    }
    work.mkdir(parents=True, exist_ok=True)
    _write_json(book_path, data)

    doc = pymupdf.open(pdf)
    if len(doc):
        doc[0].get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5)).save(work / "cover.jpg")
    return data


def segments_of(chapter: dict) -> list[tuple[str, str]]:
    """Flatten a chapter into (kind, text) where kind is 'title', 'para-start' or 'cont'."""
    out = [("title", chapter["title"])]
    for para in chapter["paragraphs"]:
        for j, seg in enumerate(para):
            out.append(("para-start" if j == 0 else "cont", seg))
    return out


def seg_path(work: Path, settings: dict, text: str) -> Path:
    key = f"{settings['engine']}|{settings['voice']}|{settings['speed']}|{text}"
    h = hashlib.sha1(key.encode("utf-8")).hexdigest()
    return work / "audio" / h[:2] / f"{h}.wav"


def load_settings(work: Path) -> dict:
    path = work / "settings.json"
    if not path.exists():
        raise SystemExit(f"{work} has no settings.json - run `generate` first.")
    return _read_json(path)


def _fmt_eta(seconds: float) -> str:
    h, rem = divmod(int(seconds), 3600)
    return f"{h}h{rem // 60:02d}m" if h else f"{rem // 60}m{rem % 60:02d}s"


def synthesize(work: Path, book: dict, engine_name: str, voice: str, speed: float,
               lang: str | None, device: str | None, chapters: list[int] | None = None) -> None:
    settings = {"engine": engine_name, "voice": voice, "speed": speed}
    path = work / "settings.json"
    if path.exists() and _read_json(path) != settings:
        print(f"Note: settings changed from {_read_json(path)} - segments will be re-synthesized with the new ones.")
    _write_json(path, settings)

    todo = []
    total = 0
    for ci, ch in enumerate(book["chapters"]):
        if chapters and ci + 1 not in chapters:
            continue
        for _, text in segments_of(ch):
            total += 1
            if not seg_path(work, settings, text).exists():
                todo.append((ci, text))

    done_before = total - len(todo)
    if not todo:
        print(f"All {total} segments already synthesized.")
        return
    print(f"{done_before}/{total} segments already done, {len(todo)} to go. Loading TTS ({engine_name})...")
    engine = make_engine(engine_name, voice, speed, lang, device)

    start = time.time()
    chars_total = sum(len(t) for *_, t in todo)
    chars_done = 0
    last_ch = None
    for n, (ci, text) in enumerate(todo, 1):
        if ci != last_ch:
            print(f"\n== Chapter {ci + 1}: {book['chapters'][ci]['title']}")
            last_ch = ci
        target = seg_path(work, settings, text)
        if not target.exists():  # the same sentence can appear twice in a book
            audio.write_wav_atomic(target, engine.synthesize(text))
        chars_done += len(text)
        elapsed = time.time() - start
        eta = elapsed / chars_done * (chars_total - chars_done)
        print(f"\r  [{done_before + n}/{total}] {100 * (done_before + n) / total:5.1f}%  ETA {_fmt_eta(eta)}   ",
              end="", flush=True)
    print()


def missing_segments(work: Path, book: dict, settings: dict) -> int:
    return sum(
        not seg_path(work, settings, text).exists()
        for ch in book["chapters"]
        for _, text in segments_of(ch)
    )


def assemble(work: Path, book: dict, out: Path, bitrate: str = "64k") -> Path:
    """Build the final outputs from the segment WAVs."""
    audio.require_ffmpeg()
    settings = load_settings(work)
    missing = missing_segments(work, book, settings)
    if missing:
        raise SystemExit(f"{missing} segments are not synthesized yet - run `generate` again to finish them.")

    name = slugify(book["title"])
    dest = out / name
    app_dir = dest / "app-bundle"
    app_dir.mkdir(parents=True, exist_ok=True)
    silence_dir = work / "silence"
    cover = work / "cover.jpg" if (work / "cover.jpg").exists() else None

    # Remember what each chapter file was built from, so re-runs skip unchanged chapters.
    encoded_path = work / "encoded.json"
    encoded = _read_json(encoded_path) if encoded_path.exists() else {}
    scratch = work / "tmp"
    for stale in app_dir.glob("ch[0-9][0-9][0-9].m4a"):
        if int(stale.stem[2:]) > len(book["chapters"]):
            stale.unlink()  # chapters were merged/removed in book.json

    app_chapters, chapter_files, chapter_marks = [], [], []
    for ci, ch in enumerate(book["chapters"]):
        pieces: list[Path] = []
        segments_meta = []
        t = 0.0
        para_idx = -1
        for si, (kind, text) in enumerate(segments_of(ch)):
            if kind == "para-start":
                para_idx += 1
            if si > 0:
                gap = PAUSE_AFTER_TITLE if si == 1 else PAUSE_PARAGRAPH if kind == "para-start" else PAUSE_SENTENCE
                pieces.append(audio.silence_wav(silence_dir, gap))
                t += gap
            wav = seg_path(work, settings, text)
            dur = audio.wav_duration(wav)
            pieces.append(wav)
            segments_meta.append({"text": text, "p": para_idx, "start": round(t, 3), "end": round(t + dur, 3)})
            t += dur
        pieces.append(audio.silence_wav(silence_dir, PAUSE_AFTER_TITLE))

        fname = f"ch{ci + 1:03d}.m4a"
        target = app_dir / fname
        fingerprint = hashlib.sha1(f"{bitrate}|{'|'.join(p.name for p in pieces)}".encode()).hexdigest()
        if not target.exists() or encoded.get(str(target)) != fingerprint:
            print(f"  encoding chapter {ci + 1}/{len(book['chapters'])}: {ch['title']}")
            audio.encode_chapter(pieces, target, bitrate, scratch)
            encoded[str(target)] = fingerprint
            _write_json(encoded_path, encoded)
        duration = audio.probe_duration(target)
        chapter_files.append(target)
        chapter_marks.append((ch["title"], duration))
        app_chapters.append({"title": ch["title"], "audio": fname, "duration": round(duration, 3),
                             "segments": segments_meta})

    if cover:
        (app_dir / "cover.jpg").write_bytes(cover.read_bytes())
    _write_json(app_dir / "book.json", {
        "format": "pdf2audiobook", "version": BOOK_FORMAT_VERSION,
        "id": name, "title": book["title"], "author": book["author"],
        "cover": "cover.jpg" if cover else None,
        "duration": round(sum(d for _, d in chapter_marks), 3),
        "chapters": app_chapters,
    })

    print("  building .m4b audiobook ...")
    m4b = dest / f"{name}.m4b"
    audio.build_m4b(chapter_files, chapter_marks, m4b, book["title"], book["author"], cover, scratch)

    print("  building .epub ...")
    write_epub(dest / f"{name}.epub", book["title"], book["author"],
               [(c["title"], [" ".join(p) for p in c["paragraphs"]]) for c in book["chapters"]], cover)
    return dest
