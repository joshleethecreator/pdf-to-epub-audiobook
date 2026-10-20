"""Serve the output folder over Wi-Fi so the mobile app can download books."""

from __future__ import annotations

import functools
import json
import socket
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def _lan_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))  # no packet is sent; just picks the LAN interface
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def library(out: Path) -> list[dict]:
    books = []
    for book_json in sorted(out.glob("*/app-bundle/book.json")):
        data = json.loads(book_json.read_text(encoding="utf-8"))
        rel = book_json.parent.relative_to(out).as_posix()
        books.append({
            "id": data["id"], "title": data["title"], "author": data["author"],
            "duration": data["duration"], "chapters": len(data["chapters"]),
            "path": rel + "/",
            "files": ["book.json"] + ([data["cover"]] if data.get("cover") else []) + [c["audio"] for c in data["chapters"]],
        })
    return books


class Handler(SimpleHTTPRequestHandler):
    out: Path

    def do_GET(self):
        if self.path.rstrip("/") in ("", "/library.json"):
            body = json.dumps({"books": library(self.out)}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()


def serve(out: Path, port: int) -> None:
    out = out.resolve()
    handler = functools.partial(Handler, directory=str(out))
    Handler.out = out
    books = library(out)
    print(f"Serving {len(books)} book(s) from {out}")
    for b in books:
        print(f"  - {b['title']}")
    print(f"\nIn the app tap 'Import from computer' and enter:\n\n    http://{_lan_ip()}:{port}\n")
    print("(phone and computer must be on the same Wi-Fi). Ctrl+C to stop.")
    ThreadingHTTPServer(("0.0.0.0", port), handler).serve_forever()
