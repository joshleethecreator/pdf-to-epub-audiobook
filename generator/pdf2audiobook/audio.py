"""WAV I/O and ffmpeg helpers."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import wave
from pathlib import Path

import numpy as np

from .tts import SAMPLE_RATE


def require_ffmpeg() -> None:
    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            raise SystemExit(f"`{tool}` was not found on PATH. Install ffmpeg (https://ffmpeg.org/download.html).")


def write_wav_atomic(path: Path, audio: np.ndarray, rate: int = SAMPLE_RATE) -> None:
    """Write to a temp file then rename, so a half-written file never looks finished."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".wav.part")
    pcm = (np.clip(audio, -1.0, 1.0) * 32767).astype("<i2")
    with wave.open(str(tmp), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.tobytes())
    with open(tmp, "rb") as f:
        os.fsync(f.fileno())
    os.replace(tmp, path)


def wav_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / w.getframerate()


def silence_wav(directory: Path, seconds: float) -> Path:
    path = directory / f"silence_{int(seconds * 1000)}ms.wav"
    if not path.exists():
        write_wav_atomic(path, np.zeros(int(SAMPLE_RATE * seconds), dtype=np.float32))
    return path


def probe_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", str(path)],
        check=True, capture_output=True, text=True,
    ).stdout
    return float(json.loads(out)["format"]["duration"])


def _run_ffmpeg(args: list[str]) -> None:
    proc = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed:\n{' '.join(args)}\n{proc.stderr}")


def _concat_list(files: list[Path], list_path: Path) -> None:
    lines = []
    for f in files:
        escaped = str(f.resolve()).replace("'", "'\\''")
        lines.append(f"file '{escaped}'")
    list_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def encode_chapter(wavs: list[Path], out: Path, bitrate: str, scratch: Path) -> None:
    """Concatenate WAV pieces (sample-exact) and encode to AAC in one pass."""
    out.parent.mkdir(parents=True, exist_ok=True)
    scratch.mkdir(parents=True, exist_ok=True)
    lst = scratch / f"{out.stem}.concat.txt"
    tmp = scratch / f"{out.stem}.part.m4a"
    _concat_list(wavs, lst)
    _run_ffmpeg(["-f", "concat", "-safe", "0", "-i", str(lst), "-c:a", "aac", "-b:a", bitrate, "-ac", "1",
                 "-movflags", "+faststart", str(tmp)])
    lst.unlink()
    os.replace(tmp, out)


def _ffmeta_escape(s: str) -> str:
    for ch in ("\\", "=", ";", "#", "\n"):
        s = s.replace(ch, "\\" + ch)
    return s


def build_m4b(chapter_files: list[Path], chapters: list[tuple[str, float]], out: Path,
              title: str, author: str, cover: Path | None, scratch: Path) -> None:
    """Join chapter m4a files (no re-encode) into one .m4b with chapter markers."""
    scratch.mkdir(parents=True, exist_ok=True)
    lst = scratch / "m4b.concat.txt"
    meta = scratch / "m4b.ffmetadata.txt"
    _concat_list(chapter_files, lst)
    lines = [";FFMETADATA1", f"title={_ffmeta_escape(title)}", f"album={_ffmeta_escape(title)}",
             f"artist={_ffmeta_escape(author)}", "genre=Audiobook"]
    t = 0.0
    for name, dur in chapters:
        start, end = int(t * 1000), int((t + dur) * 1000)
        lines += ["[CHAPTER]", "TIMEBASE=1/1000", f"START={start}", f"END={end}", f"title={_ffmeta_escape(name)}"]
        t += dur
    meta.write_text("\n".join(lines) + "\n", encoding="utf-8")

    tmp = scratch / "book.part.m4b"
    args = ["-f", "concat", "-safe", "0", "-i", str(lst), "-i", str(meta)]
    if cover:
        args += ["-i", str(cover), "-map", "0:a", "-map", "2:v", "-c:v", "copy", "-disposition:v", "attached_pic"]
    else:
        args += ["-map", "0:a"]
    args += ["-map_metadata", "1", "-map_chapters", "1", "-c:a", "copy", "-movflags", "+faststart", "-f", "mp4", str(tmp)]
    _run_ffmpeg(args)
    lst.unlink()
    meta.unlink()
    os.replace(tmp, out)
