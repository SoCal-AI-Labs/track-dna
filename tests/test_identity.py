from trackdna.identity import extract_genres, parse_title
from trackdna.suno import format_suno


def test_parse_title_dash():
    parsed = parse_title("Grave Digger - Rebellion (Official Video)")
    assert parsed["artist"] == "Grave Digger"
    assert "Rebellion" in parsed["title"]
    assert "Official" not in parsed["title"]


def test_parse_title_byline():
    parsed = parse_title("Nightcall by Kavinsky")
    assert parsed["artist"] == "Kavinsky"
    assert parsed["title"] == "Nightcall"


def test_extract_genres_from_tags_and_description():
    genres = extract_genres(
        "heavy metal, speed metal",
        "Genre: Teutonic metal / power metal\nLyrics:\nwe ride at dawn through the valley",
    )
    assert "heavy metal" in genres
    assert "speed metal" in genres
    assert "power metal" in genres or "teutonic metal" in genres
    assert "we ride at dawn" not in " ".join(genres)


def test_suno_uses_identity_genres():
    dna = {
        "tempo_bpm": 162,
        "percussive_share": 0.4,
        "swing_class": "straight",
        "onset_density": 2.0,
        "spectral_centroid_hz": 2200,
        "spectral_flatness": 0.05,
        "stereo_width": 0.4,
        "loudness_range_db": 8,
        "crest_factor_db": 10,
        "true_peak_db": -1,
        "integrated_rms_db": -12,
        "key": "A minor",
        "key_runner_up": "C major",
        "key_confidence": 0.8,
        "off_pulse_ratio": 0.1,
        "syncopation_ratio": 0.04,
        "harmonic_rhythm_bars": 4,
        "chord_progression": [],
        "band_energy": [
            {"name": "sub", "energy_pct": 10},
            {"name": "bass", "energy_pct": 20},
            {"name": "low_mid", "energy_pct": 15},
            {"name": "mid", "energy_pct": 15},
            {"name": "high_mid", "energy_pct": 15},
            {"name": "presence", "energy_pct": 15},
            {"name": "air", "energy_pct": 10},
        ],
        "sections": [],
        "artist": "Grave Digger",
        "genres": ["heavy metal", "speed metal", "teutonic metal"],
        "identity": {"artist": "Grave Digger", "genres": ["heavy metal", "speed metal"]},
    }
    suno = format_suno(dna, detailed=True)
    assert "heavy metal" in suno["style"]
    assert "speed metal" in suno["style"]
    assert "in the vein of Grave Digger" in suno["style"]
    assert "we ride" not in suno["style"].lower()
