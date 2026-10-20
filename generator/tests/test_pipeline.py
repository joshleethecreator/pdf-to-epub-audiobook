"""End-to-end test with the dummy engine (no model download needed).

Run:  pip install pytest reportlab pymupdf numpy && pytest
"""

import json
import shutil
import subprocess

import pytest

from pdf2audiobook import pipeline
from pdf2audiobook.chunker import chunk_paragraph, split_sentences
from pdf2audiobook.extract import extract_book

reportlab = pytest.importorskip("reportlab")


def make_pdf(path, bookmarks: bool):
    from reportlab.lib.pagesizes import A5
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate

    st = getSampleStyleSheet()
    story = [Paragraph("The Test Book", st["Title"]), PageBreak()]
    for c in range(1, 4):
        h = Paragraph(f"Chapter {c}", st["Heading1"])
        h._bm = f"Chapter {c}" if bookmarks else None
        story.append(h)
        for p in range(6):
            story.append(Paragraph(
                f"Paragraph {p} of chapter {c}. Dr. Smith said hello to Mrs. Jones, who waved. "
                "It was a long day, and the sun was setting slowly over the quiet hills.", st["BodyText"]))
        story.append(PageBreak())

    def footer(canv, doc):
        canv.setFont("Helvetica", 8)
        canv.drawString(30, 15, f"Page {doc.page}")

    class Doc(SimpleDocTemplate):
        def afterFlowable(self, f):
            if getattr(f, "_bm", None):
                self.canv.bookmarkPage(f._bm)
                self.canv.addOutlineEntry(f._bm, f._bm, 0)

    Doc(str(path), pagesize=A5, title="The Test Book", author="Jane Doe").build(
        story, onFirstPage=footer, onLaterPages=footer)


def test_sentences_keep_abbreviations():
    assert split_sentences("Dr. Smith came. Then he left!") == ["Dr. Smith came.", "Then he left!"]


def test_chunks_are_bounded():
    text = "word " * 500
    assert all(len(c) <= 400 for c in chunk_paragraph(text))


@pytest.mark.parametrize("bookmarks,method", [(True, "toc"), (False, "headings")])
def test_chapter_detection(tmp_path, bookmarks, method):
    pdf = tmp_path / "b.pdf"
    make_pdf(pdf, bookmarks)
    book = extract_book(pdf)
    assert book.method == method
    assert [c.title for c in book.chapters] == ["Chapter 1", "Chapter 2", "Chapter 3"]
    assert all("Page" not in p for c in book.chapters for p in c.paragraphs)  # footer removed
    assert book.author == "Jane Doe"


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg")
def test_generate_resume_and_build(tmp_path):
    pdf = tmp_path / "b.pdf"
    make_pdf(pdf, True)
    work, out = tmp_path / "work", tmp_path / "out"
    book = pipeline.prepare(pdf, work)
    pipeline.synthesize(work, book, "dummy", "af_heart", 1.0, None, None, chapters=[1])
    settings = pipeline.load_settings(work)
    assert 0 < pipeline.missing_segments(work, book, settings) < sum(len(pipeline.segments_of(c)) for c in book["chapters"])

    pipeline.synthesize(work, book, "dummy", "af_heart", 1.0, None, None)  # resumes
    assert pipeline.missing_segments(work, book, settings) == 0

    dest = pipeline.assemble(work, book, out)
    m4b = next(dest.glob("*.m4b"))
    chapters = json.loads(subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_chapters", str(m4b)],
        capture_output=True, text=True, check=True).stdout)["chapters"]
    assert [c["tags"]["title"] for c in chapters] == ["Chapter 1", "Chapter 2", "Chapter 3"]

    bundle = json.loads((dest / "app-bundle" / "book.json").read_text())
    assert len(bundle["chapters"]) == 3
    segs = bundle["chapters"][0]["segments"]
    assert segs[0]["p"] == -1 and all(a["end"] <= b["start"] for a, b in zip(segs, segs[1:]))
    assert all((dest / "app-bundle" / c["audio"]).exists() for c in bundle["chapters"])
    assert next(dest.glob("*.epub")).exists()
