import os
import glob
import json
import re
import shutil
import subprocess
import sys


INPUT_DIR = "selected_clips"
OUTPUT_DIR = "tiktok_ready"
METADATA_FILE = "clips_today.json"

MAX_VIDEOS = 5

# Deutlich bessere Erkennung als small,
# besonders bei Umgangssprache / schwierigerem Audio.
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

    print("")
    print("RUN:", " ".join(command))

    result = subprocess.run(command)

    if result.returncode != 0:
        raise RuntimeError(
            "Befehl fehlgeschlagen: "
            + " ".join(command)
        )


# =========================================================
# JSON
# =========================================================

def load_json(path, default):

    if not os.path.exists(path):
        return default

    try:
        with open(
            path,
            "r",
            encoding="utf-8"
        ) as file:
            return json.load(file)

    except Exception:
        return default


# =========================================================
# FIND VIDEOS
# =========================================================

def find_videos():

    videos = []

    for extension in (
        "mp4",
        "webm",
        "mkv",
        "mov"
    ):

        videos.extend(
            glob.glob(
                os.path.join(
                    INPUT_DIR,
                    f"*.{extension}"
                )
            )
        )

    return sorted(videos)


# =========================================================
# CLEAN OUTPUT
# =========================================================

def clean_output():

    os.makedirs(
        OUTPUT_DIR,
        exist_ok=True
    )

    for path in glob.glob(
        os.path.join(
            OUTPUT_DIR,
            "*"
        )
    ):

        if os.path.isfile(path):
            os.remove(path)

        elif os.path.isdir(path):
            shutil.rmtree(path)


# =========================================================
# TEXT
# =========================================================

def clean_text(text):

    text = str(text).strip()

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    text = (
        text
        .replace("{", "(")
        .replace("}", ")")
        .replace("\\", "")
    )

    return text


def escape_ass_text(text):

    text = clean_text(text)

    text = (
        text
        .replace("\\", "")
        .replace("{", "(")
        .replace("}", ")")
        .replace("\n", " ")
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
        (seconds % 3600) // 60
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
    print("WHISPER TURBO")
    print(
        "========================================"
    )

    print(
        f"Analysiere Sprache: {video}"
    )

    base_name = os.path.splitext(
        os.path.basename(video)
    )[0]

    json_file = os.path.join(
        OUTPUT_DIR,
        base_name + ".json"
    )

    if os.path.exists(json_file):
        os.remove(json_file)

    prompt = BASE_PROMPT

    if clip_title:

        prompt += (
            " Der Twitch-Clip trägt den Titel: "
            + clean_text(clip_title)
            + "."
        )

    command = [
        sys.executable,
        "-m",
        "whisper",

        video,

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

        # stabilere Decodierung
        "--temperature",
        "0",

        "--beam_size",
        "5",

        "--condition_on_previous_text",
        "False",

        # GitHub Runner = CPU
        "--fp16",
        "False",

        "--output_format",
        "json",

        "--output_dir",
        OUTPUT_DIR,

        "--verbose",
        "False",
    ]

    try:

        run(command)

    except Exception as error:

        print(
            "WARNUNG: Whisper fehlgeschlagen:"
        )

        print(error)

        return None

    if not os.path.exists(json_file):

        print(
            "WARNUNG: Whisper JSON fehlt."
        )

        return None

    return json_file


# =========================================================
# EXTRACT WORDS
# =========================================================

def extract_words(data):

    words = []

    for segment in data.get(
        "segments",
        []
    ):

        for word in segment.get(
            "words",
            []
        ):

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
                end = start + 0.2

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

    for segment in data.get(
        "segments",
        []
    ):

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
            end = start + 2

        segments.append({
            "text": text,
            "start": start,
            "end": end,
        })

    return segments


# =========================================================
# TIKTOK CHUNKS
# =========================================================

def words_to_chunks(words):

    """
    Klassischer TikTok-Stil:
    kurze 2–4 Wortgruppen.
    """

    chunks = []

    current = []

    for word in words:

        current.append(word)

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

        elif len(current_text) >= 28:
            should_finish = True

        if not should_finish:
            continue

        chunks.append(current)

        current = []

    if current:
        chunks.append(current)

    return chunks


# =========================================================
# FALLBACK CHUNKS
# =========================================================

def segment_to_word_groups(segment):

    words = (
        segment["text"]
        .split()
    )

    if not words:
        return []

    groups = []

    max_words = 4

    pieces = [
        words[i:i + max_words]
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
            * (index + 1)
            / len(pieces)
        )

        groups.append({
            "text": " ".join(piece),
            "start": start,
            "end": end,
        })

    return groups


# =========================================================
# KARAOKE TEXT
# =========================================================

def create_karaoke_text(words):

    """
    ASS Karaoke:
    gesprochenes Wort wird gelb,
    Rest bleibt weiß.
    """

    parts = []

    for word in words:

        duration = max(
            0.08,
            word["end"]
            - word["start"]
        )

        centiseconds = max(
            8,
            int(duration * 100)
        )

        text = escape_ass_text(
            word["text"]
        )

        # \kf sorgt für laufendes Highlighting.
        parts.append(
            "{\\kf"
            + str(centiseconds)
            + "}"
            + text
        )

    return " ".join(parts)


# =========================================================
# ASS SUBTITLE FILE
# =========================================================

def create_ass(
    json_file,
    ass_file
):

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
            # Karaoke Highlight GELB
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
            # Alignment 2 = unten mittig
            "2,"
            "70,"
            "70,"
            # etwas oberhalb TikTok UI
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
                "\n".join(header)
            )

        return False

    try:

        with open(
            json_file,
            "r",
            encoding="utf-8"
        ) as file:

            data = json.load(file)

    except Exception as error:

        print(
            f"Whisper JSON Fehler: {error}"
        )

        return False

    words = extract_words(data)

    lines = list(header)

    # =====================================================
    # BEST CASE: WORD TIMESTAMPS
    # =====================================================

    if words:

        chunks = words_to_chunks(
            words
        )

        for chunk in chunks:

            start = chunk[0]["start"]
            end = chunk[-1]["end"]

            # Minimale Lesedauer
            if end - start < 0.35:
                end = start + 0.35

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

            groups = segment_to_word_groups(
                segment
            )

            for group in groups:

                text = escape_ass_text(
                    group["text"]
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
            "\n".join(lines)
        )

    print(
        f"{caption_count} "
        "TikTok-Untertitelblöcke erstellt."
    )

    return caption_count > 0


