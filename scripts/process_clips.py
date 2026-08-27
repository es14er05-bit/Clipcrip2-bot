import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path


# =========================================================
# CLIPCRIP2 PROCESSOR V5.0
# JUSSEF - SHORT NATIVE TIKTOK HOOKS
# =========================================================


# =========================================================
# PATHS
# =========================================================

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent

INPUT_DIR = REPO_ROOT / "selected_clips"
OUTPUT_DIR = REPO_ROOT / "tiktok_ready"
METADATA_FILE = REPO_ROOT / "clips_today.json"

MAX_VIDEOS = 5

WHISPER_MODEL = "turbo"

OUTPUT_PREFIX = "jussef_tiktok"

WATERMARK = "@Clipcrip2"

TARGET_WIDTH = 1080
TARGET_HEIGHT = 1920


# =========================================================
# HOOK CONFIG
# =========================================================

HOOKS_ENABLED = True

# Bleibt während des gesamten Clips sichtbar.
HOOK_END_TIME = "23:59:59.00"

# Niedrig, weil bei schwächeren Signalen trotzdem lieber
# eine spezifische Kategorie genommen werden soll.
HOOK_MIN_SCORE = 0.55

STREAMER_NAME = "Jussef"


# =========================================================
# WHISPER / STREAMER CONTEXT
# =========================================================

BASE_PROMPT = (
    "Dies ist ein deutscher Twitch-Stream von Jussef. "
    "Die Sprecher reden sehr locker, schnell und umgangssprachlich. "
    "Häufige Wörter und Namen können sein: "
    "Jussef, Yussef, Yavuz, Twitch, Discord, Stream, Streamer, "
    "Chat, Clip, Gameplay, Game, Bro, Bruder, Digga, Digger, "
    "Junge, Alter, Wallah, Vallah, Mashallah, Inshallah, "
    "Habibi, safe, cringe, crazy, NPC, crashout, Chatten, zocken, "
    "TikTok, YouTube, Fortnite, Minecraft, GTA. "
    "Transkribiere das tatsächlich Gesagte möglichst wortgetreu. "
    "Behalte Jugendsprache und Umgangssprache bei. "
    "Formuliere nichts in Hochdeutsch um."
)


# =========================================================
# HOOK BANKS
#
# ABSICHTLICH:
# - sehr kurz
# - kein künstlicher Clickbait
# - keine Emojis wegen libass/font Problemen
# - Name häufig direkt drin
# =========================================================

HOOK_BANKS = {

    "laugh": [
        "Jussef kann nicht mehr",
        "Jussef fällt fast um",
        "Jussef ist komplett weg",
        "Bro kann nicht mehr",
        "Jussef bricht weg",
        "Jussef stirbt vor Lachen",
    ],

    "rage": [
        "Jussef geht crashout",
        "Jussef reicht's komplett",
        "Bro geht crashout",
        "Jussef verliert die Nerven",
        "Jussef ist komplett durch",
        "Bro hat genug",
    ],

    "surprise": [
        "Jussef checkt gar nichts",
        "Jussef ist komplett lost",
        "Bro ist sprachlos",
        "Jussef glaubt es nicht",
        "Bro checkt's nicht",
        "Jussef ist raus",
    ],

    "fail": [
        "Jussef verkackt komplett",
        "Bro hats verkackt",
        "Jussef komplett reingeschissen",
        "Das wars für Jussef",
        "Bro ist cooked",
        "Jussef ist cooked",
    ],

    "chat": [
        "Chat macht Jussef fertig",
        "Jussef gegen den Chat",
        "Chat trollt Jussef",
        "Chat lässt nicht locker",
        "Jussef wird getrollt",
        "Chat ist wieder wild",
    ],

    "roast": [
        "Jussef wird hops genommen",
        "Bro wurde zerlegt",
        "Jussef hat keine Antwort",
        "Der saß bei Jussef",
        "Bro ist cooked",
        "Jussef wurde erwischt",
    ],

    "sus": [
        "Jussef meint das ernst",
        "Bro ist sich sicher",
        "Jussef zieht einfach durch",
        "Bro glaubt das wirklich",
        "Jussef schwört drauf",
        "Bro meint das ernst",
    ],

    "gaming": [
        "Jussef ist cooked",
        "Bro wurde komplett gepackt",
        "Jussef hats verkackt",
        "Bro ist komplett lost",
        "Jussef gegen das Game",
        "Bro hat keine Chance",
    ],
}


# =========================================================
# FALLBACKS
#
# Auch diese bewusst kurz.
# Keine "warte bis zum Ende"-Roboterhooks.
# =========================================================

FALLBACK_HOOKS = [
    "Jussef ist komplett lost",
    "Bro ist cooked",
    "Jussef meint das ernst",
    "Bro checkt gar nichts",
    "Jussef zieht einfach durch",
    "Bro ist komplett durch",
    "Jussef ist raus",
    "Was macht Jussef da",
]


# =========================================================
# SIGNALS
# =========================================================

