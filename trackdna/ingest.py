from __future__ import annotations

import re
import shutil
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx

from trackdna.ai import load_settings
from trackdna.pot import POT_HOST, POT_PORT, ensure_pot_server, node_runtime

AUDIO_SUFFIXES = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac", ".aiff", ".aif"}
CACHE_DIR = Path.home() / "AppData" / "Roaming" / "TrackDNA" / "cache"
MAX_DOWNLOAD_BYTES = 250 * 1024 * 1024


def resolve_source(source: str, workdir: str | Path | None = None, progress=None) -> Path:
    text = source.strip().strip('"')
    if not text:
        raise RuntimeError("No file or URL provided.")

    if _looks_like_url(text):
        url = _canonicalize_url(text)
        video_id = _youtube_id(url)
        cached = _cached_path(video_id) if video_id else None
        if cached and cached.exists():
            if progress:
                progress("Using cached audio from the last download")
            return cached

        dest_dir = Path(workdir) if workdir else Path(tempfile.mkdtemp(prefix="trackdna_"))
        dest_dir.mkdir(parents=True, exist_ok=True)
        if progress:
            progress("Downloading audio…")
        path = _from_url(url, dest_dir, progress=progress)
        if video_id:
            return _store_cache(video_id, path)
        return path

    path = Path(text).expanduser()
    if not path.exists():
        raise RuntimeError(f"File not found: {path}")
    if path.suffix.lower() not in AUDIO_SUFFIXES:
        raise RuntimeError(f"Unsupported file type '{path.suffix}'. Use WAV, MP3, FLAC, OGG, or M4A.")
    return path.resolve()


def _looks_like_url(text: str) -> bool:
    return bool(re.match(r"^https?://", text, flags=re.I))


def _canonicalize_url(url: str) -> str:
    video_id = _youtube_id(url)
    if video_id:
        return f"https://www.youtube.com/watch?v={video_id}"
    return url


def _youtube_id(url: str) -> str | None:
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()
    if "youtu.be" in host:
        vid = parsed.path.strip("/").split("/")[0]
        return vid or None
    if "youtube.com" in host or "youtube-nocookie.com" in host:
        if parsed.path.startswith("/watch"):
            return (parse_qs(parsed.query).get("v") or [None])[0]
        parts = [p for p in parsed.path.split("/") if p]
        if len(parts) >= 2 and parts[0] in {"shorts", "embed", "live"}:
            return parts[1]
    return None


def _cached_path(video_id: str) -> Path:
    return CACHE_DIR / f"{video_id}.wav"


def _store_cache(video_id: str, path: Path) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    dest = _cached_path(video_id)
    if path.resolve() != dest.resolve():
        shutil.copy2(path, dest)
    return dest


def _from_url(url: str, dest_dir: Path, progress=None) -> Path:
    parsed = urlparse(url)
    suffix = Path(parsed.path).suffix.lower()
    if suffix in AUDIO_SUFFIXES:
        return _download_direct(url, dest_dir, suffix)

    try:
        return _download_ytdlp(url, dest_dir, progress=progress)
    except Exception as exc:
        text = str(exc)
        if "403" in text or "Forbidden" in text:
            raise RuntimeError(
                "YouTube blocked the download (HTTP 403). "
                "Use Browse and pick a local WAV/MP3, or add a cookies.txt in Settings "
                "and try again."
            ) from exc
        raise RuntimeError(
            "Could not pull audio from that URL. Use a local WAV/MP3, "
            f"or check FFmpeg is installed.\n{exc}"
        ) from exc


def _download_direct(url: str, dest_dir: Path, suffix: str) -> Path:
    name = Path(urlparse(url).path).name or f"download{suffix}"
    dest = dest_dir / name
    written = 0
    with httpx.Client(timeout=60.0, follow_redirects=True) as client:
        with client.stream("GET", url) as res:
            res.raise_for_status()
            with dest.open("wb") as fh:
                for chunk in res.iter_bytes(64 * 1024):
                    written += len(chunk)
                    if written > MAX_DOWNLOAD_BYTES:
                        dest.unlink(missing_ok=True)
                        raise RuntimeError("Download is larger than 250 MB.")
                    fh.write(chunk)
    return dest


def _download_ytdlp(url: str, dest_dir: Path, progress=None) -> Path:
    from yt_dlp import YoutubeDL

    ensure_pot_server(progress=progress)
    cookies = (load_settings().get("cookies_txt") or "").strip()
    outtmpl = str(dest_dir / "%(id)s.%(ext)s")
    attempts = [
        {"player_client": ["web_embedded", "android_vr"]},
        {"player_client": ["mweb", "web_embedded", "android_vr"]},
        {"player_client": ["default", "-android_sdkless"]},
    ]
    last_error: Exception | None = None
    for extra in attempts:
        opts = {
            "format": "bestaudio/best",
            "outtmpl": outtmpl,
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "retries": 2,
            "max_filesize": MAX_DOWNLOAD_BYTES,
            "js_runtimes": node_runtime(),
            "extractor_args": {
                "youtube": extra,
                "youtubepot-bgutilhttp": {"base_url": [f"http://{POT_HOST}:{POT_PORT}"]},
            },
            "postprocessors": [
                {"key": "FFmpegExtractAudio", "preferredcodec": "wav", "preferredquality": "0"}
            ],
        }
        if cookies and Path(cookies).exists():
            opts["cookiefile"] = cookies
        try:
            with YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                requested = ydl.prepare_filename(info)
            wav = Path(requested).with_suffix(".wav")
            if wav.exists():
                return wav
            matches = sorted(dest_dir.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
            audio = [p for p in matches if p.suffix.lower() in AUDIO_SUFFIXES]
            if audio:
                return audio[0]
        except Exception as exc:
            last_error = exc
            continue
    if last_error:
        raise last_error
    raise RuntimeError("Download finished but no audio file was found.")
