from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import quality_control as shared


# ============================================================
# ROHAT KONFIGURATION
# ============================================================

shared.STREAMER_NAME = "Rohat"

shared.INPUT_DIR = "rohat/downloaded_clips"
shared.FINAL_DIR = "rohat/selected_clips"

shared.INPUT_JSON = "rohat/clips_today.json"
shared.USED_FILE = "rohat/used_clips.json"
shared.HISTORY_FILE = "rohat/clip_history.json"
shared.REPORT_FILE = "rohat/selection_report.json"

shared.WHISPER_PROMPT = (
    "Deutscher Twitch-Stream von Rohat. "
    "Die Sprecher reden schnell, locker und umgangssprachlich. "
    "Namen und Wörter: Rohat, xRohat, Chat, Bro, Bruder, Digga, "
    "Wallah, crashout. "
    "Transkribiere wortgetreu und behalte Jugendsprache und Slang bei."
)


if __name__ == "__main__":
    shared.main()