HOOK_SIGNALS = {

    "laugh": [
        ("hahahahaha", 3.0),
        ("hahahaha", 2.8),
        ("hahaha", 2.5),
        ("haha", 1.6),
        ("hehe", 1.0),
        ("ich kann nicht mehr", 2.5),
        ("kann nicht mehr", 2.0),
        ("lach", 1.5),
        ("lacht", 1.8),
        ("lachen", 1.6),
        ("lustig", 1.2),
        ("totlachen", 2.2),
    ],

    "rage": [
        ("ausgerastet", 3.0),
        ("rastet aus", 3.0),
        ("ausrasten", 2.5),
        ("crashout", 3.0),
        ("crash out", 3.0),
        ("rage", 2.2),
        ("halt die fresse", 2.5),
        ("halt dein maul", 2.5),
        ("kein nerv", 2.0),
        ("keinen nerv", 2.0),
        ("sauer", 1.5),
        ("schreit", 1.8),
        ("geschrien", 1.8),
        ("reicht mir", 2.0),
        ("scheiße", 0.8),
        ("fuck", 1.0),
    ],

    "surprise": [
        ("oh mein gott", 2.8),
        ("was zur hölle", 2.8),
        ("was ist das", 2.2),
        ("was war das", 2.2),
        ("niemals", 2.2),
        ("wtf", 2.2),
        ("oha", 1.5),
        ("ohha", 1.5),
        ("sprachlos", 2.0),
        ("nicht dein ernst", 2.3),
        ("ist das dein ernst", 2.3),
        ("was passiert", 1.8),
        ("hä", 0.8),
    ],

    "fail": [
        ("verkackt", 2.8),
        ("reingeschissen", 2.8),
        ("gefailt", 2.5),
        ("fail", 2.2),
        ("verloren", 1.5),
        ("gestorben", 1.5),
        ("tot", 0.8),
        ("gekillt", 1.5),
        ("daneben", 1.4),
        ("nicht geklappt", 2.3),
        ("funktioniert nicht", 2.0),
        ("crash", 1.8),
        ("cooked", 2.5),
    ],

    "chat": [
        ("der chat", 2.3),
        ("mein chat", 2.3),
        ("chat sagt", 2.3),
        ("chat schreibt", 2.3),
        ("chat", 1.3),
        ("donation", 1.8),
        ("spende", 1.8),
        ("viewer", 1.5),
        ("zuschauer", 1.5),
        ("trollt", 1.8),
        ("getrollt", 1.8),
    ],

    "roast": [
        ("hops genommen", 3.0),
        ("hops", 1.8),
        ("zerlegt", 2.2),
        ("roast", 2.2),
        ("beleidigt", 1.6),
        ("keine antwort", 2.0),
        ("auseinander genommen", 2.5),
        ("mundtot", 2.3),
        ("erwischt", 1.6),
    ],

    "sus": [
        ("ich schwöre", 2.0),
        ("wallah", 1.4),
        ("vallah", 1.4),
        ("glaub mir", 1.8),
        ("lügst", 2.3),
        ("gelogen", 2.3),
        ("lüge", 2.0),
        ("safe", 1.2),
        ("hundert prozent", 1.8),
        ("100 prozent", 1.8),
        ("ernst", 1.0),
    ],

    "gaming": [
        ("game", 0.8),
        ("zocken", 0.8),
        ("fortnite", 1.0),
        ("minecraft", 1.0),
        ("gta", 1.0),
        ("gekillt", 1.5),
        ("kill", 1.2),
        ("gegner", 1.0),
        ("runde", 0.8),
        ("rank", 1.0),
        ("ranked", 1.0),
    ],
}


# =========================================================
# COMMAND
# =========================================================

def run(command):

    command = [
        str(item)
        for item in command
    ]

    print("")
    print(
        "RUN:",
        " ".join(command)
    )

    result = subprocess.run(
        command
    )

    if result.returncode != 0:

        raise RuntimeError(
            "Befehl fehlgeschlagen: "
            + " ".join(command)
        )


# =========================================================
# JSON
# =========================================================

def load_json(path, default):

    path = Path(path)

    if not path.exists():

        return default

    try:

        with open(
            path,
            "r",
            encoding="utf-8"
        ) as file:

            return json.load(
                file
            )

    except Exception as error:

        print(
            f"JSON konnte nicht geladen werden: {path}"
        )

        print(
            error
        )

        return default


# =========================================================
# VIDEO SORTIERUNG
# =========================================================

def video_number(path):

    name = Path(
        path
    ).stem

    match = re.search(
        r"clip_(\d+)",
        name,
        re.IGNORECASE
    )

    if match:

        return int(
            match.group(1)
        )

    match = re.search(
        r"(\d+)",
        name
    )

    if match:

        return int(
            match.group(1)
        )

    return 999999


# =========================================================
# FIND VIDEOS
# =========================================================

def find_videos():

    print("")
    print(
        "========================================"
    )
    print(
        "SELECTED_CLIPS SUCHEN"
    )
    print(
        "========================================"
    )

    print(
        f"Repository Root: {REPO_ROOT}"
    )

    print(
        f"Erwarteter Ordner: {INPUT_DIR}"
    )

    print(
        f"Ordner existiert: {INPUT_DIR.exists()}"
    )

    if INPUT_DIR.exists():

        try:

            contents = list(
                INPUT_DIR.iterdir()
            )

            print(
                f"Inhalt selected_clips: "
                f"{len(contents)} Dateien/Ordner"
            )

            for item in contents:

                print(
                    "  -> "
                    + str(item)
                )

        except Exception as error:

            print(
                "Ordnerinhalt konnte nicht "
                "angezeigt werden:"
            )

            print(
                error
            )

    videos = []

    extensions = {
        ".mp4",
        ".webm",
        ".mkv",
        ".mov",
        ".m4v",
    }

    if INPUT_DIR.exists():

        for path in INPUT_DIR.iterdir():

            if (
                path.is_file()
                and path.suffix.lower()
                in extensions
            ):

                videos.append(
                    path
                )

    videos.sort(
        key=lambda path: (
            video_number(
                path
            ),
            path.name.lower()
        )
    )

    print("")
    print(
        f"{len(videos)} Videos in "
        "selected_clips gefunden."
    )

    for video in videos:

        print(
            "VIDEO GEFUNDEN: "
            + str(video)
        )

    return videos


