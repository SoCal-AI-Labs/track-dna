from __future__ import annotations

import ipaddress
import json
import re
import socket
from html import unescape
from pathlib import Path
from urllib.parse import urlparse

import httpx

MUSICBRAINZ = "https://musicbrainz.org/ws/2"
USER_AGENT = "TrackDNA/0.1.0 (https://github.com/SoCal-AI-Labs/track-dna)"
RELATED_HOSTS = {
    "bandcamp.com",
    "soundcloud.com",
    "open.spotify.com",
    "spotify.com",
    "music.apple.com",
    "itunes.apple.com",
    "tidal.com",
    "listen.tidal.com",
    "deezer.com",
    "www.deezer.com",
    "en.wikipedia.org",
    "wikipedia.org",
}
JUNK_ARTISTS = {
    "official video",
    "official audio",
    "lyric video",
    "lyrics",
    "audio",
    "topic",
    "vevo",
    "various artists",
    "unknown",
}
TITLE_JUNK = (
    "official video",
    "official audio",
    "official music video",
    "lyric video",
    "lyrics video",
    "visualizer",
    "audio only",
    "hd",
    "4k",
    "hq",
    "remastered",
    "explicit",
)

# Longest phrases first so "drum and bass" wins over "bass"
GENRE_PHRASES = [
    "alternative metal", "alternative rock", "art rock", "atmospheric black metal",
    "black metal", "blackgaze", "bluegrass", "blues rock", "boom bap",
    "death metal", "deathcore", "djent", "doom metal", "dream pop",
    "drum and bass", "dungeon synth", "east coast hip hop", "electro-industrial",
    "folk metal", "folk rock", "funk metal", "goth rock", "gothic metal",
    "groove metal", "hard rock", "heavy metal", "hip hop", "horrorcore",
    "indie folk", "indie pop", "indie rock", "industrial metal", "industrial rock",
    "melodic death metal", "melodic metal", "new wave", "nu metal", "nu-metal",
    "pop punk", "post-hardcore", "post-metal", "post-punk", "post-rock",
    "power metal", "prog metal", "progressive metal", "progressive rock",
    "psych rock", "psychedelic rock", "rap metal", "riot grrrl",
    "shoegaze", "sludge metal", "southern gothic", "southern metal",
    "southern rock", "speed metal", "stoner metal", "stoner rock",
    "symphonic metal", "synth pop", "synthwave", "tech death",
    "technical death metal", "teutonic metal", "thrash metal", "trap metal",
    "trip hop", "west coast hip hop",
    "afrobeat", "ambient", "blackened", "bluegrass", "blues", "breakbeat",
    "country", "crust", "cumbia", "dancehall", "darkwave", "disco",
    "dubstep", "edm", "emo", "emo rap", "folk", "funk", "garage",
    "grime", "grunge", "hardcore", "house", "hyperpop", "idm",
    "industrial", "jazz", "jungle", "k-pop", "lo-fi", "lofi",
    "metalcore", "metal", "newgrass", "opera", "phonk", "pop",
    "punk", "r&b", "rnb", "reggae", "reggaeton", "rockabilly",
    "rock", "salsa", "ska", "soul", "swing", "synth", "techno",
    "trance", "trap", "uk garage",
]


def build_identity(path: str | Path, raw: dict | None = None, progress=None) -> dict:
    try:
        return _build_identity(path, raw, progress=progress)
    except Exception:
        name = Path(path).name
        return {
            "artist": "",
            "title": name,
            "album": "",
            "year": "",
            "channel": "",
            "source_url": (raw or {}).get("source_url") or "",
            "source_kind": (raw or {}).get("source_kind") or "file",
            "genres": [],
            "tags": [],
            "related_links": [],
            "musicbrainz": {},
            "display_name": name,
            "evidence": "",
        }


