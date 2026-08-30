from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import process_clips as shared


# ============================================================
# ROHAT KONFIGURATION
# ============================================================

shared.STREAMER_NAME = "Rohat"

shared.INPUT_DIR = ROOT / "rohat" / "selected_clips"
shared.OUTPUT_DIR = ROOT / "rohat" / "tiktok_ready"

shared.METADATA_FILE = ROOT / "rohat" / "clips_today.json"
shared.SELECTION_REPORT_FILE = ROOT / "rohat" / "selection_report.json"

shared.OUTPUT_PREFIX = "rohat_tiktok"

# Keine automatische Hook.
# Watermark bleibt nur klein im Video.
shared.WATERMARK = "@clipcrip4"


if __name__ == "__main__":
    shared.main()