# =========================================================
# CLEAN OUTPUT
# =========================================================

def clean_output():

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    for path in OUTPUT_DIR.iterdir():

        try:

            if path.is_file():

                path.unlink()

            elif path.is_dir():

                shutil.rmtree(
                    path
                )

        except Exception as error:

            print(
                f"Konnte Output-Datei nicht löschen: "
                f"{path}"
            )

            print(
                error
            )


# =========================================================
# TEXT
# =========================================================

def clean_text(text):

    text = str(
        text
    ).strip()

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    text = (
        text
        .replace(
            "{",
            "("
        )
        .replace(
            "}",
            ")"
        )
        .replace(
            "\\",
            ""
        )
    )

    return text


def escape_ass_text(text):

    text = clean_text(
        text
    )

    text = (
        text
        .replace(
            "\\",
            ""
        )
        .replace(
            "{",
            "("
        )
        .replace(
            "}",
            ")"
        )
        .replace(
            "\n",
            " "
        )
    )

    return text


# =========================================================
# REMOVE EMOJIS / UNSUPPORTED SYMBOLS
# =========================================================

def remove_unsupported_hook_chars(text):

    text = clean_text(
        text
    )

    # Nur Zeichen behalten, die DejaVu Sans zuverlässig
    # darstellen kann. Dadurch keine Emoji-Kästchen mehr.
    text = re.sub(
        r"[^A-Za-z0-9ÄÖÜäöüß?!.,'’\- ]",
        "",
        text
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    ).strip()

    return text


# =========================================================
# HOOK CONTEXT
# =========================================================

def normalize_hook_context(text):

    text = clean_text(
        text
    ).lower()

    text = re.sub(
        r"[^a-z0-9äöüß\s!?'-]",
        " ",
        text
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    ).strip()

    return text


def transcription_text(data):

    if not isinstance(
        data,
        dict
    ):

        return ""

    direct_text = clean_text(
        data.get(
            "text",
            ""
        )
    )

    if direct_text:

        return direct_text

    parts = []

    for segment in data.get(
        "segments",
        []
    ):

        if not isinstance(
            segment,
            dict
        ):

            continue

        text = clean_text(
            segment.get(
                "text",
                ""
            )
        )

        if text:

            parts.append(
                text
            )

    return " ".join(
        parts
    )


def signal_score(
    text,
    signals
):

    score = 0.0

    for phrase, weight in signals:

        if phrase in text:

            score += float(
                weight
            )

    return score


def stable_choice(
    values,
    seed
):

    if not values:

        return ""

    digest = hashlib.sha256(
        str(
            seed
        ).encode(
            "utf-8"
        )
    ).digest()

    index = int.from_bytes(
        digest[:4],
        "big"
    ) % len(
        values
    )

    return values[
        index
    ]


def format_hook(text):

    text = remove_unsupported_hook_chars(
        text
    )

    if not text:

        return ""

    for index, char in enumerate(
        text
    ):

        if char.isalpha():

            text = (
                text[:index]
                + char.upper()
                + text[index + 1:]
            )

            break

    return text


# =========================================================
# HOOK -> ASS
# =========================================================

def hook_to_ass(text):

    safe_text = escape_ass_text(
        text
    )

    words = safe_text.split()

    # Kurze Hooks bewusst eine Zeile.
    if len(words) <= 4:

        return safe_text

    # Bei 5-6 Wörtern auf zwei kompakte Zeilen.
    split_at = (
        len(words)
        + 1
    ) // 2

    first_line = " ".join(
        words[:split_at]
    )

    second_line = " ".join(
        words[split_at:]
    )

    return (
        first_line
        + "\\N"
        + second_line
    )


# =========================================================
# CREATE HOOK V5
# =========================================================

def create_hook(
    data,
    clip_title,
    seed
):

    if not HOOKS_ENABLED:

        return ""

    spoken = normalize_hook_context(
        transcription_text(
            data
        )
    )

    title = normalize_hook_context(
        clip_title
    )

    combined_context = (
        spoken
        + " "
        + title
    ).strip()

    scores = {}

    for category, signals in (
        HOOK_SIGNALS.items()
    ):

        spoken_score = signal_score(
            spoken,
            signals
        )

        title_score_value = signal_score(
            title,
            signals
        )

        # Titel zählt stark mit, weil Twitch-Titel
        # häufig den Clip-Kontext bereits verrät.
        scores[
            category
        ] = (
            spoken_score
            + title_score_value * 0.80
        )

    if scores:

        category = max(
            scores,
            key=scores.get
        )

        best_score = scores[
            category
        ]

    else:

        category = ""
        best_score = 0.0

    if (
        category
        and best_score >= HOOK_MIN_SCORE
    ):

        hook = stable_choice(
            HOOK_BANKS.get(
                category,
                []
            ),
            (
                str(seed)
                + "|"
                + category
                + "|"
                + combined_context[:300]
            )
        )

        print(
            "HOOK CATEGORY: "
            f"{category} "
            f"({best_score:.2f})"
        )

    else:

        hook = stable_choice(
            FALLBACK_HOOKS,
            (
                str(seed)
                + "|fallback|"
                + combined_context[:300]
            )
        )

        print(
            "HOOK FALLBACK: "
            f"{best_score:.2f}"
        )

    hook = format_hook(
        hook
    )

    words = hook.split()

    # V5 Hooks sollen kurz bleiben.
    if (
        not hook
        or len(words) < 2
        or len(words) > 6
    ):

        hook = format_hook(
            stable_choice(
                FALLBACK_HOOKS,
                (
                    str(seed)
                    + "|emergency"
                )
            )
        )

    print(
        "HOOK FINAL: "
        + hook
    )

    return hook


