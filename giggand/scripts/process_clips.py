from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import process_clips as shared


# ============================================================
# GIGGAND KONFIGURATION
# ============================================================

shared.STREAMER_NAME = "Giggand"

shared.INPUT_DIR = ROOT / "giggand" / "selected_clips"
shared.OUTPUT_DIR = ROOT / "giggand" / "tiktok_ready"

shared.METADATA_FILE = ROOT / "giggand" / "clips_today.json"
shared.SELECTION_REPORT_FILE = ROOT / "giggand" / "selection_report.json"

shared.OUTPUT_PREFIX = "giggand_tiktok"

shared.WATERMARK = "@clipcrip5"


if __name__ == "__main__":
    shared.main()