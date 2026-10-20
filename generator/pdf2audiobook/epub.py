"""Minimal EPUB 3 writer (no extra dependencies)."""

from __future__ import annotations

import html
import uuid
import zipfile
from pathlib import Path


def _xhtml(title: str, body: str) -> str:
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">\n'
        f"<head><meta charset=\"utf-8\"/><title>{html.escape(title)}</title>"
        '<link rel="stylesheet" href="style.css"/></head>\n'
        f"<body>\n{body}\n</body>\n</html>\n"
    )


def write_epub(out: Path, title: str, author: str, chapters: list[tuple[str, list[str]]],
               cover: Path | None = None, lang: str = "en") -> None:
    book_id = f"urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, title + author)}"
    manifest, spine, nav = [], [], []
    files: dict[str, str | bytes] = {
        "OEBPS/style.css": "body{font-family:serif;line-height:1.5;margin:0 5%}h1{text-align:center;margin:2em 0 1em}"
                           "p{text-indent:1.2em;margin:0 0 .4em}img{max-width:100%}",
    }
    manifest.append('<item id="css" href="style.css" media-type="text/css"/>')

    if cover:
        files["OEBPS/cover.jpg"] = cover.read_bytes()
        files["OEBPS/cover.xhtml"] = _xhtml(title, f'<div style="text-align:center"><img src="cover.jpg" alt="cover"/></div>')
        manifest.append('<item id="cover-image" href="cover.jpg" media-type="image/jpeg" properties="cover-image"/>')
        manifest.append('<item id="cover" href="cover.xhtml" media-type="application/xhtml+xml"/>')
        spine.append('<itemref idref="cover"/>')

    for i, (name, paragraphs) in enumerate(chapters, 1):
        fname = f"ch{i:03d}.xhtml"
        body = f"<h1>{html.escape(name)}</h1>\n" + "\n".join(f"<p>{html.escape(p)}</p>" for p in paragraphs)
        files[f"OEBPS/{fname}"] = _xhtml(name, body)
        manifest.append(f'<item id="ch{i}" href="{fname}" media-type="application/xhtml+xml"/>')
        spine.append(f'<itemref idref="ch{i}"/>')
        nav.append(f'<li><a href="{fname}">{html.escape(name)}</a></li>')

    files["OEBPS/nav.xhtml"] = _xhtml(
        "Contents", f'<nav epub:type="toc" id="toc"><h1>Contents</h1><ol>{"".join(nav)}</ol></nav>'
    )
    manifest.append('<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>')
    files["OEBPS/content.opf"] = f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="bookid">{book_id}</dc:identifier>
    <dc:title>{html.escape(title)}</dc:title>
    <dc:creator>{html.escape(author)}</dc:creator>
    <dc:language>{lang}</dc:language>
    <meta property="dcterms:modified">2000-01-01T00:00:00Z</meta>
  </metadata>
  <manifest>
    {chr(10).join("    " + m for m in manifest).strip()}
  </manifest>
  <spine>
    {chr(10).join("    " + s for s in spine).strip()}
  </spine>
</package>
"""
    files["META-INF/container.xml"] = """<?xml version="1.0" encoding="utf-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>
"""
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w") as z:
        # The mimetype entry must be first and uncompressed.
        z.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        for name, data in files.items():
            z.writestr(name, data, compress_type=zipfile.ZIP_DEFLATED)
