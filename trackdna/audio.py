from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf


ANALYSIS_SR = 22050


@dataclass
class Audio:
    path: str
    y: np.ndarray
    y_stereo: np.ndarray
    sr: int
    duration: float
    channels: int

    @property
    def name(self) -> str:
        return Path(self.path).name


def load_audio(path: str | Path, sr: int = ANALYSIS_SR, progress=None) -> Audio:
    path = str(Path(path).expanduser().resolve())
    if progress:
        progress("Loading audio")

    try:
        y, _ = librosa.load(path, sr=sr, mono=True)
    except Exception as exc:
        raise RuntimeError(
            f"Could not load '{path}'. Install FFmpeg for MP3/M4A, or use WAV/FLAC.\n{exc}"
        ) from exc

    if y.size == 0:
        raise RuntimeError(f"Audio file is empty: {path}")

    try:
        y_st, _ = librosa.load(path, sr=sr, mono=False)
    except Exception:
        y_st = y.copy()

    if y_st.ndim == 1:
        y_stereo = np.stack([y_st, y_st], axis=0)
        channels = _channel_count(path, default=1)
    else:
        y_stereo = np.asarray(y_st)
        if y_stereo.shape[0] > 2:
            y_stereo = y_stereo[:2]
        channels = int(y_stereo.shape[0])

    duration = float(y.size / sr)
    if duration < 1.0:
        raise RuntimeError("Track is shorter than 1 second — nothing useful to analyze.")

    return Audio(
        path=path,
        y=np.asarray(y, dtype=np.float32),
        y_stereo=np.asarray(y_stereo, dtype=np.float32),
        sr=sr,
        duration=duration,
        channels=channels,
    )


def _channel_count(path: str, default: int = 1) -> int:
    try:
        info = sf.info(path)
        return int(info.channels)
    except Exception:
        return default
