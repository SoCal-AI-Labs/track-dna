from __future__ import annotations

import librosa
import numpy as np

from trackdna.audio import Audio
from trackdna.util import safe_div


def analyze_rhythm(audio: Audio, progress=None) -> dict:
    if progress:
        progress("Measuring tempo and groove")

    y, sr = audio.y, audio.sr
    raw_tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, units="frames")
    raw_bpm = float(np.atleast_1d(raw_tempo)[0])
    tempo_bpm, tempo_corrected = _octave_correct(raw_bpm)
    beats = librosa.frames_to_time(beat_frames, sr=sr)
    if beats.size == 0:
        beats = np.array([0.0, audio.duration], dtype=float)
    beats = _resample_beats_for_octave(beats, raw_bpm, tempo_bpm)

    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    onset_frames = librosa.onset.onset_detect(
        onset_envelope=onset_env, sr=sr, units="frames", backtrack=False
    )
    onsets = librosa.frames_to_time(onset_frames, sr=sr)
    onset_density = safe_div(float(onsets.size), audio.duration)

    y_harm, y_perc = librosa.effects.hpss(y)
    perc_energy = float(np.sum(y_perc**2))
    total_energy = float(np.sum(y**2))
    percussive_share = safe_div(perc_energy, total_energy)

    median_ioi = float(np.median(np.diff(beats))) if beats.size > 1 else 60.0 / max(tempo_bpm, 1.0)
    off_pulse_ratio, syncopation_ratio = _grid_stats(onsets, beats, median_ioi)
    swing_ratio, swing_class = _swing(onsets, beats)

    return {
        "tempo_bpm": round(tempo_bpm, 2),
        "tempo_raw_bpm": round(raw_bpm, 2),
        "tempo_corrected": bool(tempo_corrected),
        "beat_count": int(max(beats.size, 0)),
        "beats": beats.astype(float),
        "onsets": onsets.astype(float),
        "onset_density": round(onset_density, 3),
        "off_pulse_ratio": round(off_pulse_ratio, 3),
        "syncopation_ratio": round(syncopation_ratio, 3),
        "swing_ratio": round(swing_ratio, 3),
        "swing_class": swing_class,
        "percussive_share": round(percussive_share, 3),
        "y_harmonic": y_harm,
        "y_percussive": y_perc,
        "median_beat_sec": round(median_ioi, 4),
    }


def _octave_correct(raw_bpm: float) -> tuple[float, bool]:
    bpm = float(raw_bpm)
    if bpm <= 0:
        return 120.0, False
    if bpm < 70:
        return bpm * 2.0, True
    if bpm > 180:
        return bpm / 2.0, True
    return bpm, False


def _resample_beats_for_octave(beats: np.ndarray, raw_bpm: float, corrected_bpm: float) -> np.ndarray:
    if corrected_bpm == raw_bpm or beats.size < 2:
        return beats
    if corrected_bpm > raw_bpm:  # doubled -> interpolate midpoints
        midpoints = (beats[:-1] + beats[1:]) / 2.0
        return np.sort(np.concatenate([beats, midpoints]))
    return beats[::2]  # halved -> keep every other beat


def _grid_stats(onsets: np.ndarray, beats: np.ndarray, median_ioi: float) -> tuple[float, float]:
    if onsets.size == 0 or beats.size < 2:
        return 0.0, 0.0

    beat_tol = 0.20 * median_ioi
    sixteenths = _subdivide(beats, 4)
    sixteenth_tol = max(0.035, 0.40 * (median_ioi / 4.0))

    off = 0
    sync = 0
    for t in onsets:
        if float(np.min(np.abs(beats - t))) > beat_tol:
            off += 1
        if float(np.min(np.abs(sixteenths - t))) > sixteenth_tol:
            sync += 1
    n = float(onsets.size)
    return off / n, sync / n


def _subdivide(beats: np.ndarray, parts: int) -> np.ndarray:
    if beats.size < 2:
        return beats
    grid = []
    for a, b in zip(beats[:-1], beats[1:]):
        grid.extend(np.linspace(a, b, parts, endpoint=False))
    grid.append(float(beats[-1]))
    return np.asarray(grid, dtype=float)


def _swing(onsets: np.ndarray, beats: np.ndarray) -> tuple[float, str]:
    if onsets.size < 8 or beats.size < 3:
        return 1.0, "straight"

    phases = []
    for a, b in zip(beats[:-1], beats[1:]):
        dur = b - a
        if dur <= 0:
            continue
        inside = onsets[(onsets >= a) & (onsets < b)]
        for t in inside:
            phase = float((t - a) / dur)
            if 0.35 <= phase <= 0.75:
                phases.append(phase)

    if len(phases) < 8:
        return 1.0, "straight"

    offbeat = float(np.median(phases))
    iqr = float(np.percentile(phases, 75) - np.percentile(phases, 25))
    if iqr > 0.18:
        return 1.0, "straight"
    swing_ratio = offbeat / max(1.0 - offbeat, 1e-6)
    if swing_ratio < 1.15:
        return swing_ratio, "straight"
    if swing_ratio < 1.6:
        return swing_ratio, "light swing"
    return swing_ratio, "heavy swing"
