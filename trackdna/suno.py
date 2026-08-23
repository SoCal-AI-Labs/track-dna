from __future__ import annotations

from trackdna.harmony import format_progression, spell_key
from trackdna.spectrum import spectral_tilt_label

STYLE_LIMIT = 1000
LYRICS_LIMIT = 3000


def format_suno(dna: dict, instrumental: bool = True, detailed: bool = True) -> dict:
    instrumental = True
    style = _style_line(dna, instrumental=instrumental, detailed=detailed)
    lyrics = _lyrics_block(dna, instrumental=instrumental, detailed=detailed)
    style = _clip(style, STYLE_LIMIT)
    lyrics = _clip(lyrics, LYRICS_LIMIT)
    paste = (
        "=== PASTE INTO SUNO / MINIMAX → STYLE ===\n"
        f"{style}\n\n"
        "=== PASTE INTO SUNO / MINIMAX → STRUCTURE (tags only, no lyrics) ===\n"
        f"{lyrics}\n"
    )
    return {
        "style": style,
        "lyrics": lyrics,
        "paste": paste,
        "instrumental": instrumental,
        "detailed": detailed,
        "style_chars": len(style),
        "lyrics_chars": len(lyrics),
    }


def _style_line(dna: dict, instrumental: bool, detailed: bool) -> str:
    if not detailed:
        return _join_budget(_compact_tags(dna, instrumental), STYLE_LIMIT)
    return _join_budget(_dna_clauses(dna, instrumental), STYLE_LIMIT)


def _compact_tags(dna: dict, instrumental: bool) -> list[str]:
    genres = [g for g in (dna.get("genres") or []) if g][:3]
    tags = genres or [_measured_genre(dna)]
    artist = _artist_clause(dna)
    if artist:
        tags.append(artist)
    tags.extend([_mood_short(dna), "instrumental"])
    tags.extend(_instrument_short(dna))
    tags.append(_image_clause(dna))
    tags.append(f"{_bpm(dna)} BPM")
    return _dedupe(tags)[:10]


def _dna_clauses(dna: dict, instrumental: bool) -> list[str]:
    key = spell_key(dna.get("key", ""))
    runner = spell_key(dna.get("key_runner_up", ""))
    clauses = [
        _genre_clause(dna),
        _artist_clause(dna),
        key,
        f"{_bpm(dna)} BPM",
        _groove_clause(dna),
        _drum_clause(dna),
        _low_end_clause(dna),
        _body_clause(dna),
        _top_clause(dna),
        _image_clause(dna),
        _dynamics_clause(dna),
        _harmony_clause(dna),
        _form_clause(dna),
        _avoid_clause(dna),
    ]
    if dna.get("key_confidence", 1) < 0.35 and runner:
        clauses.insert(2, f"alt {runner}")
    clauses.append("instrumental no vocals")
    return [c for c in clauses if c]


def _lyrics_block(dna: dict, instrumental: bool, detailed: bool) -> str:
    key = dna.get("key", "")
    lines: list[str] = []
    sections = dna.get("sections") or []
    for sec in sections:
        tag = _suno_section_tag(sec["label"])
        lines.append(f"[{tag}]")
        lines.append("[Instrumental]")
        if detailed:
            lines.append(f"[{_stamp(sec['start'])}-{_stamp(sec['end'])}]")
            for extra in _section_detail_tags(sec, key):
                lines.append(f"[{extra}]")
        else:
            for extra in _section_short_tags(sec, True):
                lines.append(f"[{extra}]")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _section_detail_tags(sec: dict, key: str) -> list[str]:
    tags = []
    energy = _energy_word(sec.get("energy_bar", ""))
    tilt = sec.get("spectral_tilt", "balanced")
    perc = float(sec.get("percussive_pct", 0))
    if perc <= 20:
        drums = "sparse drums"
    elif perc <= 35:
        drums = "dry pocket drums"
    else:
        drums = "drums forward"
    tags.append(f"{tilt} {energy} {drums}")
    chords = format_progression(sec.get("chords") or [], limit=8, key=key)
    if chords != "n/a":
        tags.append(f"chords {chords}")
    tags.append(f"{sec['length_sec']:.0f}s")
    return tags[:4]


def _section_short_tags(sec: dict, instrumental: bool) -> list[str]:
    tags = []
    tags.append(sec.get("spectral_tilt", "balanced"))
    perc = float(sec.get("percussive_pct", 0))
    if perc >= 55:
        tags.append("drums forward")
    elif perc <= 30:
        tags.append("sparse drums")
    return tags[:4]


