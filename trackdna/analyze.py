from __future__ import annotations

from pathlib import Path

from trackdna import __version__
from trackdna.audio import load_audio
from trackdna.harmony import analyze_harmony
from trackdna.rhythm import analyze_rhythm
from trackdna.spectrum import analyze_spectrum
from trackdna.structure import analyze_structure
from trackdna.util import json_safe


def analyze_track(
    path: str | Path,
    segments: int | None = None,
    min_len: float = 8.0,
    progress=None,
) -> dict:
    audio = load_audio(path, progress=progress)
    rhythm = analyze_rhythm(audio, progress=progress)
    harmony = analyze_harmony(
        audio, rhythm["tempo_bpm"], y_harm=rhythm["y_harmonic"], progress=progress
    )
    spectrum = analyze_spectrum(audio, progress=progress)
    structure = analyze_structure(
        audio,
        rhythm,
        harmony,
        target_segments=segments,
        min_len=min_len,
        progress=progress,
    )

    if progress:
        progress("Building report")

    progression_by_section = [
        {
            "label": sec["label"],
            "start": sec["start"],
            "end": sec["end"],
            "chords": sec["chord_sequence"],
        }
        for sec in structure["sections"]
    ]

    result = {
        "analysis_version": __version__,
        "source_path": audio.path,
        "source_name": audio.name,
        "sample_rate": audio.sr,
        "channels": audio.channels,
        "duration_sec": round(audio.duration, 3),
        "tempo_bpm": rhythm["tempo_bpm"],
        "tempo_raw_bpm": rhythm["tempo_raw_bpm"],
        "tempo_corrected": rhythm["tempo_corrected"],
        "key": harmony["key"],
        "key_runner_up": harmony["key_runner_up"],
        "key_confidence": harmony["key_confidence"],
        "beat_count": rhythm["beat_count"],
        "swing_class": rhythm["swing_class"],
        "swing_ratio": rhythm["swing_ratio"],
        "onset_density": rhythm["onset_density"],
        "off_pulse_ratio": rhythm["off_pulse_ratio"],
        "syncopation_ratio": rhythm["syncopation_ratio"],
        "percussive_share": rhythm["percussive_share"],
        "chord_progression": harmony["chord_progression"],
        "chord_change_count": harmony["chord_change_count"],
        "harmonic_rhythm_sec": harmony["harmonic_rhythm_sec"],
        "harmonic_rhythm_bars": harmony["harmonic_rhythm_bars"],
        "progression_by_section": progression_by_section,
        "integrated_rms_db": spectrum["integrated_rms_db"],
        "true_peak_db": spectrum["true_peak_db"],
        "crest_factor_db": spectrum["crest_factor_db"],
        "loudness_range_db": spectrum["loudness_range_db"],
        "spectral_centroid_hz": spectrum["spectral_centroid_hz"],
        "spectral_rolloff_hz": spectrum["spectral_rolloff_hz"],
        "spectral_bandwidth_hz": spectrum["spectral_bandwidth_hz"],
        "spectral_flatness": spectrum["spectral_flatness"],
        "stereo_width": spectrum["stereo_width"],
        "band_energy": spectrum["band_energy"],
        "mix_diagnostics": spectrum["mix_diagnostics"],
        "sections": structure["sections"],
        "target_segments": structure["target_segments"],
    }
    return json_safe(result)
