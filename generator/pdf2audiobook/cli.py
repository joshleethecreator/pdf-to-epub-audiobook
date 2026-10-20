from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import pipeline

VOICES = """American English (lang a):  af_heart (default, best), af_bella, af_nicole, af_sarah, af_sky,
                            am_michael, am_fenrir, am_puck, am_adam
British English  (lang b):  bf_emma, bf_isabella, bf_alice, bm_george, bm_fable, bm_daniel
Full list: https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md"""


def _work_dir(args, pdf: Path | None = None) -> Path:
    if args.work:
        return Path(args.work)
    if pdf is None:
        raise SystemExit("--work is required")
    return Path("work") / pipeline.slugify(pdf.stem)


def _chapters_arg(s: str | None) -> list[int] | None:
    if not s:
        return None
    out: list[int] = []
    for part in s.split(","):
        a, _, b = part.partition("-")
        out.extend(range(int(a), int(b or a) + 1))
    return out


def _print_chapters(book: dict) -> None:
    print(f"\n{book['title']} — {book['author']}")
    print(f"Chapters found with method: {book['chapter_method']}\n")
    total = 0
    for i, ch in enumerate(book["chapters"], 1):
        words = sum(len(seg.split()) for para in ch["paragraphs"] for seg in para)
        total += words
        print(f"  {i:3d}. {ch['title'][:70]:<70} {words:>7,} words  (~{words / 150:.0f} min)")
    print(f"\n  Total: {total:,} words, roughly {total / 150 / 60:.1f} hours of audio.")


def cmd_inspect(args) -> None:
    pdf = Path(args.pdf)
    work = _work_dir(args, pdf)
    book = pipeline.prepare(pdf, work, args.chapters_from, args.pages_per_part, args.title, args.author, force=True)
    _print_chapters(book)
    print(f"\nSaved to {work / 'book.json'} — edit chapter titles there if you like, then run `generate`.")


def cmd_generate(args) -> None:
    pdf = Path(args.pdf)
    work = _work_dir(args, pdf)
    fresh = not (work / "book.json").exists()
    book = pipeline.prepare(pdf, work, args.chapters_from, args.pages_per_part, args.title, args.author,
                            force=args.re_extract)
    if fresh or args.re_extract:
        _print_chapters(book)
    else:
        print(f"Resuming {book['title']} from {work}")
    try:
        pipeline.synthesize(work, book, args.engine, args.voice, args.speed, args.lang, args.device,
                            _chapters_arg(args.only_chapters))
    except KeyboardInterrupt:
        print("\n\nStopped. Progress is saved — run the same command again to continue where you left off.")
        sys.exit(130)
    if args.only_chapters:
        print("Done with the selected chapters (skipping build because --only-chapters was used).")
        return
    print("\nAll audio generated. Building outputs...")
    dest = pipeline.assemble(work, book, Path(args.out), args.bitrate)
    _print_done(dest)


def cmd_build(args) -> None:
    work = Path(args.work)
    book = pipeline._read_json(work / "book.json")
    _print_done(pipeline.assemble(work, book, Path(args.out), args.bitrate))


def _print_done(dest: Path) -> None:
    print(f"\nDone! Everything is in {dest}/")
    for f in sorted(dest.iterdir()):
        print(f"  {f.name}")
    print("\n  *.m4b       -> the audiobook with chapters (works in any audiobook player)")
    print("  *.epub      -> the text as an e-book")
    print("  app-bundle/ -> import this into the mobile app (or run `pdf2audiobook serve`)")


def cmd_serve(args) -> None:
    from .serve import serve
    serve(Path(args.out), args.port)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="pdf2audiobook", description="PDF -> chaptered Kokoro audiobook")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_extract_opts(sp):
        sp.add_argument("pdf", help="the PDF file")
        sp.add_argument("--work", help="work folder for progress (default: work/<pdf-name>)")
        sp.add_argument("--chapters-from", choices=["auto", "toc", "headings", "pages"], default="auto",
                        help="how to find chapters (default: auto = bookmarks, then headings)")
        sp.add_argument("--pages-per-part", type=int, default=20, help="part size when --chapters-from pages")
        sp.add_argument("--title", help="override the book title")
        sp.add_argument("--author", help="override the author")

    sp = sub.add_parser("inspect", help="detect chapters and show them, without generating audio")
    add_extract_opts(sp)
    sp.set_defaults(func=cmd_inspect)

    sp = sub.add_parser("generate", help="generate the audiobook (resumable: just run it again)")
    add_extract_opts(sp)
    sp.add_argument("--out", default="output", help="output folder (default: output)")
    sp.add_argument("--voice", default="af_heart", help="Kokoro voice (see `pdf2audiobook voices`)")
    sp.add_argument("--speed", type=float, default=1.0, help="speech speed, e.g. 0.9 or 1.1")
    sp.add_argument("--lang", help="Kokoro language code (default: first letter of the voice)")
    sp.add_argument("--device", choices=["cpu", "cuda", "mps"], help="torch device (default: auto)")
    sp.add_argument("--engine", choices=["kokoro", "dummy"], default="kokoro",
                    help="'dummy' makes beeps instead of speech - for testing the pipeline quickly")
    sp.add_argument("--bitrate", default="64k", help="AAC bitrate (default 64k, fine for speech)")
    sp.add_argument("--only-chapters", help="only synthesize these chapters, e.g. 1-3,7")
    sp.add_argument("--re-extract", action="store_true", help="re-read the PDF even if book.json exists")
    sp.set_defaults(func=cmd_generate)

    sp = sub.add_parser("build", help="rebuild m4b/epub/app-bundle from an existing work folder")
    sp.add_argument("--work", required=True)
    sp.add_argument("--out", default="output")
    sp.add_argument("--bitrate", default="64k")
    sp.set_defaults(func=cmd_build)

    sp = sub.add_parser("serve", help="share finished books with the phone app over Wi-Fi")
    sp.add_argument("--out", default="output")
    sp.add_argument("--port", type=int, default=8765)
    sp.set_defaults(func=cmd_serve)

    sp = sub.add_parser("voices", help="list some Kokoro voices")
    sp.set_defaults(func=lambda _: print(VOICES))

    args = p.parse_args(argv)
    args.func(args)
