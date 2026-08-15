from __future__ import annotations

from trackdna.harmony import format_progression


def format_report(dna: dict) -> str:
    lines = []
    lines.append(f"TRACK DNA — {dna.get('source_name', 'unknown')}")
    lines.append("=" * 64)
    lines.append("")
    lines.append("OVERVIEW")
    lines.append(f"  Duration     { _hms(dna['duration_sec']) } ({dna['duration_sec']:.1f}s)")
    tempo = f"{dna['tempo_bpm']:.1f} BPM"
    if dna.get("tempo_corrected"):
        tempo += f"  (raw detector {dna['tempo_raw_bpm']:.1f})"
    lines.append(f"  Tempo        {tempo}")
    key = dna["key"]
    if dna.get("key_confidence", 1) < 0.5:
        key += f"  | runner-up {dna['key_runner_up']}  (confidence {dna['key_confidence']:.2f})"
    else:
        key += f"  (confidence {dna['key_confidence']:.2f})"
    lines.append(f"  Key          {key}")
    lines.append(f"  Beats        {dna['beat_count']}")
    lines.append("")

    lines.append("RHYTHM & FEEL")
    lines.append(f"  Swing        {dna['swing_class']}  (ratio {dna['swing_ratio']:.2f})")
    lines.append(f"  Onsets       {dna['onset_density']:.2f} / sec")
    lines.append(f"  Off-pulse    {dna['off_pulse_ratio']:.2f}   (not on the quarter-note pulse)")
    lines.append(f"  Syncopation  {dna['syncopation_ratio']:.2f}   (misses the 16th-note grid)")
    lines.append(f"  Percussive   {100 * dna['percussive_share']:.1f}% of total energy")
    lines.append("")

    prog = format_progression(
        [c["chord"] for c in dna.get("chord_progression", [])],
        limit=16,
        key=dna.get("key", ""),
    )
    lines.append("HARMONY")
    lines.append(f"  Progression  {prog}")
    lines.append(f"  Changes      {dna['chord_change_count']}")
    lines.append(
        f"  Harm. rhythm {dna['harmonic_rhythm_sec']:.2f}s  ({dna['harmonic_rhythm_bars']:.2f} bars)"
    )
    lines.append("")

    lines.append("LOUDNESS & DYNAMICS")
    lines.append(f"  Integrated   {dna['integrated_rms_db']:.1f} dBFS")
    lines.append(f"  True peak    {dna['true_peak_db']:.1f} dBFS")
    lines.append(f"  Crest        {dna['crest_factor_db']:.1f} dB")
    lines.append(f"  Loudness rng {dna['loudness_range_db']:.1f} dB")
    lines.append("")

    lines.append("SPECTRUM")
    lines.append(f"  Centroid     {dna['spectral_centroid_hz']:.0f} Hz")
    lines.append(f"  Rolloff      {dna['spectral_rolloff_hz']:.0f} Hz")
    lines.append(f"  Bandwidth    {dna['spectral_bandwidth_hz']:.0f} Hz")
    lines.append(f"  Flatness     {dna['spectral_flatness']:.3f}")
    lines.append(f"  Stereo width {dna['stereo_width']:.2f}")
    lines.append("  7-band energy")
    for band in dna.get("band_energy", []):
        bar = _pct_bar(band["energy_pct"])
        lines.append(
            f"    {band['name']:<10} {band['range_hz']:<12} {band['energy_pct']:5.1f}%  {bar}"
        )
    lines.append("")

    lines.append("MIX DIAGNOSTICS")
    for item in dna.get("mix_diagnostics", []):
        lines.append(f"  [{item['severity'].upper():<4}] {item['name']:<16} {item['reason']}")
    lines.append("")

    lines.append("STRUCTURE")
    for sec in dna.get("sections", []):
        lines.append(
            f"  {sec['start']:6.1f}-{sec['end']:6.1f}  {sec['label']:<12}  "
            f"{sec['length_sec']:5.1f}s  perc {sec['percussive_pct']:4.0f}%  "
            f"{sec['spectral_tilt']:<8}  {sec['energy_bar']}  {sec['chord_sequence']}"
        )
    lines.append("")
    lines.append("Notes: section names are heuristic. Boundaries, tempo, key, and mix numbers are measured.")
    return "\n".join(lines)


def _hms(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _pct_bar(pct: float, width: int = 16) -> str:
    filled = int(round((pct / 100.0) * width))
    filled = min(width, max(0, filled))
    return "#" * filled + "-" * (width - filled)
