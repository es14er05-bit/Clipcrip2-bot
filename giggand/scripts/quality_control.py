from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import quality_control as shared


# ============================================================
# GIGGAND KONFIGURATION
# ============================================================

shared.STREAMER_NAME = "Giggand"

shared.INPUT_DIR = "giggand/downloaded_clips"
shared.FINAL_DIR = "giggand/selected_clips"

shared.INPUT_JSON = "giggand/clips_today.json"
shared.USED_FILE = "giggand/used_clips.json"
shared.HISTORY_FILE = "giggand/clip_history.json"
shared.REPORT_FILE = "giggand/selection_report.json"

shared.WHISPER_PROMPT = (
    "Deutscher Twitch-Stream von Giggand. "
    "Die Sprecher reden schnell, locker und umgangssprachlich. "
    "Namen und Wörter: Giggand, Chat, Bro, Bruder, Digga, Wallah, "
    "crashout. "
    "Transkribiere wortgetreu und behalte Jugendsprache und Slang bei."
)


if __name__ == "__main__":
    shared.main()