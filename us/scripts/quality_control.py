"""
ClipCrip3 US Quality Control

Nutzt die gemeinsame ClipCrip
Quality Engine, aber:

- Englisch
- Kai / Speed / N3on
- 30 Kandidaten analysierbar
- GENAU 5 Gewinner
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


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


from scripts import quality_control as shared


# ============================================================
# CLIPCRIP3 US
# ============================================================

shared.STREAMER_NAME = (
    "Kai + IShowSpeed + N3on"
)


shared.INPUT_DIR = (
    "us/downloaded_clips"
)


shared.FINAL_DIR = (
    "us/selected_clips"
)


shared.INPUT_JSON = (
    "us/clips_today.json"
)


shared.USED_FILE = (
    "us/used_clips.json"
)


shared.HISTORY_FILE = (
    "us/clip_history.json"
)


shared.REPORT_FILE = (
    "us/selection_report.json"
)


# ============================================================
# GENAU 5
# ============================================================

shared.TARGET_COUNT = 5

shared.MIN_COUNT = 5

shared.MAX_FINAL_COUNT = 5


# ============================================================
# BREITER QUALITÄTSPOOL
# ============================================================

shared.SEMANTIC_POOL_SIZE = 30


# ============================================================
# SCORE-GRENZEN
# ============================================================

shared.PREMIUM_SCORE = 64.0

shared.GOOD_SCORE = 50.0

shared.FALLBACK_SCORE = 36.0


shared.MIN_DURATION = 8.0

shared.MAX_REASONABLE_DURATION = 60.5


# ============================================================
# WHISPER
# ============================================================

shared.WHISPER_PROMPT = (

    "English livestream clips featuring "
    "Kai Cenat, IShowSpeed or N3on. "

    "Speakers talk quickly, interrupt "
    "each other and use internet slang. "

    "Transcribe exactly. "

    "Keep names, reactions and slang "
    "such as Kai, Speed, N3on, bro, "
    "chat, W, L, nah, crashout, crazy, "
    "no way and oh my god."
)


# ============================================================
# VIRAL / REACTION SIGNALS
# ============================================================

shared.REACTION_TERMS = {

    "crashout": 4.0,

    "crash out": 4.0,

    "rage": 3.5,

    "raging": 3.5,

    "scream": 3.0,

    "screaming": 3.0,

    "wtf": 3.5,

    "what the fuck": 3.5,

    "oh my god": 3.0,

    "omg": 2.5,

    "no way": 3.0,

    "nah": 1.0,

    "crazy": 2.0,

    "insane": 2.5,

    "laugh": 2.0,

    "laughing": 2.0,

    "hahaha": 3.0,

    "funny": 1.5,

    "fail": 2.5,

    "roast": 2.5,

    "troll": 2.0,

    "caught": 2.0,

    "exposed": 2.0,

    "bro": 0.5,

    "chat": 0.5,
}


# ============================================================
# WERBUNG / PROMO PENALTY
# ============================================================

shared.PROMO_TERMS = {

    "follow me": 4.0,

    "follow him": 4.0,

    "subscribe": 4.0,

    "sub to": 4.0,

    "link in bio": 4.0,

    "new upload": 3.0,

    "new video": 2.5,

    "sponsor": 2.5,

    "giveaway": 3.0,
}


# ============================================================
# ENGLISH TRANSCRIPTION
# ============================================================

def transcribe_english(
    model: Any,
    path: Path,
) -> dict[
    str,
    Any,
]:

    raw = model.transcribe(

        str(
            path
        ),

        language="en",

        task="transcribe",

        word_timestamps=True,

        initial_prompt=(
            shared.WHISPER_PROMPT
        ),

        temperature=0.0,

        condition_on_previous_text=False,

        fp16=False,

        verbose=False,
    )


    return (
        shared.compact_transcript(
            raw
        )
    )


# Nur die sprachabhängige
# Transkriptionsfunktion ersetzen.
shared.transcribe = (
    transcribe_english
)


if __name__ == "__main__":

    shared.main()
