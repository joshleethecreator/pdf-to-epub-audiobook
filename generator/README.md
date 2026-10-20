# pdf2audiobook (generator)

See the [main README](../README.md) for setup and usage.

```bash
python -m pdf2audiobook inspect  book.pdf      # show detected chapters
python -m pdf2audiobook generate book.pdf      # resumable: re-run to continue
python -m pdf2audiobook build --work work/book # rebuild outputs only
python -m pdf2audiobook serve                  # share output/ with the phone app over Wi-Fi
python -m pdf2audiobook voices                 # list voices
```

| Module | Job |
| --- | --- |
| `extract.py` | PDF → cleaned paragraphs → chapters (bookmarks → headings → pages) |
| `chunker.py` | paragraphs → sentence-aligned segments |
| `tts.py` | Kokoro engine (and a `dummy` engine for tests) |
| `pipeline.py` | resumable synthesis, chapter encoding, `.m4b` / `.epub` / app bundle |
| `audio.py`, `epub.py` | ffmpeg helpers, EPUB writer |
| `serve.py` | tiny HTTP server for the app's Wi-Fi import |