def _build_identity(path: str | Path, raw: dict | None = None, progress=None) -> dict:
    raw = dict(raw or {})
    file_meta = _file_tags(path)
    merged = _merge_raw(raw, file_meta)
    title_guess = _parse_title(merged.get("title") or Path(path).stem)
    artist = _clean_name(
        merged.get("artist")
        or title_guess.get("artist")
        or _channel_artist(merged.get("channel") or merged.get("uploader") or "")
    )
    title = _clean_title(merged.get("track") or title_guess.get("title") or merged.get("title") or Path(path).name)
    texts = _text_blobs(merged)
    genres = _extract_genres(texts)[:8]
    links = _related_links(merged.get("description") or "")
    mb = {}
    display = " – ".join(p for p in (artist, title) if p) or Path(path).name
    return {
        "artist": artist,
        "title": title,
        "album": _clean_name(merged.get("album") or ""),
        "year": merged.get("year") or "",
        "channel": merged.get("channel") or merged.get("uploader") or "",
        "source_url": merged.get("source_url") or "",
        "source_kind": merged.get("source_kind") or ("url" if merged.get("source_url") else "file"),
        "genres": genres,
        "tags": _dedupe_keep((merged.get("tags") or [])[:16]),
        "related_links": links,
        "musicbrainz": mb,
        "display_name": display,
        "evidence": _evidence(merged, genres, artist),
    }


def parse_title(title: str) -> dict:
    return _parse_title(title)


def extract_genres(*texts: str) -> list[str]:
    return _extract_genres(list(texts))


def _merge_raw(raw: dict, file_meta: dict) -> dict:
    out = dict(file_meta)
    for key, value in raw.items():
        if value in (None, "", [], {}):
            continue
        out[key] = value
    artists = out.get("artists")
    if not out.get("artist") and isinstance(artists, list) and artists:
        first = artists[0]
        out["artist"] = first.get("name") if isinstance(first, dict) else str(first)
    genre = out.get("genre")
    if isinstance(genre, str) and genre.strip():
        out.setdefault("tags", [])
        if isinstance(out["tags"], list):
            out["tags"] = [genre] + list(out["tags"])
    if isinstance(out.get("genres"), list):
        out.setdefault("tags", [])
        out["tags"] = list(out["genres"]) + list(out.get("tags") or [])
    year = out.get("release_year") or out.get("date") or out.get("upload_date") or ""
    if year and not out.get("year"):
        out["year"] = str(year)[:4]
    return out


def _file_tags(path: str | Path) -> dict:
    try:
        import mutagen

        audio = mutagen.File(path, easy=True)
    except Exception:
        return {}
    if not audio:
        return {}
    tags = {k.lower(): v for k, v in dict(audio).items()}

    def first(*keys: str) -> str:
        for key in keys:
            val = tags.get(key)
            if isinstance(val, list) and val:
                return str(val[0]).strip()
            if isinstance(val, str) and val.strip():
                return val.strip()
        return ""

    genre = first("genre")
    return {
        "title": first("title"),
        "artist": first("artist", "albumartist"),
        "album": first("album"),
        "genre": genre,
        "year": first("date", "year"),
        "tags": [genre] if genre else [],
    }


def _parse_title(title: str) -> dict:
    text = _clean_title(title)
    if not text:
        return {}
    for sep in (" — ", " – ", " - ", " | ", " ~ ", ": "):
        if sep in text:
            left, right = [p.strip() for p in text.split(sep, 1)]
            if left and right and not _looks_junk(left):
                return {"artist": _clean_name(left), "title": _clean_title(right)}
    by_match = re.search(r"^(?P<title>.+?)\s+by\s+(?P<artist>.+)$", text, flags=re.I)
    if by_match:
        return {
            "artist": _clean_name(by_match.group("artist")),
            "title": _clean_title(by_match.group("title")),
        }
    return {"title": text}


def _channel_artist(channel: str) -> str:
    text = re.sub(r"\s*[-–—]?\s*(official|vevo|topic)\s*$", "", channel, flags=re.I)
    text = re.sub(r"vevo$", "", text, flags=re.I).strip()
    if _looks_junk(text):
        return ""
    return _clean_name(text)


def _clean_title(text: str) -> str:
    value = unescape(str(text or "")).strip()
    value = re.sub(r"\[[^\]]{0,40}\]", " ", value)
    value = re.sub(r"\((?:official|lyric|audio|video|visualizer|hd|4k|hq|remaster).+?\)", " ", value, flags=re.I)
    for junk in TITLE_JUNK:
        value = re.sub(rf"\b{re.escape(junk)}\b", " ", value, flags=re.I)
    return re.sub(r"\s+", " ", value).strip(" -–—|~")


