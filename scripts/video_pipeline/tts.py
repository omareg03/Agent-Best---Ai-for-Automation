"""Narration engines.

Priority (verified 2026-10-26):
  1. kokoro   -- Kokoro-82M, Apache-2.0, CPU-viable, commercial-safe. Default.
  2. edge     -- edge-tts >= 7.3.1 ONLY. Microsoft rotated the Sec-MS-GEC token on
                 2026-10-12 and every older release 403s (also 403s from GitHub-hosted
                 runners). Kept as an optional fallback, never the CI default.
  3. mock     -- deterministic formant synthesis, exact word timings, zero deps.
                 This is what CI and `selftest` use, so the assembly chain is
                 genuinely exercised instead of skipped.

F5-TTS (weights CC-BY-NC) and Fish Audio S2 (research licence) are intentionally
absent: this repo must stay commercial-safe by default.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import urllib.error
import urllib.request
import wave
from dataclasses import dataclass, field
from pathlib import Path

from .align import estimate_word_timings, syllables
from .captions import Word
from .config import (
    AUDIO_RATE,
    DEFAULT_EDGE_VOICE,
    DEFAULT_TTS_VOICE,
    KOKORO_TTS_URL,
)
from .errors import EngineError
from .ffmpeg_util import assert_artifact, probe, run_ffmpeg


@dataclass
class TTSResult:
    path: Path
    duration: float
    engine: str
    voice: str
    words: list[Word] = field(default_factory=list)
    exact_timings: bool = False
    cost_usd: float = 0.0


class TTSEngine:
    name = "base"
    commercial_safe = True

    def synthesize(self, text: str, out_path: Path, *, voice: str = "", seed: int = 0) -> TTSResult:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Mock: real audio, real timings, no model
# ---------------------------------------------------------------------------
_MOCK_SR = 48000


def _formant_gain(freq: float, formants: tuple[float, ...]) -> float:
    gain = 0.0
    for center in formants:
        bandwidth = 110.0
        gain += 1.0 / (1.0 + ((freq - center) / bandwidth) ** 2)
    return gain


def _synth_word(word: str, f0: float, rng: list[int]) -> tuple["object", float]:
    """Additive 'vowel-ish' syllable: harmonic stack shaped by 3 formants."""
    import numpy as np

    n_syll = syllables(word)
    duration = 0.17 * n_syll + 0.05
    samples = max(1, int(duration * _MOCK_SR))
    t = np.arange(samples) / _MOCK_SR

    rng[0] = (1103515245 * rng[0] + 12345) % (2**31)
    vowel = rng[0] % 5
    formants = {
        0: (730.0, 1090.0, 2440.0),  # a
        1: (530.0, 1840.0, 2480.0),  # e
        2: (270.0, 2290.0, 3010.0),  # i
        3: (570.0, 840.0, 2410.0),   # o
        4: (300.0, 870.0, 2240.0),   # u
    }[vowel]

    # Pitch: slight downward drift + vibrato (prosody, not a pure tone).
    pitch = f0 * (1.0 + 0.04 * np.sin(2 * np.pi * 1.7 * t)) - 6.0 * (t / max(duration, 1e-6))
    phase = 2 * np.pi * np.cumsum(pitch) / _MOCK_SR

    signal = np.zeros(samples)
    nyquist = _MOCK_SR / 2
    for harmonic in range(1, 18):
        freq = harmonic * f0
        if freq >= nyquist * 0.9:
            break
        amplitude = _formant_gain(freq, formants) / (harmonic**0.6)
        signal += amplitude * np.sin(harmonic * phase)
    if not np.any(signal):
        signal = np.sin(phase)

    # Envelope: 12 ms attack, 45 ms release, gentle syllable ripple.
    attack = max(1, int(0.012 * _MOCK_SR))
    release = max(1, int(0.045 * _MOCK_SR))
    envelope = np.ones(samples)
    envelope[:attack] = np.linspace(0, 1, attack)
    envelope[-release:] = np.linspace(1, 0, release)
    if n_syll > 1:
        envelope *= 0.82 + 0.18 * np.abs(np.sin(np.pi * n_syll * t / duration))
    signal *= envelope

    peak = float(np.max(np.abs(signal))) or 1.0
    return (signal / peak * 0.55).astype("float32"), duration


class MockTTS(TTSEngine):
    """Deterministic speech-like narration with exact word timing.

    Not intelligible speech -- a prosody-accurate stand-in whose *timings* are exact.
    That is the property the assembly chain needs to be tested against.
    """

    name = "mock"

    def synthesize(self, text: str, out_path: Path, *, voice: str = "", seed: int = 0) -> TTSResult:
        text = text.strip()
        if not text:
            raise EngineError("cannot synthesise empty narration")
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        digest = hashlib.sha256(f"{voice}|{seed}".encode()).digest()
        f0 = 95.0 + (digest[0] / 255.0) * 85.0
        rng = [int.from_bytes(digest[1:5], "big")]

        try:
            import numpy as np
        except ImportError:  # pragma: no cover - numpy is in CI, but stay runnable
            duration = max(1.0, len(text.split()) * 0.36)
            run_ffmpeg(
                ["-f", "lavfi", "-i", f"sine=frequency={f0:.1f}:sample_rate={_MOCK_SR}",
                 "-t", f"{duration:.3f}", "-ac", "1", "-c:a", "pcm_s16le", str(out_path)]
            )
            return TTSResult(out_path, probe(out_path).duration, self.name, voice or "mock",
                             estimate_word_timings(text, duration), False)

        chunks: list[object] = []
        words: list[Word] = []
        cursor = 0.0
        tokens = text.split()
        for index, token in enumerate(tokens):
            signal, duration = _synth_word(token, f0, rng)
            start = cursor
            end = start + duration
            words.append(Word(text=token, start=round(start, 3), end=round(end, 3)))
            chunks.append(signal)
            pause = 0.055
            if re.search(r"[.!?]$", token):
                pause = 0.30
            elif re.search(r"[,;:]$", token):
                pause = 0.13
            if index < len(tokens) - 1:
                chunks.append(np.zeros(int(pause * _MOCK_SR), dtype="float32"))
                cursor = end + pause
            else:
                cursor = end

        audio = np.concatenate(chunks) if chunks else np.zeros(_MOCK_SR, dtype="float32")
        peak = float(np.max(np.abs(audio)))
        if peak > 0:
            audio = audio / peak * 0.6
        pcm = (audio * 32767).astype("<i2")
        with wave.open(str(out_path), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(_MOCK_SR)
            handle.writeframes(pcm.tobytes())

        assert_artifact(out_path, min_bytes=2048, kind="narration")
        return TTSResult(
            path=out_path,
            duration=probe(out_path).duration,
            engine=self.name,
            voice=voice or "mock",
            words=words,
            exact_timings=True,
            cost_usd=0.0,
        )


# ---------------------------------------------------------------------------
# Kokoro (default production voice)
# ---------------------------------------------------------------------------
class KokoroTTS(TTSEngine):
    """Kokoro-82M through a Kokoro-FastAPI server (OpenAI-compatible endpoint).

    Self-host:  docker run -p 8880:8880 ghcr.io/remsky/kokoro-fastapi-cpu:latest
    Licence:    Apache-2.0 (model + code) -> commercial-safe.
    """

    name = "kokoro"

    def synthesize(self, text: str, out_path: Path, *, voice: str = "", seed: int = 0) -> TTSResult:
        text = text.strip()
        if not text:
            raise EngineError("cannot synthesise empty narration")
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path = out_path.with_suffix(".raw.wav")
        voice = voice or DEFAULT_TTS_VOICE

        payload = json.dumps(
            {"model": "kokoro", "input": text, "voice": voice, "response_format": "wav", "speed": 1.0}
        ).encode()
        request = urllib.request.Request(
            f"{KOKORO_TTS_URL.rstrip('/')}/v1/audio/speech",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=300) as response:
                raw_path.write_bytes(response.read())
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
            raise EngineError(
                f"Kokoro TTS unreachable at {KOKORO_TTS_URL}: {exc}",
                hint=(
                    "start Kokoro-FastAPI, set KOKORO_TTS_URL, or run with --tts mock "
                    "(mock produces exact timings and is what CI uses)"
                ),
                stage="tts",
            ) from exc

        assert_artifact(raw_path, min_bytes=2048, kind="kokoro output")
        run_ffmpeg(
            ["-i", str(raw_path), "-ar", str(AUDIO_RATE), "-ac", "1", "-c:a", "pcm_s16le", str(out_path)]
        )
        raw_path.unlink(missing_ok=True)
        duration = probe(out_path).duration
        return TTSResult(out_path, duration, self.name, voice, estimate_word_timings(text, duration), False)


# ---------------------------------------------------------------------------
# Edge (optional; broken before 7.3.1, and blocked on GitHub runners)
# ---------------------------------------------------------------------------
def edge_tts_version() -> str | None:
    try:
        from importlib.metadata import version

        return version("edge-tts")
    except Exception:  # noqa: BLE001
        return None


def _parse_srt_words(path: Path) -> list[Word]:
    if not path.exists():
        return []
    blocks = re.split(r"\n\s*\n", path.read_text(encoding="utf-8", errors="ignore").strip())
    words: list[Word] = []
    for block in blocks:
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        if len(lines) < 3:
            continue
        match = re.match(
            r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)", lines[1]
        )
        if not match:
            continue
        h1, m1, s1, ms1, h2, m2, s2, ms2 = (int(g) for g in match.groups())
        start = h1 * 3600 + m1 * 60 + s1 + ms1 / 1000
        end = h2 * 3600 + m2 * 60 + s2 + ms2 / 1000
        text = " ".join(lines[2:]).strip()
        if text:
            words.append(Word(text=text, start=start, end=end))
    return words


class EdgeTTS(TTSEngine):
    name = "edge"

    def synthesize(self, text: str, out_path: Path, *, voice: str = "", seed: int = 0) -> TTSResult:
        version = edge_tts_version()
        if version is None:
            raise EngineError(
                "edge-tts is not installed",
                hint="pip install 'edge-tts>=7.3.1'",
                stage="tts",
            )
        if tuple(int(p) for p in re.findall(r"\d+", version)[:3]) < (7, 3, 0):
            raise EngineError(
                f"edge-tts {version} cannot work: Microsoft rotated Sec-MS-GEC on 2026-10-12 "
                "and every release before 7.3.0 returns HTTP 403",
                hint="pip install --upgrade 'edge-tts>=7.3.1'",
                stage="tts",
            )

        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        mp3_path = out_path.with_suffix(".mp3")
        srt_path = out_path.with_suffix(".words.srt")
        voice = voice or DEFAULT_EDGE_VOICE
        proc = subprocess.run(
            [
                "python3", "-m", "edge_tts", "--voice", voice, "--text", text,
                "--write-media", str(mp3_path), "--write-subtitles", str(srt_path),
            ],
            capture_output=True,
            text=True,
            timeout=300,
        )
        if proc.returncode != 0 or not mp3_path.exists():
            raise EngineError(
                "edge-tts synthesis failed",
                hint=(proc.stderr or "").strip()[-400:] or "check network / voice name",
                stage="tts",
            )
        run_ffmpeg(
            ["-i", str(mp3_path), "-ar", str(AUDIO_RATE), "-ac", "1", "-c:a", "pcm_s16le", str(out_path)]
        )
        mp3_path.unlink(missing_ok=True)
        duration = probe(out_path).duration
        words = _parse_srt_words(srt_path)
        srt_path.unlink(missing_ok=True)
        exact = bool(words)
        return TTSResult(
            out_path, duration, self.name, voice,
            words if exact else estimate_word_timings(text, duration), exact,
        )


# ---------------------------------------------------------------------------
def get_tts_engine(name: str) -> TTSEngine:
    engines = {engine.name: engine for engine in (MockTTS(), KokoroTTS(), EdgeTTS())}
    if name not in engines:
        raise EngineError(f"unknown tts engine '{name}' (choose: {', '.join(sorted(engines))})")
    return engines[name]
