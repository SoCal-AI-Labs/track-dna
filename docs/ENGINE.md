# Track DNA engine contract

Detailed DSP analysis of a music track: structure, harmony, rhythm, dynamics,
spectrum, and mix diagnostics. Everything reported is measured — the descriptive
language is a deterministic mapping off the numbers, not a guess.

This is the analysis contract carried over from the Claude planning notes.

## CLI

```bash
python track_dna.py analyze song.mp3
python track_dna.py analyze song.mp3 --json out.json
python track_dna.py analyze song.mp3 --suno
python track_dna.py compare mix_v1.wav mix_v2.wav
python track_dna.py app
```

The JSON is the format to paste into an LLM when you want it to reason over the
track rather than just print numbers.

## What it reports

**Overview** — duration, tempo (octave-corrected, with the raw detector value
shown when corrected), key + runner-up key with confidence, beat count.

**Rhythm & feel** — swing classification and swing ratio, onset density,
off-pulse ratio, syncopation, percussive share of total energy.

Off-pulse and syncopation are deliberately separate measurements. Straight
eighth-note hi-hats sit off the quarter-note pulse but are not syncopated; only
onsets that miss the 16th-note grid entirely count as syncopation.

**Harmony** — chord progression over time, chord change count, harmonic rhythm
in seconds and bars, plus the progression per section.

**Loudness & dynamics** — integrated RMS, true peak, crest factor, loudness range.

**Spectrum** — centroid, rolloff, bandwidth, flatness, stereo width, and a
7-band energy plot with frequency ranges labeled.

**Mix diagnostics** — muddiness, harshness, sibilance risk, sub weight, air,
dynamics, and noise floor, each with a severity and the reason.

**Structure** — per section: timestamp, label, length, level, percussive
percentage, spectral tilt, energy bar, and chord sequence.

## How structure detection works

**Boundaries** — Foote novelty. A self-similarity matrix is built over a fixed
0.5s grid of chroma (harmony) + MFCC (timbre) + RMS (energy), then a
checkerboard kernel slides down its diagonal, spiking where the music stops
resembling what came before.

A fixed time grid is used rather than a beat-synchronous one deliberately: beat
trackers routinely lock to half-tempo, which would halve the resolution of the
whole analysis. Boundaries snap back onto the beat grid afterward.

**Repeats** — segments are hierarchically clustered so verse 1 and verse 2 share
a label. Energy is weighted heavily here, because two sections often share
chords and differ only in loudness and density — exactly the verse/chorus
contrast. Position overrides cluster identity for quiet bookends, so a soft
intro and soft outro don't get labeled as a repeated verse.

## Accuracy and limits

Reliable: tempo, key, dynamics, spectrum, band balance, boundaries.

Trust with care:

- **Section labels** are heuristic over energy, repetition, and position — not a
  trained model. The boundaries are more trustworthy than the names.
- **Chords** are triad template matching. Clean on triadic material; extended or
  altered harmony (9ths, sus, jazz voicings) snaps to a nearby triad.
- **Key** relative major/minor ambiguity is real, which is why the runner-up is
  printed whenever confidence is below 0.5.

Not included in the DSP core: lyric transcription (needs Whisper), stem
separation (needs Demucs), genre/instrument tagging (needs a trained model such
as CLAP). Genre language in the Suno prompt is either a deterministic hint from
the measurements or an optional LLM rewrite.

## Tuning

- `--segments N` — target section count
- `min_len` in `segment_track()` — raise for long-form tracks, lower for short
  edits with fast section turnover
- `--suno` — emit the copy-paste Style + Lyrics blocks