def _clean_name(text: str) -> str:
    value = _clean_title(text)
    if _looks_junk(value) or len(value) < 2:
        return ""
    return value


def _looks_junk(text: str) -> bool:
    return text.strip().lower() in JUNK_ARTISTS


def _text_blobs(merged: dict) -> list[str]:
    blobs = [
        merged.get("title") or "",
        merged.get("album") or "",
        merged.get("description") or "",
        " ".join(merged.get("tags") or []),
        " ".join(merged.get("categories") or []),
        merged.get("genre") or "",
    ]
    return [b for b in blobs if b]


def _extract_genres(texts: list[str]) -> list[str]:
    hay = _strip_lyric_blocks(" \n ".join(t for t in texts if t)).lower()
    labeled = re.findall(
        r"(?:genres?|styles?|sounds?)\s*[:\-]\s*([^\n|]{2,80})",
        hay,
        flags=re.I,
    )
    found: list[str] = []
    for chunk in labeled:
        for piece in re.split(r"[,/&]| and ", chunk):
            piece = piece.strip(" .")
            if 2 <= len(piece) <= 32:
                found.append(piece)
    for phrase in GENRE_PHRASES:
        if re.search(rf"\b{re.escape(phrase)}\b", hay):
            found.append(phrase)
    return _dedupe_keep(_normalize_genre(g) for g in found)


def _normalize_genre(text: str) -> str:
    value = re.sub(r"\s+", " ", text.strip().lower())
    aliases = {
        "hip hop": "hip-hop",
        "hiphop": "hip-hop",
        "rnb": "r&b",
        "r and b": "r&b",
        "lofi": "lo-fi",
        "nu-metal": "nu metal",
        "dnb": "drum and bass",
        "d&b": "drum and bass",
    }
    return aliases.get(value, value)


def _strip_lyric_blocks(text: str) -> str:
    lines = []
    skipping = False
    for line in text.splitlines():
        if re.match(r"^\s*(lyrics|lyric video)\b", line, flags=re.I):
            skipping = True
            continue
        if skipping and line.strip() == "":
            skipping = False
            continue
        if not skipping:
            lines.append(line)
    return "\n".join(lines)


def _related_links(description: str) -> list[str]:
    urls = re.findall(r"https?://[^\s)<>\"']+", description or "")
    out = []
    for url in urls:
        url = url.rstrip(".,);")
        host = (urlparse(url).hostname or "").lower()
        if host.startswith("www."):
            host = host[4:]
        if any(host == allowed or host.endswith("." + allowed) for allowed in RELATED_HOSTS):
            if url not in out:
                out.append(url)
        if len(out) >= 3:
            break
    return out


def _fetch_related_text(urls: list[str]) -> str:
    blobs = []
    for url in urls[:1]:
        html = _fetch_public_html(url)
        if html:
            blobs.append(_html_meta(html))
    return " ".join(b for b in blobs if b)


