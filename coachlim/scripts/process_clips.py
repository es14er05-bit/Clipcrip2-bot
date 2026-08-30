from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(ROOT),
    )

from scripts import process_clips as shared


# ============================================================
# COACHLIM KONFIGURATION
# ============================================================

shared.STREAMER_NAME = "Coachlim"

shared.INPUT_DIR = (
    ROOT
    / "coachlim"
    / "selected_clips"
)

shared.OUTPUT_DIR = (
    ROOT
    / "coachlim"
    / "tiktok_ready"
)

shared.METADATA_FILE = (
    ROOT
    / "coachlim"
    / "clips_today.json"
)

shared.SELECTION_REPORT_FILE = (
    ROOT
    / "coachlim"
    / "selection_report.json"
)

shared.OUTPUT_PREFIX = "coachlim_tiktok"

# Gleicher Stil wie die bestehenden Bots:
# Untertitel + kleines Watermark.
shared.WATERMARK = "@clipcrip6"


if __name__ == "__main__":
    shared.main()