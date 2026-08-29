from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(ROOT),
    )

from scripts import quality_control as shared


# ============================================================
# COACHLIM KONFIGURATION
# ============================================================

shared.STREAMER_NAME = "Coachlim"

shared.INPUT_DIR = "coachlim/downloaded_clips"
shared.FINAL_DIR = "coachlim/selected_clips"

shared.INPUT_JSON = "coachlim/clips_today.json"
shared.USED_FILE = "coachlim/used_clips.json"
shared.HISTORY_FILE = "coachlim/clip_history.json"
shared.REPORT_FILE = "coachlim/selection_report.json"

shared.WHISPER_PROMPT = (
    "Deutscher Twitch-Stream von Coachlim. "
    "Die Sprecher reden schnell, locker und umgangssprachlich. "
    "Namen und Wörter: Coachlim, Coach Lim, Lim, Chat, "
    "Bro, Bruder, Digga, Wallah, Junge, Alter, "
    "crashout. "
    "Transkribiere wortgetreu und behalte "
    "Jugendsprache und Slang bei."
)


if __name__ == "__main__":
    shared.main()