"""Word-level timing.

Two paths, in order of truthfulness:
  1. whisperx forced alignment on the rendered narration (real timings, ~50 ms)
  2. deterministic estimator from the known script (approximate, honest about it)

We always have the transcript (we wrote the script), which is exactly the input a
forced aligner wants -- so the estimator is a fallback, never the goal.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from .captions import Word
from .errors import MediaError

VOWEL_GROUPS = re.compile(r"[aeiouy]+", re.IGNORECASE)
_PAUSE_RE = re.compile(r"[.!?]$")
_COMMA_RE = re.compile(r"[,;:]$")

# Punctuation pauses, in seconds.
STOP_PAUSE = 0.30
CLAUSE_PAUSE = 0.14


def syllables(word: str) -> int:
    cleaned = re.sub(r"[^a-zA-Z]", "", word)
    if not cleaned:
        return 1
    return max(1, len(VOWEL_GROUPS.findall(cleaned)))


def estimate_word_timings(
    text: str, duration: float, *, lead_in: float = 0.10, tail: float = 0.12, rate_wpm: float = 155.0
) -> list[Word]:
    """Distribute a known transcript across a known audio duration.

    Weight = syllable count, plus explicit pauses at punctuation. This is far better
    than uniform splitting and needs no GPU -- but it is still an estimate, and the
    caller records which method was used.
    """
    tokens = text.split()
    if not tokens:
        return []
    usable = max(0.2, duration - lead_in - tail)
    weights: list[float] = []
    pauses: list[float] = []
    for index, token in enumerate(tokens):
        weights.append(float(syllables(token)))
        pause = 0.0
        if index < len(tokens) - 1:
            if _PAUSE_RE.search(token):
                pause = STOP_PAUSE
            elif _COMMA_RE.search(token):
                pause = CLAUSE_PAUSE
        pauses.append(pause)

    total_pause = sum(pauses)
    weight_sum = sum(weights)
    # The measured audio duration is ground truth: the transcript MUST fit inside it.
    # (Expanding to a nominal words-per-minute would push captions past the audio and
    # desynchronise every cue after it -- a bug that is invisible until you watch it.)
    speech_time = max(0.2, usable - total_pause)
    if len(tokens) > 1:
        speech_time = min(speech_time, usable)

    words: list[Word] = []
    cursor = lead_in
    for index, (token, weight, pause) in enumerate(zip(tokens, weights, pauses)):
        share = speech_time * (weight / weight_sum)
        start = cursor
        end = start + share
        words.append(Word(text=token, start=round(start, 3), end=round(min(end, duration), 3)))
        cursor = end + pause
    return words


def whisperx_available() -> bool:
    if shutil.which("whisperx"):
        return True
    try:  # module installed but entry point missing
        import importlib.util

        return importlib.util.find_spec("whisperx") is not None
    except Exception:  # noqa: BLE001
        return False


def whisperx_align(
    audio: str | Path, *, language: str = "en", timeout: int = 1800
) -> list[Word] | None:
    """Forced alignment with whisperx. Returns None when unavailable or failed."""
    if not whisperx_available():
        return None
    audio = Path(audio).resolve()
    with tempfile.TemporaryDirectory(prefix="align_") as tmp:
        cmd = [
            shutil.which("whisperx") or "whisperx",
            str(audio),
            "--output_format", "json",
            "--output_dir", tmp,
            "--language", language,
            "--compute_type", "int8",
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        except (subprocess.TimeoutExpired, OSError):
            return None
        if proc.returncode != 0:
            return None
        candidates = sorted(Path(tmp).glob("*.json"))
        if not candidates:
            return None
        try:
            payload = json.loads(candidates[0].read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None

        words: list[Word] = []
        for segment in payload.get("segments", []):
            for item in segment.get("words", []) or []:
                if item.get("start") is None or item.get("end") is None:
                    continue
                text = str(item.get("word", "")).strip()
                if not text:
                    continue
                words.append(Word(text=text, start=float(item["start"]), end=float(item["end"])))
        return words or None


def align(
    audio: str | Path,
    text: str,
    duration: float,
    *,
    method: str = "auto",
    language: str = "en",
) -> tuple[list[Word], str]:
    """Return (words, method_used). 'method' is recorded in state + the render manifest."""
    if method in ("auto", "whisperx"):
        words = whisperx_align(audio, language=language)
        if words:
            return words, "whisperx"
        if method == "whisperx":
            raise MediaError(
                "whisperx alignment requested but unavailable/failed",
                hint="pip install 'whisperx>=3.8.4' (3.8.3 was yanked) or use --align estimate",
            )
    if method not in ("auto", "whisperx", "estimate"):
        raise MediaError(f"unknown alignment method: {method}")
    return estimate_word_timings(text, duration), "estimate"


def offset_words(words: list[Word], seconds: float) -> list[Word]:
    return [Word(w.text, round(w.start + seconds, 3), round(w.end + seconds, 3)) for w in words]
