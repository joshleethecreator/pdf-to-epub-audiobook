"""Text-to-speech engines. Kokoro is the real one; "dummy" is for quick tests."""

from __future__ import annotations

import numpy as np

SAMPLE_RATE = 24_000


class KokoroEngine:
    name = "kokoro"

    def __init__(self, voice: str, speed: float = 1.0, lang: str | None = None, device: str | None = None):
        try:
            from kokoro import KPipeline
        except ImportError as e:  # pragma: no cover - depends on user env
            raise SystemExit(
                "Kokoro is not installed. Run:  pip install -r requirements.txt\n"
                f"(import error: {e})"
            )
        self.voice = voice
        self.speed = speed
        # Voice names start with their language code: af_heart -> 'a' (American English).
        self.pipeline = KPipeline(lang_code=lang or voice[0], repo_id="hexgrad/Kokoro-82M", device=device)

    def synthesize(self, text: str) -> np.ndarray:
        chunks = [
            r.audio.detach().cpu().numpy()
            for r in self.pipeline(text, voice=self.voice, speed=self.speed, split_pattern=None)
            if r.audio is not None
        ]
        if not chunks:
            return np.zeros(int(SAMPLE_RATE * 0.2), dtype=np.float32)
        return np.concatenate(chunks).astype(np.float32)


class DummyEngine:
    """Produces a quiet tone whose length scales with the text. No model download."""

    name = "dummy"

    def __init__(self, *_, **__):
        pass

    def synthesize(self, text: str) -> np.ndarray:
        seconds = max(0.3, len(text) / 15)
        t = np.arange(int(SAMPLE_RATE * seconds)) / SAMPLE_RATE
        return (0.05 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


def make_engine(name: str, voice: str, speed: float, lang: str | None, device: str | None):
    if name == "dummy":
        return DummyEngine()
    return KokoroEngine(voice, speed, lang, device)
