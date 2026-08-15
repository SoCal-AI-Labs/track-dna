from __future__ import annotations

import librosa
import numpy as np

from trackdna.audio import Audio
from trackdna.harmony import chords_in_window, format_progression
from trackdna.spectrum import spectral_tilt_label
from trackdna.util import nearest, safe_div

GRID_SEC = 0.5


def analyze_structure(
    audio: Audio,
    rhythm: dict,
    harmony: dict,
    target_segments: int | None = None,
    min_len: float = 8.0,
    progress=None,
) -> dict:
    if progress:
        progress("Detecting song structure")

    y, sr = audio.y, audio.sr
    hop = int(GRID_SEC * sr)
    if hop < 1:
        hop = sr // 2

    chroma = librosa.feature.chroma_stft(y=y, sr=sr, hop_length=hop)
    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13, hop_length=hop)
    rms = librosa.feature.rms(y=y, hop_length=hop)[0]
    perc = librosa.feature.rms(y=rhythm["y_percussive"], hop_length=hop)[0]
    centroid = librosa.feature.spectral_centroid(y=y, sr=sr, hop_length=hop)[0]

    n = min(chroma.shape[1], mfcc.shape[1], rms.size)
    chroma, mfcc = chroma[:, :n], mfcc[:, :n]
    rms, perc, centroid = rms[:n], perc[:n], centroid[:n]
    times = librosa.frames_to_time(np.arange(n), sr=sr, hop_length=hop)

    features = _stack_features(chroma, mfcc, rms)
    novelty = _foote_novelty(features, kernel_size=8)
    if target_segments is None:
        target_segments = int(np.clip(round(audio.duration / 16.0), 4, 12))
    target_segments = int(np.clip(target_segments, 2, 16))

    min_frames = max(2, int(min_len / GRID_SEC))
    peaks = _pick_peaks(novelty, target_segments - 1, min_frames)
    bounds = np.concatenate(([0], peaks, [n - 1]))
    bounds = np.unique(bounds)

    beats = np.asarray(rhythm["beats"], dtype=float)
    sections = []
    for i in range(len(bounds) - 1):
        a, b = int(bounds[i]), int(bounds[i + 1])
        if b <= a:
            continue
        start = nearest(beats, float(times[a])) if a > 0 else 0.0
        end = nearest(beats, float(times[min(b, n - 1)]))
        if i == len(bounds) - 2:
            end = audio.duration
        if end - start < min_len * 0.55 and sections:
            sections[-1]["end"] = end
            continue
        sl = slice(a, max(b, a + 1))
        level = float(np.mean(rms[sl]))
        perc_share = safe_div(float(np.mean(perc[sl] ** 2)), float(np.mean(rms[sl] ** 2) + 1e-12))
        tilt_hz = float(np.mean(centroid[sl]))
        feat = np.concatenate(
            [
                chroma[:, sl].mean(axis=1),
                mfcc[:, sl].mean(axis=1),
                np.array([level * 4.0]),  # energy weighted heavily
            ]
        )
        sections.append(
            {
                "start": start,
                "end": end,
                "level": level,
                "percussive_pct": 100.0 * perc_share,
                "spectral_tilt_hz": tilt_hz,
                "feature": feat,
            }
        )

    if not sections:
        sections = [
            {
                "start": 0.0,
                "end": audio.duration,
                "level": float(np.mean(rms)),
                "percussive_pct": 50.0,
                "spectral_tilt_hz": float(np.mean(centroid)),
                "feature": features.mean(axis=0),
            }
        ]

    _merge_short(sections, min_len * 0.7)
    clusters = _cluster_sections(sections)
    labels = _label_sections(sections, clusters)
    chords = harmony["chord_progression"]

    out = []
    for i, sec in enumerate(sections):
        names = chords_in_window(chords, sec["start"], sec["end"])
        energy_bar = _energy_bar(sec["level"], [s["level"] for s in sections])
        out.append(
            {
                "index": i + 1,
                "label": labels[i],
                "start": round(float(sec["start"]), 2),
                "end": round(float(sec["end"]), 2),
                "length_sec": round(float(sec["end"] - sec["start"]), 2),
                "level": round(float(sec["level"]), 5),
                "percussive_pct": round(float(sec["percussive_pct"]), 1),
                "spectral_tilt": spectral_tilt_label(sec["spectral_tilt_hz"]),
                "spectral_tilt_hz": round(float(sec["spectral_tilt_hz"]), 1),
                "energy_bar": energy_bar,
                "chords": names,
                "chord_sequence": format_progression(names, key=harmony.get("key", "")),
                "cluster": int(clusters[i]),
            }
        )

    return {
        "sections": out,
        "target_segments": target_segments,
        "novelty": novelty,
    }


def _stack_features(chroma: np.ndarray, mfcc: np.ndarray, rms: np.ndarray) -> np.ndarray:
    parts = [
        _zscore(chroma.T),
        _zscore(mfcc.T),
        _zscore(rms.reshape(-1, 1)),
    ]
    return np.concatenate(parts, axis=1)


def _zscore(x: np.ndarray) -> np.ndarray:
    mu = x.mean(axis=0, keepdims=True)
    sd = x.std(axis=0, keepdims=True)
    sd[sd < 1e-8] = 1.0
    return (x - mu) / sd