# =========================================================
# ASS TIME
# =========================================================

def ass_time(seconds):

    seconds = max(
        0.0,
        float(
            seconds
        )
    )

    hours = int(
        seconds // 3600
    )

    minutes = int(
        (
            seconds % 3600
        ) // 60
    )

    secs = int(
        seconds % 60
    )

    centiseconds = int(
        (
            seconds
            - int(
                seconds
            )
        )
        * 100
    )

    centiseconds = max(
        0,
        min(
            99,
            centiseconds
        )
    )

    return (
        f"{hours}:"
        f"{minutes:02d}:"
        f"{secs:02d}."
        f"{centiseconds:02d}"
    )


# =========================================================
# WHISPER
# =========================================================

def create_transcription(
    video,
    clip_title=""
):

    print("")
    print(
        "========================================"
    )
    print(
        "WHISPER TURBO"
    )
    print(
        "========================================"
    )

    print(
        f"Analysiere Sprache: {video}"
    )

    video = Path(
        video
    )

    base_name = video.stem

    json_file = (
        OUTPUT_DIR
        / (
            base_name
            + ".json"
        )
    )

    if json_file.exists():

        json_file.unlink()

    prompt = BASE_PROMPT

    if clip_title:

        prompt += (
            " Der Twitch-Clip trägt den Titel: "
            + clean_text(
                clip_title
            )
            + "."
        )

    command = [
        sys.executable,
        "-m",
        "whisper",

        str(
            video
        ),

        "--model",
        WHISPER_MODEL,

        "--language",
        "German",

        "--task",
        "transcribe",

        "--word_timestamps",
        "True",

        "--initial_prompt",
        prompt,

        "--temperature",
        "0",

        "--condition_on_previous_text",
        "False",

        "--fp16",
        "False",

        "--output_format",
        "json",

        "--output_dir",
        str(
            OUTPUT_DIR
        ),

        "--verbose",
        "False",
    ]

    try:

        run(
            command
        )

    except Exception as error:

        print(
            "WARNUNG: Whisper fehlgeschlagen:"
        )

        print(
            error
        )

        return None

    if not json_file.exists():

        print(
            "WARNUNG: Whisper JSON fehlt."
        )

        return None

    print(
        "Whisper erfolgreich: "
        + str(
            json_file
        )
    )

    return json_file


# =========================================================
# EXTRACT WORDS
# =========================================================

def extract_words(data):

    words = []

    if not isinstance(
        data,
        dict
    ):

        return words

    for segment in data.get(
        "segments",
        []
    ):

        if not isinstance(
            segment,
            dict
        ):

            continue

        segment_words = segment.get(
            "words",
            []
        )

        if not isinstance(
            segment_words,
            list
        ):

            continue

        for word in segment_words:

            if not isinstance(
                word,
                dict
            ):

                continue

            text = clean_text(
                word.get(
                    "word",
                    ""
                )
            )

            if not text:

                continue

            try:

                start = float(
                    word.get(
                        "start",
                        0
                    )
                )

                end = float(
                    word.get(
                        "end",
                        start + 0.2
                    )
                )

            except Exception:

                continue

            if end <= start:

                end = (
                    start
                    + 0.2
                )

            words.append({
                "text": text,
                "start": start,
                "end": end,
            })

    return words


# =========================================================
# FALLBACK SEGMENTS
# =========================================================

def extract_segments(data):

    segments = []

    if not isinstance(
        data,
        dict
    ):

        return segments

    for segment in data.get(
        "segments",
        []
    ):

        if not isinstance(
            segment,
            dict
        ):

            continue

        text = clean_text(
            segment.get(
                "text",
                ""
            )
        )

        if not text:

            continue

        try:

            start = float(
                segment.get(
                    "start",
                    0
                )
            )

            end = float(
                segment.get(
                    "end",
                    start + 2
                )
            )

        except Exception:

            continue

        if end <= start:

            end = (
                start
                + 2
            )

        segments.append({
            "text": text,
            "start": start,
            "end": end,
        })

    return segments


# =========================================================
# TIKTOK CAPTION CHUNKS
# =========================================================

def words_to_chunks(words):

    chunks = []

    current = []

    for word in words:

        current.append(
            word
        )

        current_text = " ".join(
            item[
                "text"
            ]
            for item in current
        )

        duration = (
            current[-1]["end"]
            - current[0]["start"]
        )

        should_finish = False

        if len(
            current
        ) >= 4:

            should_finish = True

        elif (
            len(current) >= 3
            and duration >= 1.2
        ):

            should_finish = True

        elif (
            len(current) >= 2
            and current[-1]["text"].endswith(
                (
                    ".",
                    "!",
                    "?",
                    ",",
                    ":",
                    ";",
                )
            )
        ):

            should_finish = True

        elif len(
            current_text
        ) >= 28:

            should_finish = True

        if not should_finish:

            continue

        chunks.append(
            current
        )

        current = []

    if current:

        chunks.append(
            current
        )

    return chunks


