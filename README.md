# Track DNA

**Suno prompt generator and MiniMax instrumental prompt builder** from real song analysis.

Track DNA is a Windows desktop app that listens to a track — local WAV / MP3 / FLAC or a YouTube URL — and turns **measured** tempo, key, groove, mix, and structure into **copy-paste prompts** for [Suno](https://suno.com) and MiniMax.

No lyrics. No transcription. The second paste box is structure tags only (`[Intro]`, `[Instrumental]`, timestamps, mix notes).

## Why it exists

Most AI-music prompts are vibe guesses. Track DNA starts from DSP: BPM, key, swing, bass weight, loudness, and a section map. Those numbers become a dense **Sound DNA** style line (~1000 characters) plus an optional structure map (~3000 characters) for Suno’s two fields.

## Features

- **BPM, key, and groove** — tempo with octave correction, key + runner-up, swing vs straight
- **Mix readout** — 7-band energy, bass weight, loudness, true peak, crest
- **Section map** — measured boundaries, tagged as instrumental form
- **Suno / MiniMax paste** — style prompt + structure tags, each with a copy button
- **Local or URL** — drop a file, or pull audio from YouTube when the download path works
- **Optional AI polish** — rewrite the prompt from the measured JSON if you add an API key
- **CLI** — same engine from the terminal

## Install (Windows)

1. Python 3.11+ (3.14 works if the scientific wheels install).
2. [FFmpeg](https://ffmpeg.org/download.html) on your PATH — required for MP3 / M4A and most URL downloads. WAV / FLAC work without it.
3. In this folder:

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Run

Desktop app:

```bat
python app.py
```

or double-click `run.bat`.

CLI:

```bat
python track_dna.py analyze song.mp3
python track_dna.py analyze song.mp3 --json out.json
python track_dna.py analyze song.mp3 --suno
python track_dna.py compare mix_v1.wav mix_v2.wav
```

## How to use the prompts

1. Analyze a reference track you have the right to use.
2. Open Suno or MiniMax → custom / advanced.
3. Paste the **style prompt** into the style / genre field.
4. Optionally open the structure map and paste tags into the second box. It is tags only — this app never writes words to sing.
5. Generate. Tweak genre language if the hint is off — genre is inferred from measurements, not a trained tagger.

## What is measured vs guessed

The engine contract is in [docs/ENGINE.md](docs/ENGINE.md).

**Trust:** tempo, key, dynamics, spectrum, band balance, section *boundaries*.

**Treat as hints:** section *names* (verse / chorus), triad chords on jazz or extended harmony, genre wording in the style line.

Lyric transcription is intentionally not included. Stem separation and CLAP genre tags are also not in v1.

## Privacy

- Analysis runs on your machine. Audio is not uploaded for the core extract.
- Optional AI polish sends **measured JSON** (not the audio file) to the API you configure.
- API keys and a cookies.txt path live in `%APPDATA%\TrackDNA\settings.json` — not in this repo.
- YouTube cookie files stay local and are only read by the downloader if you point Settings at them.

## Optional AI polish

Settings → paste an OpenAI-compatible API key. **Polish** asks the model for a tighter style line plus structure tags. Analysis itself never needs a key.