def _foote_novelty(features: np.ndarray, kernel_size: int = 8) -> np.ndarray:
    x = features / (np.linalg.norm(features, axis=1, keepdims=True) + 1e-9)
    ssm = np.clip(x @ x.T, -1.0, 1.0)
    k = max(4, kernel_size)
    if k % 2:
        k += 1
    half = k // 2
    kernel = np.ones((k, k))
    kernel[:half, half:] = -1
    kernel[half:, :half] = -1
    n = ssm.shape[0]
    novelty = np.zeros(n, dtype=float)
    for i in range(half, n - half):
        patch = ssm[i - half : i + half, i - half : i + half]
        novelty[i] = float(np.sum(patch * kernel))
    novelty = np.maximum(novelty, 0.0)
    if novelty.max() > 0:
        novelty = novelty / novelty.max()
    return novelty


def _pick_peaks(novelty: np.ndarray, count: int, min_distance: int) -> np.ndarray:
    if novelty.size < 3 or count <= 0:
        return np.array([], dtype=int)
    cand = []
    for i in range(1, novelty.size - 1):
        if novelty[i] >= novelty[i - 1] and novelty[i] >= novelty[i + 1] and novelty[i] > 0.12:
            cand.append((float(novelty[i]), i))
    cand.sort(reverse=True)
    chosen: list[int] = []
    for _, idx in cand:
        if all(abs(idx - c) >= min_distance for c in chosen):
            chosen.append(idx)
        if len(chosen) >= count:
            break
    return np.array(sorted(chosen), dtype=int)


def _merge_short(sections: list[dict], min_len: float) -> None:
    i = 0
    while i < len(sections):
        length = sections[i]["end"] - sections[i]["start"]
        if length < min_len and len(sections) > 1:
            if i == 0:
                sections[1]["start"] = sections[0]["start"]
                sections.pop(0)
                continue
            sections[i - 1]["end"] = sections[i]["end"]
            sections.pop(i)
            continue
        i += 1


def _cluster_sections(sections: list[dict]) -> list[int]:
    feats = np.stack([s["feature"] for s in sections])
    n = len(sections)
    if n == 1:
        return [0]
    n_clusters = int(np.clip(round(n * 0.55), 2, min(5, n)))
    try:
        from sklearn.cluster import AgglomerativeClustering

        model = AgglomerativeClustering(n_clusters=n_clusters, linkage="ward")
        return [int(x) for x in model.fit_predict(feats)]
    except Exception:
        return _fallback_cluster(feats, n_clusters)


def _fallback_cluster(feats: np.ndarray, n_clusters: int) -> list[int]:
    # simple farthest-first + nearest assignment
    feats = _zscore(feats)
    centers = [0]
    for _ in range(n_clusters - 1):
        d = np.min(
            [np.linalg.norm(feats - feats[c], axis=1) for c in centers],
            axis=0,
        )
        centers.append(int(np.argmax(d)))
    labels = []
    for row in feats:
        dist = [float(np.linalg.norm(row - feats[c])) for c in centers]
        labels.append(int(np.argmin(dist)))
    return labels


def _label_sections(sections: list[dict], clusters: list[int]) -> list[str]:
    n = len(sections)
    energies = np.array([s["level"] for s in sections], dtype=float)
    median_e = float(np.median(energies))
    labels = ["section"] * n

    cluster_energy = {}
    cluster_count = {}
    for i, c in enumerate(clusters):
        cluster_energy.setdefault(c, []).append(energies[i])
        cluster_count[c] = cluster_count.get(c, 0) + 1
    cluster_mean = {c: float(np.mean(v)) for c, v in cluster_energy.items()}

    repeated = [c for c, k in cluster_count.items() if k >= 2]
    if repeated:
        chorus_c = max(repeated, key=lambda c: cluster_mean[c])
        verse_candidates = [c for c in repeated if c != chorus_c]
        verse_c = max(verse_candidates, key=lambda c: cluster_count[c]) if verse_candidates else None
    else:
        chorus_c = max(cluster_mean, key=cluster_mean.get)
        verse_c = min(cluster_mean, key=cluster_mean.get) if len(cluster_mean) > 1 else None

    verse_n = 0
    chorus_n = 0
    for i, c in enumerate(clusters):
        if c == chorus_c:
            chorus_n += 1
            labels[i] = "chorus" if chorus_n == 1 else f"chorus {chorus_n}"
        elif verse_c is not None and c == verse_c:
            verse_n += 1
            labels[i] = "verse" if verse_n == 1 else f"verse {verse_n}"
        elif cluster_mean[c] > median_e * 1.15 and cluster_count[c] == 1 and i not in (0, n - 1):
            labels[i] = "bridge"
        else:
            labels[i] = "section"

    if n >= 2 and energies[0] <= median_e * 0.85:
        labels[0] = "intro"
    if n >= 2 and energies[-1] <= median_e * 0.9:
        labels[-1] = "outro"

    # pre-chorus: unlabeled medium-energy section immediately before a chorus
    for i in range(n - 1):
        if labels[i] == "section" and labels[i + 1].startswith("chorus"):
            labels[i] = "pre-chorus"
    return labels


def _energy_bar(level: float, levels: list[float], width: int = 12) -> str:
    hi = max(levels) if levels else 1.0
    frac = safe_div(level, hi, default=0.0)
    filled = int(round(frac * width))
    return "#" * filled + "-" * (width - filled)