# =========================================================
# FALLBACK CAPTION GROUPS
# =========================================================

def segment_to_word_groups(
    segment
):

    words = (
        segment[
            "text"
        ]
        .split()
    )

    if not words:

        return []

    groups = []

    max_words = 4

    pieces = [
        words[
            i:i + max_words
        ]
        for i in range(
            0,
            len(
                words
            ),
            max_words
        )
    ]

    duration = max(
        0.5,
        segment[
            "end"
        ]
        - segment[
            "start"
        ]
    )

    for index, piece in enumerate(
        pieces
    ):

        start = (
            segment[
                "start"
            ]
            + duration
            * index
            / len(
                pieces
            )
        )

        end = (
            segment[
                "start"
            ]
            + duration
            * (
                index + 1
            )
            / len(
                pieces
            )
        )

        groups.append({
            "text":
                " ".join(
                    piece
                ),
            "start":
                start,
            "end":
                end,
        })

    return groups


# =========================================================
# KARAOKE TEXT
# =========================================================

def create_karaoke_text(
    words
):

    parts = []

    for word in words:

        duration = max(
            0.08,
            word[
                "end"
            ]
            - word[
                "start"
            ]
        )

        centiseconds = max(
            8,
            int(
                duration
                * 100
            )
        )

        text = escape_ass_text(
            word[
                "text"
            ]
        )

        parts.append(
            "{\\kf"
            + str(
                centiseconds
            )
            + "}"
            + text
        )

    return " ".join(
        parts
    )


# =========================================================
# WRITE FALLBACK HOOK ASS
# =========================================================

def write_hook_only_ass(
    ass_file,
    header,
    clip_title,
    hook_seed
):

    lines = list(
        header
    )

    hook = create_hook(
        {},
        clip_title,
        hook_seed
    )

    hook_text = hook_to_ass(
        hook
    )

    lines.append(
        "Dialogue: 1,"
        "0:00:00.00,"
        f"{HOOK_END_TIME},"
        "Hook,"
        ","
        "0,"
        "0,"
        "0,"
        ","
        f"{hook_text}"
    )

    with open(
        ass_file,
        "w",
        encoding="utf-8"
    ) as file:

        file.write(
            "\n".join(
                lines
            )
        )

    return {
        "has_ass_content": True,
        "has_subtitles": False,
        "hook": hook,
    }


# =========================================================
# ASS SUBTITLE FILE
# =========================================================