def _suno_section_tag(label: str) -> str:
    raw = label.lower().strip()
    mapping = {
        "intro": "Intro",
        "outro": "Outro",
        "bridge": "Bridge",
        "pre-chorus": "Pre-Chorus",
        "chorus": "Chorus",
        "verse": "Verse",
        "section": "Break",
    }
    for key, tag in mapping.items():
        if raw.startswith(key):
            suffix = raw[len(key) :].strip()
            if suffix.isdigit():
                return f"{tag} {suffix}"
            return tag
    return label.title()


def _genre_clause(dna: dict) -> str:
    measured = _measured_genre(dna)
    genres = [g for g in (dna.get("genres") or []) if g]
    identity = dna.get("identity") or {}
    if not genres:
        genres = [g for g in (identity.get("genres") or []) if g]
    if genres:
        head = ", ".join(genres[:5])
        if measured and measured.lower() not in head.lower():
            return f"{head}, measured feel {measured}"
        return head
    return measured


def _artist_clause(dna: dict) -> str:
    artist = (dna.get("artist") or (dna.get("identity") or {}).get("artist") or "").strip()
    if not artist:
        return ""
    return f"in the vein of {artist}"


def _measured_genre(dna: dict) -> str:
    bpm = dna["tempo_bpm"]
    perc = dna["percussive_share"]
    swing = dna["swing_class"]
    onset = dna["onset_density"]
    centroid = dna["spectral_centroid_hz"]
    sub = _band(dna, "sub")
    bass = _band(dna, "bass")
    low = sub + bass
    air = _band(dna, "air")
    flat = dna["spectral_flatness"]

    if swing != "straight" and 70 <= bpm <= 110:
        return "dusty neo-soul"
    if bpm >= 160 and onset >= 4:
        return "drum and bass"
    if 120 <= bpm <= 136 and perc >= 0.45 and sub >= 12:
        return "house"
    if 130 <= bpm <= 150 and perc >= 0.4:
        return "techno"
    if low >= 55 and 68 <= bpm <= 88 and perc <= 0.35:
        return "dark 808 hip-hop"
    if 70 <= bpm <= 85 and sub >= 14:
        return "hip-hop"
    if 85 <= bpm <= 100 and perc >= 0.4:
        return "boom bap"
    if bpm >= 140 and centroid >= 2800:
        return "pop punk"
    if centroid < 1500 and perc < 0.3 and air < 2:
        return "dark ambient cinematic"
    if flat >= 0.15 and perc >= 0.4:
        return "industrial electronic"
    if 95 <= bpm <= 125 and 0.25 <= perc <= 0.5:
        return "indie electronic"
    return "alt pop"


def _mood_short(dna: dict) -> str:
    key = dna.get("key", "").lower()
    lra = dna["loudness_range_db"]
    mood = "moody" if "minor" in key else "bright"
    energy = "dynamic" if lra > 12 else "driving" if lra < 7 else "steady"
    return f"{mood} {energy}"


def _groove_clause(dna: dict) -> str:
    bits = [dna["swing_class"] + " groove"]
    if dna["tempo_bpm"] <= 90 and dna["onset_density"] <= 2.0:
        bits.append("half-time feel")
    if dna["off_pulse_ratio"] >= 0.25 and dna["syncopation_ratio"] <= 0.05:
        bits.append("off-beat percussion locked to a 16th grid")
    elif dna["syncopation_ratio"] >= 0.12:
        bits.append("true syncopation")
    if dna["onset_density"] < 1.4:
        bits.append("low event density")
    elif dna["onset_density"] > 3.5:
        bits.append("busy onsets")
    return ", ".join(bits)


def _drum_clause(dna: dict) -> str:
    perc = dna["percussive_share"]
    if perc < 0.22:
        return "sparse dry drums, kick and snare with little fill"
    if perc < 0.35:
        return "dry pocket drums under the bass"
    if perc < 0.5:
        return "punchy drums, groove-forward"
    return "drums dominate the mix"


def _low_end_clause(dna: dict) -> str:
    sub = _band(dna, "sub")
    bass = _band(dna, "bass")
    low = sub + bass
    if low >= 70:
        return f"808 sub and bass dominate the mix, about {low:.0f} percent of energy below 250 Hz"
    if low >= 50:
        return f"heavy low end, sub {sub:.0f} percent, bass {bass:.0f} percent"
    if sub < 5:
        return "thin sub, bass-light"
    return f"balanced low end, sub {sub:.0f} percent, bass {bass:.0f} percent"


