from __future__ import annotations

import librosa
import numpy as np
from scipy.ndimage import median_filter

from trackdna.audio import Audio
from trackdna.util import safe_div

PITCH_CLASSES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# Krumhansl-Schmuckler key profiles
MAJOR_PROFILE = np.array(
    [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88],
    dtype=float,
)
MINOR_PROFILE = np.array(
    [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17],
    dtype=float,
)

MAJOR_TRIAD = np.array([1.0, 0, 0, 0, 1.0, 0, 0, 1.0, 0, 0, 0, 0])
MINOR_TRIAD = np.array([1.0, 0, 0, 1.0, 0, 0, 0, 1.0, 0, 0, 0, 0])


def analyze_harmony(audio: Audio, tempo_bpm: float, y_harm=None, progress=None) -> dict:
    if progress:
        progress("Detecting key and chords")

    y = audio.y if y_harm is None else y_harm
    sr = audio.sr
    hop = 2048
    try:
        chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=hop)
    except Exception:
        chroma = librosa.feature.chroma_stft(y=y, sr=sr, hop_length=hop)

    chroma = np.maximum(chroma, 0.0)
    chroma = librosa.util.normalize(chroma, axis=0)
    times = librosa.frames_to_time(np.arange(chroma.shape[1]), sr=sr, hop_length=hop)

    key, runner_up, confidence = _estimate_key(chroma.mean(axis=1))
    chords = _track_chords(chroma, times)
    named = [c["chord"] for c in chords if c["chord"] != "N"]
    named = _dedupe_adjacent(named)
    changes = max(len(named) - 1, 0)
    if len(chords) >= 2:
        gaps = [
            chords[i + 1]["time"] - chords[i]["time"]
            for i in range(len(chords) - 1)
            if chords[i + 1]["chord"] != "N"
        ]
        harm_sec = float(np.mean(gaps)) if gaps else audio.duration
    else:
        harm_sec = audio.duration

    bar_sec = 4.0 * (60.0 / max(tempo_bpm, 1.0))
    harm_bars = safe_div(harm_sec, bar_sec)

    return {
        "key": key,
        "key_runner_up": runner_up,
        "key_confidence": round(confidence, 3),
        "chord_progression": chords,
        "chord_change_count": int(changes),
        "harmonic_rhythm_sec": round(harm_sec, 3),
        "harmonic_rhythm_bars": round(harm_bars, 3),
        "chroma": chroma,
        "chroma_times": times,
        "chroma_hop": hop,
    }


def chords_in_window(chords: list[dict], start: float, end: float) -> list[str]:
    covering = [c["chord"] for c in chords if c["time"] <= start]
    names = [covering[-1]] if covering else []
    for item in chords:
        if start < item["time"] < end:
            names.append(item["chord"])
    return _dedupe_adjacent(names)


SHARP_TO_FLAT = {"C#": "Db", "D#": "Eb", "F#": "Gb", "G#": "Ab", "A#": "Bb"}
FLAT_KEY_NAMES = {
    "F major",
    "Bb major",
    "Eb major",
    "Ab major",
    "Db major",
    "Gb major",
    "D minor",
    "G minor",
    "C minor",
    "F minor",
    "Bb minor",
    "Eb minor",
}


def prefers_flats(key: str) -> bool:
    return key in FLAT_KEY_NAMES or key.startswith(("F ", "Bb", "Eb", "Ab", "Db", "Gb"))


def spell_chord(chord: str, key: str) -> str:
    if not chord or chord == "N":
        return chord
    if not prefers_flats(key):
        return chord
    for sharp, flat in SHARP_TO_FLAT.items():
        if chord.startswith(sharp):
            return flat + chord[len(sharp) :]
    return chord


def spell_key(key: str) -> str:
    if not key:
        return key
    root, _, mode = key.partition(" ")
    return f"{spell_chord(root, key)} {mode}".strip()


def format_progression(names: list[str], limit: int = 12, key: str = "") -> str:
    clean = []
    for name in names:
        spelled = spell_chord(name, key) if key else name
        if not spelled or spelled == "N":
            continue
        if not clean or clean[-1] != spelled:
            clean.append(spelled)
    if not clean:
        return "n/a"
    if len(clean) > limit:
        return "-".join(clean[:limit]) + "…"
    return "-".join(clean)


def _estimate_key(chroma_mean: np.ndarray) -> tuple[str, str, float]:
    vec = np.asarray(chroma_mean, dtype=float)
    if vec.sum() <= 0:
        return "C major", "A minor", 0.0
    vec = vec / (np.linalg.norm(vec) + 1e-9)

    scores = []
    for i, name in enumerate(PITCH_CLASSES):
        maj = np.roll(MAJOR_PROFILE, i)
        minor = np.roll(MINOR_PROFILE, i)
        maj = maj / (np.linalg.norm(maj) + 1e-9)
        minor = minor / (np.linalg.norm(minor) + 1e-9)
        scores.append((float(vec @ maj), f"{name} major"))
        scores.append((float(vec @ minor), f"{name} minor"))

    scores.sort(key=lambda x: x[0], reverse=True)
    best, runner = scores[0], scores[1]
    span = best[0] - scores[-1][0]
    confidence = safe_div(best[0] - runner[0], span if span > 1e-6 else 1.0)
    return best[1], runner[1], float(np.clip(confidence, 0.0, 1.0))


def _track_chords(chroma: np.ndarray, times: np.ndarray) -> list[dict]:
    templates = []
    labels = []
    for i, name in enumerate(PITCH_CLASSES):
        templates.append(np.roll(MAJOR_TRIAD, i))
        labels.append(f"{name}")
        templates.append(np.roll(MINOR_TRIAD, i))
        labels.append(f"{name}m")
    templates = np.stack(templates)
    templates = templates / (np.linalg.norm(templates, axis=1, keepdims=True) + 1e-9)

    frames = chroma / (np.linalg.norm(chroma, axis=0, keepdims=True) + 1e-9)
    sims = templates @ frames
    idx = np.argmax(sims, axis=0)
    best = sims[idx, np.arange(sims.shape[1])]
    codes = idx.astype(np.int32)
    codes[best < 0.72] = -1
    codes = median_filter(codes, size=9)

    chords = []
    last = None
    for t, code in zip(times, codes):
        label = "N" if int(code) < 0 else labels[int(code)]
        if label != last:
            chords.append({"time": round(float(t), 3), "chord": label})
            last = label
    if not chords:
        chords = [{"time": 0.0, "chord": "N"}]
    return _drop_short_chords(chords, min_sec=0.75)


def _drop_short_chords(chords: list[dict], min_sec: float) -> list[dict]:
    if len(chords) < 2:
        return chords
    kept = [chords[0]]
    for i in range(1, len(chords)):
        prev = kept[-1]
        dur = chords[i]["time"] - prev["time"]
        if dur < min_sec:
            kept[-1] = chords[i]
        else:
            kept.append(chords[i])
    return _dedupe_chord_events(kept)


def _dedupe_chord_events(chords: list[dict]) -> list[dict]:
    out = []
    for item in chords:
        if out and out[-1]["chord"] == item["chord"]:
            continue
        out.append(item)
    return out or chords


def _dedupe_adjacent(names: list[str]) -> list[str]:
    out = []
    for name in names:
        if not out or out[-1] != name:
            out.append(name)
    return out
