from __future__ import annotations

import librosa
import numpy as np
from scipy.signal import resample_poly

from trackdna.audio import Audio
from trackdna.util import db

BANDS = [
    ("sub", 20, 60),
    ("bass", 60, 250),
    ("low_mid", 250, 500),
    ("mid", 500, 2000),
    ("high_mid", 2000, 6000),
    ("presence", 6000, 10000),
    ("air", 10000, 20000),
]


def analyze_spectrum(audio: Audio, progress=None) -> dict:
    if progress:
        progress("Measuring loudness, spectrum, and mix")

    y, sr = audio.y, audio.sr
    hop = 512
    rms = librosa.feature.rms(y=y, hop_length=hop)[0]
    rms = np.maximum(rms, 1e-12)
    integrated_rms = float(np.sqrt(np.mean(y**2)))
    true_peak = _true_peak(audio.y_stereo if audio.channels > 1 else y)
    crest = safe_crest(true_peak, integrated_rms)

    frame_db = 20.0 * np.log10(rms)
    p10, p95 = np.percentile(frame_db, [10, 95])
    loudness_range = float(p95 - p10)

    centroid = float(np.mean(librosa.feature.spectral_centroid(y=y, sr=sr)))
    rolloff = float(np.mean(librosa.feature.spectral_rolloff(y=y, sr=sr, roll_percent=0.85)))
    bandwidth = float(np.mean(librosa.feature.spectral_bandwidth(y=y, sr=sr)))
    flatness = float(np.mean(librosa.feature.spectral_flatness(y=y)))
    stereo_width = _stereo_width(audio.y_stereo)
    band_energy = _band_energy(y, sr)
    noise_floor_db = max(float(np.percentile(frame_db, 5)), -90.0)

    diagnostics = _mix_diagnostics(
        band_energy=band_energy,
        crest_db=crest,
        loudness_range_db=loudness_range,
        noise_floor_db=noise_floor_db,
        stereo_width=stereo_width,
    )

    return {
        "integrated_rms_db": round(db(integrated_rms), 2),
        "true_peak_db": round(db(true_peak), 2),
        "crest_factor_db": round(crest, 2),
        "loudness_range_db": round(loudness_range, 2),
        "spectral_centroid_hz": round(centroid, 1),
        "spectral_rolloff_hz": round(rolloff, 1),
        "spectral_bandwidth_hz": round(bandwidth, 1),
        "spectral_flatness": round(flatness, 4),
        "stereo_width": round(stereo_width, 3),
        "band_energy": band_energy,
        "noise_floor_db": round(noise_floor_db, 2),
        "mix_diagnostics": diagnostics,
        "rms_frames": rms,
        "rms_hop": hop,
    }


def safe_crest(peak: float, rms: float) -> float:
    if rms <= 1e-12:
        return 0.0
    return db(peak) - db(rms)


def _true_peak(y: np.ndarray) -> float:
    x = np.asarray(y, dtype=np.float64)
    if x.ndim == 2:
        x = x.reshape(-1)
    # 4x upsample approximates inter-sample peaks
    up = resample_poly(x, 4, 1)
    return float(np.max(np.abs(up)))


def _stereo_width(y_stereo: np.ndarray) -> float:
    if y_stereo.ndim != 2 or y_stereo.shape[0] < 2:
        return 0.0
    left, right = y_stereo[0], y_stereo[1]
    if left.size != right.size:
        n = min(left.size, right.size)
        left, right = left[:n], right[:n]
    mid = 0.5 * (left + right)
    side = 0.5 * (left - right)
    mid_e = float(np.mean(mid**2))
    side_e = float(np.mean(side**2))
    if mid_e + side_e <= 1e-12:
        return 0.0
    corr = float(np.corrcoef(left, right)[0, 1])
    if np.isnan(corr):
        corr = 1.0
    width = 0.5 * (1.0 - abs(corr)) + 0.5 * (side_e / (mid_e + side_e))
    return float(np.clip(width, 0.0, 1.0))


def _band_energy(y: np.ndarray, sr: int) -> list[dict]:
    n_fft = 4096
    S = np.abs(librosa.stft(y, n_fft=n_fft)) ** 2
    freqs = librosa.fft_frequencies(sr=sr, n_fft=n_fft)
    total = float(np.sum(S)) + 1e-12
    rows = []
    for name, lo, hi in BANDS:
        mask = (freqs >= lo) & (freqs < hi)
        share = float(np.sum(S[mask]) / total) if np.any(mask) else 0.0
        rows.append(
            {
                "name": name,
                "range_hz": f"{lo}-{hi}",
                "energy_pct": round(100.0 * share, 2),
            }
        )
    return rows


