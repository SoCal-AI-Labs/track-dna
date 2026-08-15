from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

from trackdna.analyze import analyze_track
from trackdna.suno import format_suno


def _tone(freq: float, t: np.ndarray, amp: float = 0.2) -> np.ndarray:
    return amp * np.sin(2 * np.pi * freq * t)


def _kick(sr: int, n: int) -> np.ndarray:
    t = np.arange(n) / sr
    env = np.exp(-t * 18)
    return 0.9 * env * np.sin(2 * np.pi * 55 * t)


def write_synthetic(path: Path, bpm: float = 128.0, seconds: float = 24.0) -> None:
    sr = 22050
    n = int(seconds * sr)
    y = np.zeros(n, dtype=np.float32)
    beat = 60.0 / bpm
    # Am (A3 C4 E4) for 8s, C (C4 E4 G4) for 8s, Am again, C again
    chords = [
        (0.0, 8.0, [220.00, 261.63, 329.63]),
        (8.0, 16.0, [261.63, 329.63, 392.00]),
        (16.0, 24.0, [220.00, 261.63, 329.63]),
    ]
    t = np.arange(n) / sr
    for start, end, freqs in chords:
        mask = (t >= start) & (t < end)
        for f in freqs:
            y[mask] += _tone(f, t[mask], amp=0.12)
    # kicks on every beat
    step = int(beat * sr)
    kick = _kick(sr, int(0.2 * sr))
    for i in range(0, n, step):
        j = min(n, i + kick.size)
        y[i:j] += kick[: j - i]
    y = np.clip(y, -1.0, 1.0)
    sf.write(path, y, sr)


def test_synthetic_tempo_and_suno():
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "synth.wav"
        write_synthetic(wav)
        dna = analyze_track(wav, segments=4, min_len=4.0)
        assert 118 <= dna["tempo_bpm"] <= 138
        assert dna["duration_sec"] >= 20
        assert len(dna["sections"]) >= 2
        assert dna["key"].split()[0] in {"A", "C", "Am", "C#", "G", "E", "F"}
        suno = format_suno(dna, instrumental=True, detailed=True)
        assert "BPM" in suno["style"]
        assert any(tag in suno["lyrics"] for tag in ("[Intro]", "[Verse]", "[Chorus]", "[Outro]", "[Break]"))
        assert "(" not in suno["lyrics"]
        assert len(suno["style"]) <= 1000
        assert len(suno["lyrics"]) <= 3000
        assert suno["style_chars"] > 80
