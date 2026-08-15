from __future__ import annotations

import json
from pathlib import Path

import httpx

from trackdna.suno import LYRICS_LIMIT, STYLE_LIMIT

APP_DIR = Path.home() / "AppData" / "Roaming" / "TrackDNA"
SETTINGS_PATH = APP_DIR / "settings.json"

SYSTEM = """You turn measured Track DNA JSON into a Suno v5 / v5.5 instrumental recreation prompt.
Goal: recreate the reference SOUND only — groove, mix, harmony, form. Never lyrics.
Rules:
- Output JSON only: {"style": "...", "lyrics": "..."}
  The "lyrics" key is Suno's second box. It must contain structure tags only.
- Never transcribe, quote, paraphrase, or invent sung/rapped words.
- Style field: dense comma-separated clauses, use most of the 1000-character budget.
  Must include measured BPM, key, groove, drum density, low-end balance, mid/top character,
  stereo image, dynamics, form, and "instrumental no vocals".
- Second box: one [section] tag per measured section, then [Instrumental] and bracket-only
  arrangement notes (timestamps, energy, drums, chords). No unbracketed text.
- Style max 1000 characters. Second box max 3000 characters.
"""


def load_settings() -> dict:
    if not SETTINGS_PATH.exists():
        return {}
    try:
        return json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_settings(data: dict) -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    current = load_settings()
    current.update(data)
    SETTINGS_PATH.write_text(json.dumps(current, indent=2), encoding="utf-8")


def polish_suno(dna: dict, instrumental: bool = True, settings: dict | None = None) -> dict:
    cfg = settings or load_settings()
    api_key = (cfg.get("api_key") or "").strip()
    if not api_key:
        raise RuntimeError("Add an API key in Settings to use AI polish.")

    base = (cfg.get("base_url") or "https://api.openai.com/v1").rstrip("/")
    model = cfg.get("model") or "gpt-4.1-mini"
    payload = {
        "model": model,
        "temperature": 0.4,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM},
            {
                "role": "user",
                "content": json.dumps(
                    {"instrumental": True, "no_lyrics": True, "track_dna": _compact(dna)},
                    ensure_ascii=False,
                ),
            },
        ],
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    with httpx.Client(timeout=60.0) as client:
        res = client.post(f"{base}/chat/completions", headers=headers, json=payload)
        res.raise_for_status()
        content = res.json()["choices"][0]["message"]["content"]
    data = json.loads(content)
    style = str(data.get("style", "")).strip()[:STYLE_LIMIT]
    lyrics = str(data.get("lyrics", "")).strip()[:LYRICS_LIMIT]
    if not style or not lyrics:
        raise RuntimeError("AI returned an empty prompt.")
    paste = (
        "=== PASTE INTO SUNO → STYLE OF MUSIC ===\n"
        f"{style}\n\n"
        "=== PASTE INTO SUNO → SECOND BOX (structure only, no lyrics) ===\n"
        f"{lyrics}\n"
    )
    return {"style": style, "lyrics": lyrics, "paste": paste, "source": "llm"}


def _compact(dna: dict) -> dict:
    skip = {"chord_progression"}
    out = {k: v for k, v in dna.items() if k not in skip}
    # keep a short progression instead of every chord stamp
    chords = [c["chord"] for c in dna.get("chord_progression", [])][:24]
    out["chord_progression_short"] = chords
    return out