# =========================================================
# ESCAPE PATH
# =========================================================

def escape_filter_path(path):

    absolute = os.path.abspath(
        path
    )

    absolute = (
        absolute
        .replace("\\", "/")
        .replace(":", "\\:")
        .replace("'", "\\'")
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

        # BLURRED BACKGROUND
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

        # KOMPLETTES ORIGINAL
        (
            "[0:v]"
            "scale=1080:1920:"
            "force_original_aspect_ratio=decrease,"
            "setsar=1"
            "[fg]"
        ),

        # ORIGINAL MITTIG
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
        "text='@Clipcrip2':"
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

        escaped_ass = escape_filter_path(
            ass_file
        )

        filter_parts.append(
            current
            +
            "subtitles="
            f"'{escaped_ass}'"
            ":fontsdir=/usr/share/fonts/truetype/dejavu"
            "[final]"
        )

        current = "[final]"

    return (
        ";".join(filter_parts),
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

    clip_title = ""

    if isinstance(metadata, dict):
        clip_title = metadata.get(
            "title",
            ""
        )

    print(
        f"Clip-Titel: {clip_title}"
    )

    # =====================================================
    # 1. TRANSKRIPTION
    # =====================================================

    json_file = create_transcription(
        source,
        clip_title
    )

    # =====================================================
    # 2. TIKTOK SUBTITLES
    # =====================================================

    ass_file = os.path.join(
        OUTPUT_DIR,
        f"caption_{index}.ass"
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

    filter_complex, final_stream = (
        create_filter(
            ass_file,
            has_subtitles
        )
    )

    # =====================================================
    # 4. FINAL EXPORT
    # =====================================================

    command = [
        "ffmpeg",
        "-y",

        "-i",
        source,

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

        output,
    ]

    run(command)

    if not os.path.exists(output):

        raise RuntimeError(
            f"Finales Video fehlt: "
            f"{output}"
        )

    size = os.path.getsize(
        output
    )

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
        "output": output,
        "subtitles": has_subtitles,
    }


# =========================================================
# CLEAN TEMP FILES
# =========================================================

def cleanup_temp_files():

    for extension in (
        "*.json",
        "*.ass",
        "*.txt",
        "*.srt",
        "*.vtt",
        "*.tsv"
    ):

        for path in glob.glob(
            os.path.join(
                OUTPUT_DIR,
                extension
            )
        ):

            try:
                os.remove(path)
            except Exception:
                pass


# =========================================================
# MAIN
# =========================================================

def main():

    print("")
    print(
        "========================================"
    )
    print(
        "CLIPCRIP2 PROCESSOR V3"
    )
    print(
        "========================================"
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

    clean_output()

    videos = find_videos()

    if not videos:

        raise RuntimeError(
            "Keine selected_clips gefunden."
        )

    videos = videos[
        :MAX_VIDEOS
    ]

    if len(videos) != 5:

        raise RuntimeError(
            f"Nicht genau 5 Videos. "
            f"Gefunden: {len(videos)}"
        )

    metadata_list = load_json(
        METADATA_FILE,
        []
    )

    successful = []
    failed = []

    for index, source in enumerate(
        videos,
        start=1
    ):

        output = os.path.join(
            OUTPUT_DIR,
            (
                f"{index:02d}_"
                f"{OUTPUT_PREFIX}.mp4"
            )
        )

        metadata = {}

        if (
            index - 1
            < len(metadata_list)
        ):
            metadata = metadata_list[
                index - 1
            ]

        try:

            result = process_video(
                source,
                output,
                index,
                metadata
            )

            successful.append(result)

        except Exception as error:

            print("")
            print(
                "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
            )
            print(
                f"FEHLER VIDEO {index}"
            )
            print(error)
            print(
                "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
            )

            failed.append({
                "video": source,
                "error": str(error),
            })

    cleanup_temp_files()

    print("")
    print(
        "========================================"
    )
    print("ERGEBNIS")
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
        if item["subtitles"]
    )

    print(
        f"MIT UNTERTITELN: "
        f"{subtitle_count}/"
        f"{len(successful)}"
    )

    if len(successful) != 5:

        for item in failed:

            print(
                item["video"]
            )
            print(
                item["error"]
            )

        raise RuntimeError(
            "Nicht alle 5 Videos "
            "wurden verarbeitet."
        )

    final_files = glob.glob(
        os.path.join(
            OUTPUT_DIR,
            "*.mp4"
        )
    )

    if len(final_files) != 5:

        raise RuntimeError(
            "Output enthält nicht "
            "genau 5 MP4-Dateien."
        )

    print("")
    print(
        "========================================"
    )
    print(
        "PROCESSOR V3 ERFOLGREICH"
    )
    print(
        "5/5 Videos fertig."
    )
    print(
        "========================================"
    )


if __name__ == "__main__":
    main()