def create_ass(
    json_file,
    ass_file,
    clip_title="",
    hook_seed=""
):

    ass_file = Path(
        ass_file
    )

    header = [
        "[Script Info]",
        "ScriptType: v4.00+",
        "PlayResX: 1080",
        "PlayResY: 1920",
        "ScaledBorderAndShadow: yes",
        "WrapStyle: 2",
        "",

        "[V4+ Styles]",

        (
            "Format: Name, Fontname, Fontsize, "
            "PrimaryColour, SecondaryColour, "
            "OutlineColour, BackColour, Bold, "
            "Italic, Underline, StrikeOut, "
            "ScaleX, ScaleY, Spacing, Angle, "
            "BorderStyle, Outline, Shadow, "
            "Alignment, MarginL, MarginR, "
            "MarginV, Encoding"
        ),

        # =================================================
        # CAPTIONS
        # =================================================

        (
            "Style: TikTok,"
            "DejaVu Sans,"
            "72,"
            "&H00FFFFFF,"
            "&H0000FFFF,"
            "&H00000000,"
            "&H70000000,"
            "-1,"
            "0,"
            "0,"
            "0,"
            "100,"
            "100,"
            "1,"
            "0,"
            "1,"
            "6,"
            "2,"
            "2,"
            "70,"
            "70,"
            "420,"
            "1"
        ),

        # =================================================
        # V5 HOOK
        #
        # TikTok-artiger kompakter Overlay:
        # - Arial/Arial Bold Fallback über Liberation Sans
        # - große weiße Schrift
        # - schwarzer kräftiger Rand
        # - roter kompakter Hintergrund
        # - kein riesiger voller Bildschirmbalken
        # =================================================

        (
            "Style: Hook,"
            "Liberation Sans,"
            "86,"
            "&H00FFFFFF,"
            "&H00FFFFFF,"
            "&H00000000,"
            "&H001818E8,"
            "-1,"
            "0,"
            "0,"
            "0,"
            "100,"
            "100,"
            "0,"
            "0,"
            "3,"
            "10,"
            "0,"
            "8,"
            "80,"
            "80,"
            "205,"
            "1"
        ),

        "",

        "[Events]",

        (
            "Format: Layer, Start, End, "
            "Style, Name, MarginL, MarginR, "
            "MarginV, Effect, Text"
        ),
    ]

    # =====================================================
    # WHISPER FEHLER -> TROTZDEM HOOK
    # =====================================================

    if json_file is None:

        return write_hook_only_ass(
            ass_file,
            header,
            clip_title,
            hook_seed
        )

    json_file = Path(
        json_file
    )

    try:

        with open(
            json_file,
            "r",
            encoding="utf-8"
        ) as file:

            data = json.load(
                file
            )

    except Exception as error:

        print(
            f"Whisper JSON Fehler: {error}"
        )

        return write_hook_only_ass(
            ass_file,
            header,
            clip_title,
            hook_seed
        )

    words = extract_words(
        data
    )

    lines = list(
        header
    )

    # =====================================================
    # PERMANENTE HOOK
    # =====================================================

    hook = create_hook(
        data,
        clip_title,
        hook_seed
    )

    if (
        HOOKS_ENABLED
        and not hook
    ):

        hook = format_hook(
            stable_choice(
                FALLBACK_HOOKS,
                (
                    str(
                        hook_seed
                    )
                    + "|absolute-emergency"
                )
            )
        )

    hook_added = False

    if hook:

        hook_text = hook_to_ass(
            hook
        )

        lines.append(
            "Dialogue: 1,"
            "0:00:00.00,"
            f"{HOOK_END_TIME},"
            "Hook,"
            ","
            "0,"
            "0,"
            "0,"
            ","
            f"{hook_text}"
        )

        hook_added = True

        print(
            "PERMANENTE HOOK: "
            + hook
        )

    # =====================================================
    # WORD TIMESTAMP CAPTIONS
    # =====================================================

    if words:

        chunks = words_to_chunks(
            words
        )

        for chunk in chunks:

            if not chunk:

                continue

            start = (
                chunk[
                    0
                ][
                    "start"
                ]
            )

            end = (
                chunk[
                    -1
                ][
                    "end"
                ]
            )

            if (
                end
                - start
                < 0.35
            ):

                end = (
                    start
                    + 0.35
                )

            text = create_karaoke_text(
                chunk
            )

            lines.append(
                "Dialogue: 0,"
                f"{ass_time(start)},"
                f"{ass_time(end)},"
                "TikTok,"
                ","
                "0,"
                "0,"
                "0,"
                ","
                f"{text}"
            )

    # =====================================================
    # FALLBACK CAPTIONS
    # =====================================================

    else:

        segments = extract_segments(
            data
        )

        for segment in segments:

            groups = (
                segment_to_word_groups(
                    segment
                )
            )

            for group in groups:

                text = escape_ass_text(
                    group[
                        "text"
                    ]
                )

                lines.append(
                    "Dialogue: 0,"
                    f"{ass_time(group['start'])},"
                    f"{ass_time(group['end'])},"
                    "TikTok,"
                    ","
                    "0,"
                    "0,"
                    "0,"
                    ","
                    f"{text}"
                )

    caption_count = (
        len(
            lines
        )
        - len(
            header
        )
        - (
            1
            if hook_added
            else 0
        )
    )

    with open(
        ass_file,
        "w",
        encoding="utf-8"
    ) as file:

        file.write(
            "\n".join(
                lines
            )
        )

    print(
        f"{caption_count} "
        "TikTok-Untertitelblöcke erstellt."
    )

    return {
        "has_ass_content":
            (
                caption_count > 0
                or hook_added
            ),

        "has_subtitles":
            (
                caption_count > 0
            ),

        "hook":
            hook,
    }


# =========================================================
# ESCAPE FILTER PATH
# =========================================================

def escape_filter_path(path):

    absolute = str(
        Path(
            path
        ).resolve()
    )

    absolute = (
        absolute
        .replace(
            "\\",
            "/"
        )
        .replace(
            ":",
            "\\:"
        )
        .replace(
            "'",
            "\\'"
        )
    )

    return absolute


# =========================================================
# VIDEO FILTER
# =========================================================

def create_filter(
    ass_file,
    has_ass_content
):

    filter_parts = [

        (
            "[0:v]"
            "scale=1080:1920:"
            "force_original_aspect_ratio=increase,"
            "crop=1080:1920,"
            "boxblur=25:10,"
            "eq=brightness=-0.12,"
            "setsar=1"
            "[bg]"
        ),

        (
            "[0:v]"
            "scale=1080:1920:"
            "force_original_aspect_ratio=decrease,"
            "setsar=1"
            "[fg]"
        ),

        (
            "[bg][fg]"
            "overlay="
            "(W-w)/2:"
            "(H-h)/2"
            "[combined]"
        ),
    ]

    current = "[combined]"

    # =====================================================
    # WATERMARK
    # =====================================================

    filter_parts.append(
        current
        +
        "drawtext="
        f"text='{WATERMARK}':"
        "font='DejaVu Sans':"
        "fontsize=54:"
        "fontcolor=white@0.58:"
        "borderw=3:"
        "bordercolor=black@0.40:"
        "x=(w-text_w)/2:"
        "y=(h-text_h)/2"
        "[watermarked]"
    )

    current = "[watermarked]"

    # =====================================================
    # SUBTITLES + HOOK
    # =====================================================

    if has_ass_content:

        escaped_ass = (
            escape_filter_path(
                ass_file
            )
        )

        filter_parts.append(
            current
            +
            "subtitles="
            f"'{escaped_ass}'"
            ":fontsdir="
            "/usr/share/fonts/"
            "truetype"
            "[final]"
        )

        current = "[final]"

    return (
        ";".join(
            filter_parts
        ),
        current
    )


# =========================================================
# PROCESS VIDEO
# =========================================================