def _body_clause(dna: dict) -> str:
    low_mid = _band(dna, "low_mid")
    mid = _band(dna, "mid")
    high_mid = _band(dna, "high_mid")
    body = low_mid + mid + high_mid
    if body <= 22 and _band(dna, "bass") >= 40:
        return "scooped mids, melody tucked behind the bass"
    if low_mid >= 20:
        return "warm thick low-mids"
    if high_mid >= 24:
        return "forward high-mids"
    return f"midrange body {body:.0f} percent"


def _top_clause(dna: dict) -> str:
    air = _band(dna, "air")
    presence = _band(dna, "presence")
    tilt = spectral_tilt_label(dna["spectral_centroid_hz"])
    if air < 1.0 and presence < 5:
        return f"{tilt} closed top, almost no air above 10 kHz"
    if air >= 8:
        return f"{tilt} open airy top"
    return f"{tilt} top end, presence {presence:.0f} percent, air {air:.0f} percent"


def _image_clause(dna: dict) -> str:
    w = dna["stereo_width"]
    if w < 0.1:
        return "dry centered near-mono image"
    if w < 0.3:
        return "narrow stereo"
    if w > 0.65:
        return "very wide stereo"
    return "wide stereo"


def _dynamics_clause(dna: dict) -> str:
    crest = dna["crest_factor_db"]
    lra = dna["loudness_range_db"]
    peak = dna["true_peak_db"]
    rms = dna["integrated_rms_db"]
    bits = [f"integrated {rms:.0f} dBFS", f"crest {crest:.0f} dB", f"LRA {lra:.0f} dB"]
    if peak >= 0:
        bits.append("true peak above 0, limited or clipped")
    if crest < 8 and lra < 7:
        bits.append("crushed loud")
    elif lra >= 12:
        bits.append("still dynamic")
    return ", ".join(bits)


def _harmony_clause(dna: dict) -> str:
    key = dna.get("key", "")
    names = [c["chord"] for c in dna.get("chord_progression", [])]
    prog = format_progression(names, limit=8, key=key)
    bars = dna.get("harmonic_rhythm_bars", 0)
    return f"slow harmony about {bars:.1f} bars per change, progression {prog}"


def _avoid_clause(dna: dict) -> str:
    avoids = []
    if _band(dna, "air") < 1.2:
        avoids.append("airy shimmer")
    if dna["stereo_width"] < 0.12:
        avoids.append("wide stereo FX")
    if dna["percussive_share"] < 0.32:
        avoids.append("busy trap hats")
    if _band(dna, "bass") + _band(dna, "sub") >= 60:
        avoids.append("thin small-speaker bass")
    if not avoids:
        return ""
    return "avoid " + ", ".join(avoids)


def _form_clause(dna: dict) -> str:
    labels = [_suno_section_tag(s["label"]) for s in dna.get("sections", [])]
    if not labels:
        return ""
    compact = []
    for name in labels:
        if not compact or compact[-1] != name:
            compact.append(name)
    return "form " + "-".join(compact[:10])


def _instrument_short(dna: dict) -> list[str]:
    tags = []
    if _band(dna, "sub") + _band(dna, "bass") >= 50:
        tags.append("808 bass")
    elif _band(dna, "sub") >= 14:
        tags.append("deep bass")
    perc = dna["percussive_share"]
    if perc >= 0.45:
        tags.append("punchy drums")
    else:
        tags.append("sparse drums")
    if _band(dna, "air") < 2 and _band(dna, "mid") < 12:
        tags.append("dark closed mix")
    else:
        tags.append("layered synths")
    return tags[:3]


def _energy_word(bar: str) -> str:
    if not bar:
        return "mid energy"
    filled = bar.count("#")
    total = max(len(bar), 1)
    frac = filled / total
    if frac < 0.35:
        return "low energy"
    if frac < 0.7:
        return "mid energy"
    return "high energy"


def _bpm(dna: dict) -> int:
    return int(round(dna["tempo_bpm"]))


def _stamp(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    m, s = divmod(seconds, 60)
    return f"{m}:{s:02d}"


def _band(dna: dict, name: str) -> float:
    for row in dna.get("band_energy", []):
        if row["name"] == name:
            return float(row["energy_pct"])
    return 0.0


def _dedupe(tags: list[str]) -> list[str]:
    seen = set()
    out = []
    for tag in tags:
        key = tag.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(tag)
    return out


def _join_budget(parts: list[str], limit: int) -> str:
    out = []
    used = 0
    for part in parts:
        piece = part.strip().rstrip(",")
        if not piece:
            continue
        extra = 2 if out else 0
        if used + extra + len(piece) > limit:
            continue
        out.append(piece)
        used += extra + len(piece)
    return ", ".join(out)


def _clip(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"
