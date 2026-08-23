from __future__ import annotations

import os
from multiprocessing import Process, Queue
from queue import Empty


def _limit_threads() -> None:
    for key in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        os.environ.setdefault(key, "1")


def _worker(path: str, meta: dict, q: Queue, segments, min_len, detailed: bool) -> None:
    _limit_threads()
    from trackdna.analyze import analyze_track
    from trackdna.suno import format_suno

    def progress(msg: str) -> None:
        q.put(("progress", msg))

    try:
        dna = analyze_track(
            path,
            segments=segments,
            min_len=min_len,
            source_meta=meta,
            progress=progress,
        )
        suno = format_suno(dna, detailed=detailed)
        q.put(("done", {"dna": dna, "suno": suno}))
    except Exception as exc:
        text = str(exc).strip() or type(exc).__name__
        q.put(("error", text))


def run_analysis(
    path,
    meta: dict | None = None,
    detailed: bool = True,
    progress=None,
    segments: int | None = None,
    min_len: float = 8.0,
) -> tuple[dict, dict]:
    q: Queue = Queue()
    proc = Process(
        target=_worker,
        args=(str(path), meta or {}, q, segments, min_len, detailed),
        daemon=True,
    )
    proc.start()
    result = None
    error = None
    while True:
        try:
            kind, payload = q.get(timeout=0.25)
        except Empty:
            if not proc.is_alive():
                error = "Analysis stopped unexpectedly."
                break
            continue
        if kind == "progress":
            if progress:
                progress(payload)
        elif kind == "done":
            result = payload
            break
        elif kind == "error":
            error = payload
            break
    proc.join(timeout=3)
    if proc.is_alive():
        proc.terminate()
    if error:
        raise RuntimeError(error)
    if not result:
        raise RuntimeError("Analysis returned nothing.")
    return result["dna"], result["suno"]