def process_video(
    source,
    output,
    index,
    metadata
):

    source = Path(
        source
    )

    output = Path(
        output
    )

    print("")
    print(
        "========================================"
    )
    print(
        f"VIDEO {index}"
    )
    print(
        "========================================"
    )

    print(
        f"Quelle: {source}"
    )

    if not source.exists():

        raise RuntimeError(
            f"Quelldatei fehlt: {source}"
        )

    source_size = (
        source.stat().st_size
    )

    print(
        "Quelldatei Größe: "
        f"{source_size / 1024 / 1024:.1f} MB"
    )

    if source_size < 10000:

        raise RuntimeError(
            f"Quelldatei ist verdächtig klein: "
            f"{source}"
        )

    clip_title = ""

    if isinstance(
        metadata,
        dict
    ):

        clip_title = metadata.get(
            "title",
            ""
        )

    print(
        f"Clip-Titel: {clip_title}"
    )

    # =====================================================
    # TRANSKRIPTION
    # =====================================================

    json_file = create_transcription(
        source,
        clip_title
    )

    # =====================================================
    # ASS
    # =====================================================

    ass_file = (
        OUTPUT_DIR
        / f"caption_{index}.ass"
    )

    ass_result = create_ass(
        json_file,
        ass_file,
        clip_title,
        (
            source.name
            + "|"
            + clip_title
        )
    )

    has_ass_content = (
        ass_result[
            "has_ass_content"
        ]
    )

    has_subtitles = (
        ass_result[
            "has_subtitles"
        ]
    )

    hook = (
        ass_result[
            "hook"
        ]
    )

    print(
        "Untertitel: "
        + (
            "JA"
            if has_subtitles
            else "NEIN"
        )
    )

    print(
        "Hook: "
        + (
            hook
            if hook
            else "KEINER"
        )
    )

    # =====================================================
    # FILTER
    # =====================================================

    (
        filter_complex,
        final_stream
    ) = create_filter(
        ass_file,
        has_ass_content
    )

    # =====================================================
    # EXPORT
    # =====================================================

    command = [
        "ffmpeg",
        "-y",

        "-i",
        str(
            source
        ),

        "-filter_complex",
        filter_complex,

        "-map",
        final_stream,

        "-map",
        "0:a?",

        "-c:v",
        "libx264",

        "-preset",
        "veryfast",

        "-crf",
        "20",

        "-pix_fmt",
        "yuv420p",

        "-profile:v",
        "high",

        "-level",
        "4.1",

        "-c:a",
        "aac",

        "-b:a",
        "192k",

        "-ar",
        "48000",

        "-movflags",
        "+faststart",

        "-shortest",

        str(
            output
        ),
    ]

    run(
        command
    )

    if not output.exists():

        raise RuntimeError(
            f"Finales Video fehlt: {output}"
        )

    size = (
        output.stat().st_size
    )

    if size < 100000:

        raise RuntimeError(
            "Finales Video ist verdächtig klein."
        )

    print("")
    print(
        f"FERTIG: {output}"
    )

    print(
        f"Größe: "
        f"{size / 1024 / 1024:.1f} MB"
    )

    return {
        "output":
            str(
                output
            ),

        "subtitles":
            has_subtitles,

        "hook":
            hook,
    }


# =========================================================
# CLEAN TEMP
# =========================================================

def cleanup_temp_files():

    extensions = (
        "*.json",
        "*.ass",
        "*.txt",
        "*.srt",
        "*.vtt",
        "*.tsv",
    )

    for extension in extensions:

        for path in OUTPUT_DIR.glob(
            extension
        ):

            try:

                if path.is_file():

                    path.unlink()

            except Exception:

                pass


# =========================================================
# DEBUG
# =========================================================

def print_repository_debug():

    print("")
    print(
        "========================================"
    )
    print(
        "REPOSITORY DEBUG"
    )
    print(
        "========================================"
    )

    print(
        f"Current Working Directory: "
        f"{Path.cwd()}"
    )

    print(
        f"Script Directory: "
        f"{SCRIPT_DIR}"
    )

    print(
        f"Repository Root: "
        f"{REPO_ROOT}"
    )

    print("")
    print(
        "Ordner im Repository:"
    )

    try:

        for path in sorted(
            REPO_ROOT.iterdir(),
            key=lambda item:
                item.name.lower()
        ):

            marker = (
                "DIR"
                if path.is_dir()
                else "FILE"
            )

            print(
                f"[{marker}] "
                f"{path.name}"
            )

    except Exception as error:

        print(
            "Repository konnte nicht "
            "aufgelistet werden:"
        )

        print(
            error
        )


# =========================================================
# MAIN
# =========================================================

