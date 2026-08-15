from __future__ import annotations

from pathlib import Path

from trackdna.analyze import analyze_track


COMPARE_KEYS = [
    ("tempo_bpm", "Tempo (BPM)"),
    ("key", "Key"),
    ("swing_class", "Swing"),
    ("onset_density", "Onset density"),
    ("off_pulse_ratio", "Off-pulse"),
    ("syncopation_ratio", "Syncopation"),
    ("percussive_share", "Percussive share"),
    ("integrated_rms_db", "Integrated RMS (dB)"),
    ("true_peak_db", "True peak (dB)"),
    ("crest_factor_db", "Crest (dB)"),
    ("loudness_range_db", "Loudness range (dB)"),
    ("spectral_centroid_hz", "Centroid (Hz)"),
    ("stereo_width", "Stereo width"),
]


def compare_tracks(path_a: str | Path, path_b: str | Path, progress=None) -> dict:
    a = analyze_track(path_a, progress=progress)
    b = analyze_track(path_b, progress=progress)
    deltas = []
    for key, label in COMPARE_KEYS:
        va, vb = a.get(key), b.get(key)
        row = {"field": label, "a": va, "b": vb, "delta": None}
        if isinstance(va, (int, float)) and isinstance(vb, (int, float)):
            row["delta"] = round(float(vb) - float(va), 3)
        elif va != vb:
            row["delta"] = "changed"
        else:
            row["delta"] = "same"
        deltas.append(row)

    band_deltas = []
    bands_a = {row["name"]: row["energy_pct"] for row in a.get("band_energy", [])}
    for row in b.get("band_energy", []):
        name = row["name"]
        band_deltas.append(
            {
                "name": name,
                "a": bands_a.get(name),
                "b": row["energy_pct"],
                "delta": round(row["energy_pct"] - bands_a.get(name, 0.0), 2),
            }
        )

    return {
        "a": a,
        "b": b,
        "deltas": deltas,
        "band_deltas": band_deltas,
    }


def format_compare(result: dict) -> str:
    a_name = result["a"].get("source_name", "A")
    b_name = result["b"].get("source_name", "B")
    lines = [f"A/B COMPARE — {a_name}  →  {b_name}", "=" * 64, ""]
    lines.append(f"{'Field':<24} {'A':>12} {'B':>12} {'Δ':>10}")
    for row in result["deltas"]:
        lines.append(
            f"{row['field']:<24} {_cell(row['a']):>12} {_cell(row['b']):>12} {_cell(row['delta']):>10}"
        )
    lines.append("")
    lines.append("Band energy %")
    for row in result["band_deltas"]:
        lines.append(
            f"  {row['name']:<10} {row['a']:>6.1f}  →  {row['b']:>6.1f}   Δ {row['delta']:+.1f}"
        )
    return "\n".join(lines)


def _cell(value) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)