def _fetch_public_html(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return ""
    host = parsed.hostname or ""
    if not _host_is_public(host):
        return ""
    try:
        with httpx.Client(timeout=4.0, follow_redirects=True, headers={"User-Agent": USER_AGENT}) as client:
            res = client.get(url)
            res.raise_for_status()
            return res.text[:400_000]
    except Exception:
        return ""


def _host_is_public(host: str) -> bool:
    from concurrent.futures import ThreadPoolExecutor

    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            infos = pool.submit(socket.getaddrinfo, host, None).result(timeout=2)
    except Exception:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return False
    return True


def _html_meta(html: str) -> str:
    bits = []
    patterns = [
        r"<title[^>]*>(.*?)</title>",
        r'property=["\']og:title["\'][^>]*content=["\'](.*?)["\']',
        r'content=["\'](.*?)["\'][^>]*property=["\']og:title["\']',
        r'property=["\']og:description["\'][^>]*content=["\'](.*?)["\']',
        r'content=["\'](.*?)["\'][^>]*property=["\']og:description["\']',
        r'name=["\']description["\'][^>]*content=["\'](.*?)["\']',
        r'content=["\'](.*?)["\'][^>]*name=["\']description["\']',
        r'name=["\']keywords["\'][^>]*content=["\'](.*?)["\']',
        r'content=["\'](.*?)["\'][^>]*name=["\']keywords["\']',
    ]
    for pat in patterns:
        match = re.search(pat, html, flags=re.I | re.S)
        if match:
            bits.append(unescape(re.sub(r"<[^>]+>", " ", match.group(1))))
    return " ".join(bits)


def _musicbrainz_lookup(artist: str, title: str) -> dict:
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    out = {"artist_id": "", "recording_id": "", "genres": []}
    query = f'artist:"{_mb_quote(artist)}"'
    if title:
        query = f'recording:"{_mb_quote(title)}" AND artist:"{_mb_quote(artist)}"'
    try:
        with httpx.Client(timeout=4.0, headers=headers) as client:
            res = client.get(
                f"{MUSICBRAINZ}/{'recording' if title else 'artist'}",
                params={"query": query, "fmt": "json", "limit": 1},
            )
            if res.status_code != 200:
                return out
            payload = res.json()
            rows = payload.get("recordings") or payload.get("artists") or []
            if not rows:
                return out
            row = rows[0]
            out["recording_id"] = row.get("id") or "" if title else ""
            out["artist_id"] = "" if title else (row.get("id") or "")
            out["genres"].extend(_mb_terms(row))
            for credit in row.get("artist-credit") or []:
                artist_row = credit.get("artist") or {}
                out["genres"].extend(_mb_terms(artist_row))
                if artist_row.get("id"):
                    out["artist_id"] = artist_row["id"]
    except Exception:
        return out
    out["genres"] = _dedupe_keep(_normalize_genre(g) for g in out["genres"])
    return out


def _mb_quote(text: str) -> str:
    return text.replace('"', "").replace("\\", "")[:120]


def _mb_terms(payload: dict) -> list[str]:
    terms = []
    for key in ("genres", "tags"):
        for row in payload.get(key) or []:
            name = (row.get("name") or "").strip()
            if name:
                terms.append(name)
    return terms


def _evidence(merged: dict, genres: list[str], artist: str) -> str:
    bits = []
    if artist:
        bits.append(f"artist {artist}")
    if genres:
        bits.append("genres " + ", ".join(genres[:4]))
    if merged.get("source_url"):
        bits.append("from URL metadata")
    elif merged.get("genre") or merged.get("tags"):
        bits.append("from file tags")
    return "; ".join(bits)


def _dedupe_keep(items) -> list[str]:
    seen = set()
    out = []
    for item in items:
        key = str(item).strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(str(item).strip())
    return out


def dump_ytdlp_meta(info: dict, source_url: str = "") -> dict:
    tags = info.get("tags") or []
    if not isinstance(tags, list):
        tags = [str(tags)]
    return {
        "id": info.get("id") or "",
        "title": info.get("title") or "",
        "track": info.get("track") or "",
        "artist": info.get("artist") or info.get("creator") or "",
        "artists": info.get("artists") or [],
        "album": info.get("album") or "",
        "album_artist": info.get("album_artist") or "",
        "genre": info.get("genre") or "",
        "genres": info.get("genres") or [],
        "tags": [str(t) for t in tags][:24],
        "categories": info.get("categories") or [],
        "description": (info.get("description") or "")[:4000],
        "uploader": info.get("uploader") or "",
        "channel": info.get("channel") or "",
        "release_year": info.get("release_year") or "",
        "upload_date": info.get("upload_date") or "",
        "webpage_url": info.get("webpage_url") or source_url,
        "source_url": source_url or info.get("webpage_url") or "",
        "source_kind": "url",
    }


def save_sidecar(path: Path, meta: dict) -> None:
    side = path.with_suffix(".meta.json")
    side.write_text(json.dumps(meta, indent=2), encoding="utf-8")


def load_sidecar(path: Path) -> dict:
    side = path.with_suffix(".meta.json")
    if not side.exists():
        return {}
    try:
        return json.loads(side.read_text(encoding="utf-8"))
    except Exception:
        return {}