def main():

    print("")
    print(
        "========================================"
    )
    print(
        "CLIPCRIP2 PROCESSOR V5.0"
    )
    print(
        "SHORT NATIVE TIKTOK HOOKS"
    )
    print(
        "========================================"
    )

    print(
        "- Jussef-spezifische Hooks"
    )

    print(
        "- Sehr kurze Hook-Texte"
    )

    print(
        "- Umgangssprache / TikTok-Sprache"
    )

    print(
        "- Keine Emojis im Render"
    )

    print(
        "- Keine Emoji-Kaestchen"
    )

    print(
        "- Hook auf jedem Video"
    )

    print(
        "- Hook ueber komplettes Video"
    )

    print(
        "- Roter kompakter TikTok-Hintergrund"
    )

    print(
        "- Grosse weisse fette Schrift"
    )

    print(
        "- TikTok Karaoke Captions"
    )

    print(
        "- @Clipcrip2 Wasserzeichen"
    )

    print_repository_debug()

    # =====================================================
    # OUTPUT CLEAN
    # =====================================================

    clean_output()

    # =====================================================
    # INPUT
    # =====================================================

    videos = find_videos()

    if not videos:

        print("")
        print(
            "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
        )
        print(
            "FEHLER: selected_clips IST LEER"
        )
        print(
            "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
        )

        raise RuntimeError(
            "Keine selected_clips gefunden. "
            "Quality Control muss vorher exakt "
            "5 Dateien nach selected_clips schreiben."
        )

    if len(
        videos
    ) < MAX_VIDEOS:

        raise RuntimeError(
            f"Zu wenige selected_clips. "
            f"Erwartet: {MAX_VIDEOS}. "
            f"Gefunden: {len(videos)}."
        )

    if len(
        videos
    ) > MAX_VIDEOS:

        print(
            f"WARNUNG: {len(videos)} Videos gefunden."
        )

        print(
            f"Nur die ersten {MAX_VIDEOS} "
            "werden verarbeitet."
        )

    videos = videos[
        :MAX_VIDEOS
    ]

    print("")
    print(
        "========================================"
    )
    print(
        "5 INPUT VIDEOS"
    )
    print(
        "========================================"
    )

    for index, video in enumerate(
        videos,
        start=1
    ):

        print(
            f"{index}. {video.name}"
        )

    # =====================================================
    # METADATA
    # =====================================================

    metadata_list = load_json(
        METADATA_FILE,
        []
    )

    if not isinstance(
        metadata_list,
        list
    ):

        print(
            "WARNUNG: clips_today.json "
            "ist keine Liste."
        )

        metadata_list = []

    print("")
    print(
        f"{len(metadata_list)} "
        "Metadata-Einträge geladen."
    )

    successful = []

    failed = []

    # =====================================================
    # PROCESS ALL 5
    # =====================================================

    for index, source in enumerate(
        videos,
        start=1
    ):

        output = (
            OUTPUT_DIR
            / (
                f"{index:02d}_"
                f"{OUTPUT_PREFIX}.mp4"
            )
        )

        metadata = {}

        if (
            index - 1
            < len(
                metadata_list
            )
        ):

            possible_metadata = (
                metadata_list[
                    index - 1
                ]
            )

            if isinstance(
                possible_metadata,
                dict
            ):

                metadata = (
                    possible_metadata
                )

        try:

            result = process_video(
                source,
                output,
                index,
                metadata
            )

            successful.append(
                result
            )

        except Exception as error:

            print("")
            print(
                "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
            )
            print(
                f"FEHLER VIDEO {index}"
            )
            print(
                error
            )
            print(
                "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
            )

            failed.append({
                "video":
                    str(
                        source
                    ),
                "error":
                    str(
                        error
                    ),
            })

    # =====================================================
    # CLEAN TEMP
    # =====================================================

    cleanup_temp_files()

    # =====================================================
    # RESULT
    # =====================================================

    print("")
    print(
        "========================================"
    )
    print(
        "ERGEBNIS"
    )
    print(
        "========================================"
    )

    print(
        f"ERFOLG: "
        f"{len(successful)}/5"
    )

    print(
        f"FEHLER: "
        f"{len(failed)}/5"
    )

    subtitle_count = sum(
        1
        for item in successful
        if item[
            "subtitles"
        ]
    )

    print(
        f"MIT UNTERTITELN: "
        f"{subtitle_count}/"
        f"{len(successful)}"
    )

    hook_count = sum(
        1
        for item in successful
        if item.get(
            "hook",
            ""
        )
    )

    print(
        f"MIT HOOK: "
        f"{hook_count}/"
        f"{len(successful)}"
    )

    # =====================================================
    # HOOKS PFLICHT
    # =====================================================

    if (
        HOOKS_ENABLED
        and hook_count
        != len(
            successful
        )
    ):

        raise RuntimeError(
            "Hook-Validierung fehlgeschlagen: "
            "Nicht jedes erfolgreiche Video "
            "hat eine Hook."
        )

    if len(
        successful
    ) != MAX_VIDEOS:

        print("")
        print(
            "FEHLERDETAILS:"
        )

        for item in failed:

            print("")
            print(
                item[
                    "video"
                ]
            )

            print(
                item[
                    "error"
                ]
            )

        raise RuntimeError(
            "Nicht alle 5 Videos "
            "wurden verarbeitet."
        )

    # =====================================================
    # OUTPUT VALIDATION
    # =====================================================

    final_files = sorted(
        OUTPUT_DIR.glob(
            "*.mp4"
        )
    )

    print("")
    print(
        f"{len(final_files)} "
        "finale MP4-Dateien gefunden."
    )

    for file in final_files:

        print(
            "OUTPUT: "
            + file.name
        )

    if len(
        final_files
    ) != MAX_VIDEOS:

        raise RuntimeError(
            "Output enthält nicht "
            "genau 5 MP4-Dateien."
        )

    for file in final_files:

        size = (
            file.stat().st_size
        )

        if size < 100000:

            raise RuntimeError(
                f"Output-Datei zu klein: "
                f"{file}"
            )

    print("")
    print(
        "========================================"
    )
    print(
        "PROCESSOR V5.0 ERFOLGREICH"
    )
    print(
        "5/5 Videos fertig."
    )
    print(
        "5/5 mit permanenter Short Hook."
    )
    print(
        "========================================"
    )


if __name__ == "__main__":

    main()