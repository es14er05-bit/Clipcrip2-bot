import os
import glob
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path


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
# STREAMER / SLANG CONTEXT
# =========================================================

BASE_PROMPT = (
    "Dies ist ein deutscher Twitch-Stream von Jussef. "
    "Die Sprecher reden locker, schnell und umgangssprachlich. "
    "Häufige Wörter und Namen können sein: "
    "Jussef, Yussef, Yavuz, Twitch, Discord, Stream, Streamer, "
    "Chat, Clip, Gameplay, Game, Bro, Bruder, Digga, Digger, "
    "Junge, Alter, Wallah, Vallah, Mashallah, Inshallah, "
    "Habibi, safe, cringe, crazy, NPC, Chatten, zocken, "
    "TikTok, YouTube, Fortnite, Minecraft, GTA. "
    "Transkribiere das tatsächlich Gesagte möglichst wortgetreu. "
    "Ändere Umgangssprache nicht unnötig in Hochdeutsch."
)


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

            return json.load(file)

    except Exception as error:

        print(
            f"JSON konnte nicht geladen werden: "
            f"{path}"
        )

        print(error)

        return default


# =========================================================
# VIDEO SORTIERUNG
# =========================================================

def video_number(path):

    name = Path(path).stem

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

            print(error)

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
            video_number(path),
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
                f"Konnte Output-Datei nicht "
                f"löschen: {path}"
            )

            print(error)


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
# ASS TIME
# =========================================================

def ass_time(seconds):

    seconds = max(
        0.0,
        float(seconds)
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
            - int(seconds)
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

        str(video),

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
        str(OUTPUT_DIR),

        "--verbose",
        "False",
    ]

    try:

        run(
            command
        )

    except Exception as error:

        print(
            "WARNUNG: Whisper "
            "fehlgeschlagen:"
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
        + str(json_file)
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
                "text":
                    text,

                "start":
                    start,

                "end":
                    end,
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
            "text":
                text,

            "start":
                start,

            "end":
                end,
        })

    return segments


# =========================================================
# TIKTOK CHUNKS
# =========================================================

def words_to_chunks(words):

    chunks = []

    current = []

    for word in words:

        current.append(
            word
        )

        current_text = " ".join(
            item["text"]
            for item in current
        )

        duration = (
            current[-1]["end"]
            - current[0]["start"]
        )

        should_finish = False

        if len(current) >= 4:

            should_finish = True

        elif (
            len(current) >= 3
            and duration >= 1.2
        ):

            should_finish = True

        elif (
            len(current) >= 2
            and current[-1][
                "text"
            ].endswith(
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
# FALLBACK CHUNKS
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
            len(words),
            max_words
        )
    ]

    duration = max(
        0.5,
        segment["end"]
        - segment["start"]
    )

    for index, piece in enumerate(
        pieces
    ):

        start = (
            segment["start"]
            + duration
            * index
            / len(pieces)
        )

        end = (
            segment["start"]
            + duration
            * (
                index + 1
            )
            / len(pieces)
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
            word["end"]
            - word["start"]
        )

        centiseconds = max(
            8,
            int(
                duration
                * 100
            )
        )

        text = escape_ass_text(
            word["text"]
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
# ASS SUBTITLE FILE
# =========================================================

def create_ass(
    json_file,
    ass_file
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

        "",

        "[Events]",

        (
            "Format: Layer, Start, End, "
            "Style, Name, MarginL, MarginR, "
            "MarginV, Effect, Text"
        ),
    ]

    if json_file is None:

        with open(
            ass_file,
            "w",
            encoding="utf-8"
        ) as file:

            file.write(
                "\n".join(
                    header
                )
            )

        return False

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
            f"Whisper JSON Fehler: "
            f"{error}"
        )

        return False

    words = extract_words(
        data
    )

    lines = list(
        header
    )

    # =====================================================
    # WORD TIMESTAMPS
    # =====================================================

    if words:

        chunks = words_to_chunks(
            words
        )

        for chunk in chunks:

            if not chunk:
                continue

            start = chunk[
                0
            ][
                "start"
            ]

            end = chunk[
                -1
            ][
                "end"
            ]

            if (
                end - start
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
    # FALLBACK
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
        len(lines)
        - len(header)
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

    return (
        caption_count
        > 0
    )


# =========================================================
# ESCAPE PATH
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
    has_subtitles
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
    # SUBTITLES
    # =====================================================

    if has_subtitles:

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
            "truetype/dejavu"
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
# PROCESS ONE VIDEO
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
            f"Quelldatei fehlt: "
            f"{source}"
        )

    source_size = source.stat().st_size

    print(
        "Quelldatei Größe: "
        f"{source_size / 1024 / 1024:.1f} MB"
    )

    if source_size < 10000:

        raise RuntimeError(
            f"Quelldatei ist "
            f"verdächtig klein: "
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
        f"Clip-Titel: "
        f"{clip_title}"
    )

    # =====================================================
    # 1. TRANSKRIPTION
    # =====================================================

    json_file = (
        create_transcription(
            source,
            clip_title
        )
    )

    # =====================================================
    # 2. TIKTOK SUBTITLES
    # =====================================================

    ass_file = (
        OUTPUT_DIR
        / f"caption_{index}.ass"
    )

    has_subtitles = create_ass(
        json_file,
        ass_file
    )

    print(
        "Untertitel: "
        + (
            "JA"
            if has_subtitles
            else "NEIN"
        )
    )

    # =====================================================
    # 3. VIDEO FILTER
    # =====================================================

    (
        filter_complex,
        final_stream
    ) = create_filter(
        ass_file,
        has_subtitles
    )

    # =====================================================
    # 4. FINAL EXPORT
    # =====================================================

    command = [
        "ffmpeg",
        "-y",

        "-i",
        str(source),

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

        str(output),
    ]

    run(
        command
    )

    if not output.exists():

        raise RuntimeError(
            f"Finales Video fehlt: "
            f"{output}"
        )

    size = output.stat().st_size

    if size < 100000:

        raise RuntimeError(
            "Finales Video ist "
            "verdächtig klein."
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
            str(output),

        "subtitles":
            has_subtitles,
    }