def _band_map(band_energy: list[dict]) -> dict[str, float]:
    return {row["name"]: float(row["energy_pct"]) for row in band_energy}


def _mix_diagnostics(
    band_energy: list[dict],
    crest_db: float,
    loudness_range_db: float,
    noise_floor_db: float,
    stereo_width: float,
) -> list[dict]:
    b = _band_map(band_energy)
    out = []

    mud = b.get("low_mid", 0.0)
    if mud >= 22:
        out.append(_diag("muddiness", "high", f"Low-mids ({mud:.1f}% @ 250-500 Hz) are crowding the mix."))
    elif mud >= 18:
        out.append(_diag("muddiness", "warn", f"Low-mids are a bit thick ({mud:.1f}%)."))
    else:
        out.append(_diag("muddiness", "ok", f"Low-mids sit at {mud:.1f}% — clear enough."))

    harsh = b.get("high_mid", 0.0)
    if harsh >= 28:
        out.append(_diag("harshness", "high", f"High-mids ({harsh:.1f}% @ 2-6 kHz) risk bite/fatigue."))
    elif harsh >= 23:
        out.append(_diag("harshness", "warn", f"High-mids are forward ({harsh:.1f}%)."))
    else:
        out.append(_diag("harshness", "ok", f"High-mids at {harsh:.1f}% look controlled."))

    sib = b.get("presence", 0.0)
    if sib >= 15:
        out.append(_diag("sibilance_risk", "high", f"Presence band is hot ({sib:.1f}% @ 6-10 kHz)."))
    elif sib >= 12:
        out.append(_diag("sibilance_risk", "warn", f"Presence energy is elevated ({sib:.1f}%)."))
    else:
        out.append(_diag("sibilance_risk", "ok", f"Presence band at {sib:.1f}% — sibilance risk is low."))

    sub = b.get("sub", 0.0)
    if sub >= 25:
        out.append(_diag("sub_weight", "high", f"Sub is heavy ({sub:.1f}% @ 20-60 Hz)."))
    elif sub < 4:
        out.append(_diag("sub_weight", "warn", f"Sub is thin ({sub:.1f}%)."))
    else:
        out.append(_diag("sub_weight", "ok", f"Sub weight is {sub:.1f}%."))

    air = b.get("air", 0.0)
    if air < 1.0:
        out.append(_diag("air", "warn", f"Little air above 10 kHz ({air:.1f}%) — top end may sound closed."))
    elif air >= 12:
        out.append(_diag("air", "warn", f"Air band is bright ({air:.1f}%)."))
    else:
        out.append(_diag("air", "ok", f"Air band at {air:.1f}%."))

    if crest_db < 6 or loudness_range_db < 5:
        out.append(
            _diag(
                "dynamics",
                "high",
                f"Crushed dynamics (crest {crest_db:.1f} dB, LRA {loudness_range_db:.1f} dB).",
            )
        )
    elif crest_db < 8 or loudness_range_db < 7:
        out.append(
            _diag(
                "dynamics",
                "warn",
                f"Limited dynamics (crest {crest_db:.1f} dB, LRA {loudness_range_db:.1f} dB).",
            )
        )
    else:
        out.append(
            _diag(
                "dynamics",
                "ok",
                f"Dynamics are open (crest {crest_db:.1f} dB, LRA {loudness_range_db:.1f} dB).",
            )
        )

    if noise_floor_db > -40:
        out.append(_diag("noise_floor", "warn", f"Quietest frames sit at {noise_floor_db:.1f} dBFS."))
    else:
        out.append(_diag("noise_floor", "ok", f"Noise floor around {noise_floor_db:.1f} dBFS."))

    if stereo_width < 0.08:
        out.append(_diag("stereo_image", "ok", "Image is narrow / mostly mono."))
    elif stereo_width > 0.7:
        out.append(_diag("stereo_image", "warn", "Very wide image — check phase on small speakers."))
    else:
        out.append(_diag("stereo_image", "ok", f"Stereo width {stereo_width:.2f}."))

    return out


def _diag(name: str, severity: str, reason: str) -> dict:
    return {"name": name, "severity": severity, "reason": reason}


# imported by report for tilt language
def spectral_tilt_label(centroid_hz: float) -> str:
    if centroid_hz < 1200:
        return "dark"
    if centroid_hz < 2000:
        return "warm"
    if centroid_hz < 3200:
        return "balanced"
    if centroid_hz < 4500:
        return "bright"
    return "brittle"
