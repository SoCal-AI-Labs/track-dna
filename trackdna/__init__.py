"""Track DNA — measured song analysis for Suno-ready prompts."""

__version__ = "0.1.0"

from trackdna.analyze import analyze_track
from trackdna.compare import compare_tracks
from trackdna.report import format_report
from trackdna.suno import format_suno

__all__ = [
    "analyze_track",
    "compare_tracks",
    "format_report",
    "format_suno",
    "__version__",
]
