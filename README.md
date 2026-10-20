# PDF → Audiobook (Kokoro TTS) + phone app

Turn any text PDF into a **chaptered audiobook** using the free, local
[Kokoro](https://huggingface.co/hexgrad/Kokoro-82M) text-to-speech model, then
listen *and read along* on your phone.

```
pdf-to-epub-audiobook/
├── generator/   Python: PDF → chapters → Kokoro TTS → .m4b + .epub + app bundle
└── app/         Expo (React Native) app: library, player, chapter reader, remembers your place
```

## What you get

| Output | What it is |
| --- | --- |
| `output/<Book>/<Book>.m4b` | The audiobook, one file with **chapter markers** and cover. Plays in any audiobook player (Apple Books, BookPlayer, Smart AudioBook Player, VLC…). |
| `output/<Book>/<Book>.epub` | The text as an e-book with the same chapters. |
| `output/<Book>/app-bundle/` | Per-chapter audio + text with sentence timings, for the phone app. |

## Highlights

- **Never loses progress.** The book is split into small sentence-sized pieces and
  each one is saved to disk as soon as it's spoken. Close the laptop, press
  Ctrl+C, lose power — just run the same command again and it continues where it
  stopped (at most one sentence is redone).
- **Finds chapters automatically** — from the PDF's bookmarks if it has them,
  otherwise from headings like "Chapter 7", "PART II", "Prologue", or big
  heading text. Falls back to fixed-size parts. You can check and rename them
  before generating.
- **Cleans the text** — removes running headers/footers and page numbers, re-joins
  hyphenated words and paragraphs split across pages.
- **Phone app** — your library, a player (speed, sleep timer, ±15/30s, lock-screen
  controls, background play), and a chapter **reader that highlights the sentence
  being spoken**. Tap any sentence to jump there. It remembers exactly where you
  stopped and resumes there next time you open the book.

---

## 1. Generate an audiobook (on your computer)

Needs **Python 3.10–3.12** and **ffmpeg**. A GPU is optional (Kokoro runs fine on
CPU, just slower — roughly real-time or better on a modern laptop).

```bash
cd generator
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
# ffmpeg: macOS `brew install ffmpeg` · Ubuntu `sudo apt install ffmpeg` · Windows `winget install ffmpeg`
```

**Check the chapters first (optional but recommended):**

```bash
python -m pdf2audiobook inspect ~/Books/my-book.pdf
```

```
My Book — Some Author
Chapters found with method: toc

    1. Prologue                              1,204 words  (~8 min)
    2. Chapter 1: The Storm                  5,881 words  (~39 min)
    ...
  Total: 84,210 words, roughly 9.4 hours of audio.
```

Wrong titles or splits? Edit `work/my-book/book.json` (rename, delete or merge
chapters), or try `--chapters-from headings` / `--chapters-from pages`.

**Generate:**

```bash
python -m pdf2audiobook generate ~/Books/my-book.pdf
```

Stop it any time. To continue, run **the exact same command** again:

```
Resuming My Book from work/my-book
1830/4120 segments already done, 2290 to go. Loading TTS (kokoro)...
```

When every segment is done it builds the `.m4b`, `.epub` and `app-bundle/` into `output/`.

Useful options:

| Option | Meaning |
| --- | --- |
| `--voice bf_emma` | Pick a voice (`python -m pdf2audiobook voices` lists some). Default `af_heart`. |
| `--speed 1.1` | Speaking speed. |
| `--device cuda` | Force GPU (`cpu`, `cuda`, `mps`). Default picks automatically. |
| `--chapters-from toc\|headings\|pages` | Force a chapter-detection method. |
| `--only-chapters 1-3` | Try a few chapters first to hear the voice. |
| `--title "..." --author "..."` | Override the PDF's metadata. |
| `--engine dummy` | Beeps instead of speech — tests the whole pipeline in seconds. |

> Scanned PDFs (images of pages) have no text. Run them through OCR first, e.g.
> `ocrmypdf scanned.pdf text.pdf`.

## 2. Put it on your phone

### Install the app

The app is an [Expo](https://expo.dev) project. Quickest way to run it on your phone:

```bash
cd app
npm install
npx expo start
```

Install **Expo Go** from the App Store / Play Store and scan the QR code.

To get a real installable app (recommended for background playback and lock-screen
controls), build it once with EAS: `npx eas-cli build -p android --profile preview`
(gives you an `.apk`) or `-p ios`. Or with Android Studio / Xcode installed:
`npx expo run:android` / `npx expo run:ios`.

### Send books to it

**Over Wi-Fi (easiest):** on the computer run

```bash
python -m pdf2audiobook serve
```

It prints an address like `http://192.168.1.20:8765`. In the app tap
**Import from computer (Wi-Fi)**, enter that address, and tap the book to download it.
Phone and computer must be on the same network.

**Or by files:** copy the `output/<Book>/app-bundle/` folder to your phone (USB,
Google Drive, AirDrop…), tap **Import files from phone**, and select *all* files
in that folder.

## How resuming works (generator)

```
work/my-book/
  book.json        chapters + text split into sentence-sized segments
  settings.json    voice/speed used
  cover.jpg
  audio/xx/<hash>.wav   one file per segment, named by hash of (voice, speed, text)
```

Each WAV is written to a temporary file and renamed only when complete, so a
half-written file can never be mistaken for a finished one. On restart the
generator skips every segment whose WAV exists. Because files are named by their
text, editing `book.json` only re-synthesizes what you changed — and changing the
voice simply generates new files next to the old ones.

## Development

```bash
cd generator && pip install pytest reportlab && pytest     # end-to-end test with the dummy engine
cd app && npm run typecheck
```
