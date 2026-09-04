"""
ClipCrip3 US Renderer

Nutzt denselben Renderer wie
Rohat / Giggand / Jussef.

Ausgabe:
GENAU 5 fertige Videos.
"""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = (
    Path(__file__)
    .resolve()
    .parents[2]
)


if str(
    ROOT
) not in sys.path:

    sys.path.insert(
        0,
        str(
            ROOT
        ),
    )


from scripts import process_clips as shared


# ============================================================
# CLIPCRIP3 US
# ============================================================

shared.STREAMER_NAME = (
    "Kai + IShowSpeed + N3on"
)


shared.INPUT_DIR = (
    ROOT
    / "us"
    / "selected_clips"
)


shared.OUTPUT_DIR = (
    ROOT
    / "us"
    / "tiktok_ready"
)


shared.METADATA_FILE = (
    ROOT
    / "us"
    / "clips_today.json"
)


shared.SELECTION_REPORT_FILE = (
    ROOT
    / "us"
    / "selection_report.json"
)


# ============================================================
# GENAU 5
# ============================================================

shared.MIN_VIDEOS = 5

shared.MAX_VIDEOS = 5


# ============================================================
# OUTPUT
# ============================================================

shared.OUTPUT_PREFIX = (
    "clipcrip3_us"
)


# Hook bleibt AUS.
# Du entscheidest aus den 5 Gewinnern,
# welcher auf TikTok kommt.
shared.WATERMARK = (
    "@clipcrip3"
)


if __name__ == "__main__":

    shared.main()