# =========================================================
# CLEAN TEMP FILES
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
# DEBUG REPOSITORY
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

        print(error)


# =========================================================
# MAIN
# =========================================================

def main():

    print("")
    print(
        "========================================"
    )

    print(
        "CLIPCRIP2 PROCESSOR V3.1"
    )

    print(
        "========================================"
    )

    print(
        "- Absolute Repository-Pfade"
    )

    print(
        "- selected_clips Prüfung"
    )

    print(
        "- Whisper Turbo"
    )

    print(
        "- Streamer-/Slang-Kontext"
    )

    print(
        "- Twitch-Titel als Kontext"
    )

    print(
        "- TikTok Karaoke Captions"
    )

    print(
        "- @Clipcrip2 Wasserzeichen"
    )

    print_repository_debug()

    # =====================================================
    # WICHTIG:
    # OUTPUT ERST LÖSCHEN.
    # selected_clips WIRD NICHT ANGEFASST.
    # =====================================================

    clean_output()

    # =====================================================
    # SELECTED CLIPS LADEN
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

        print(
            f"Gesuchter Pfad:"
        )

        print(
            str(INPUT_DIR)
        )

        print("")
        print(
            "Der Processor löscht selected_clips "
            "NICHT."
        )

        print(
            "Wenn dieser Ordner leer ist, hat "
            "quality_control.py keine Dateien "
            "dorthin geschrieben."
        )

        raise RuntimeError(
            "Keine selected_clips gefunden. "
            "Quality Control muss vorher exakt "
            "5 Dateien nach selected_clips schreiben."
        )

    # =====================================================
    # GENAU 5 ERWARTEN
    # =====================================================

    if len(videos) < MAX_VIDEOS:

        raise RuntimeError(
            f"Zu wenige selected_clips. "
            f"Erwartet: {MAX_VIDEOS}. "
            f"Gefunden: {len(videos)}."
        )

    if len(videos) > MAX_VIDEOS:

        print(
            f"WARNUNG: {len(videos)} Videos "
            "gefunden."
        )

        print(
            "Es werden nur die ersten "
            f"{MAX_VIDEOS} verarbeitet."
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
            f"{index}. "
            f"{video.name}"
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
    # VIDEOS VERARBEITEN
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
            < len(metadata_list)
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
                    str(source),

                "error":
                    str(error),
            })

    # =====================================================
    # TEMP DATEIEN ENTFERNEN
    # =====================================================

    cleanup_temp_files()

    # =====================================================
    # ERGEBNIS
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
    # OUTPUT VALIDIEREN
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

    # =====================================================
    # MINDESTGRÖSSE PRÜFEN
    # =====================================================

    for file in final_files:

        size = file.stat().st_size

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
        "PROCESSOR V3.1 ERFOLGREICH"
    )

    print(
        "5/5 Videos fertig."
    )

    print(
        "========================================"
    )


if __name__ == "__main__":

    main()