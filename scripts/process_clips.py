import os
import glob
import json
import re
import shutil
import subprocess
import sys


INPUT_DIR = "selected_clips"
OUTPUT_DIR = "tiktok_ready"

MAX_VIDEOS = 5

WHISPER_MODEL = "small"

OUTPUT_PREFIX = "jussef_tiktok"

WATERMARK = "@Clipcrip2"

TARGET_WIDTH = 1080
TARGET_HEIGHT = 1920


# =========================================================
# COMMAND
# =========================================================

def run(command):

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

    return sorted(
        videos
    )


# =========================================================
# CLEAN DIRECTORY
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
# FILE SAFE NAME
# =========================================================

def safe_name(text):

    text = re.sub(
        r"[^a-zA-Z0-9_-]",
        "_",
        text
    )

    return text


# =========================================================
# WHISPER
# =========================================================

def create_transcription(video):

    print("")
    print(
        "========================================"
    )

    print(
        "WHISPER"
    )

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

    if os.path.exists(
        json_file
    ):

        os.remove(
            json_file
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

        "--output_format",
        "json",

        "--output_dir",
        OUTPUT_DIR,

        "--verbose",
        "False",
    ]

    try:

        run(
            command
        )

    except Exception as error:

        print(
            "WARNUNG:"
        )

        print(
            f"Whisper fehlgeschlagen: "
            f"{error}"
        )

        return None

    if not os.path.exists(
        json_file
    ):

        print(
            "WARNUNG: Whisper JSON "
            "nicht gefunden."
        )

        return None

    return json_file


# =========================================================
# TEXT CLEANING
# =========================================================

def clean_text(text):

    text = str(
        text
    )

    text = text.strip()

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
        )
        // 60
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
# EXTRACT WHISPER WORDS
# =========================================================

def extract_words(data):

    words = []

    for segment in data.get(
        "segments",
        []
    ):

        segment_words = segment.get(
            "words",
            []
        )

        for word in segment_words:

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
                        "start"
                    )
                )

                end = float(
                    word.get(
                        "end"
                    )
                )

            except Exception:

                continue

            if end <= start:
                continue

            words.append({
                "text": text,
                "start": start,
                "end": end,
            })

    return words


# =========================================================
# EXTRACT SEGMENTS FALLBACK
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
# CREATE CAPTION CHUNKS
# =========================================================

def words_to_chunks(words):

    chunks = []

    current = []

    for word in words:

        current.append(
            word
        )

        text = " ".join(
            item[
                "text"
            ]
            for item in current
        )

        finished = False

        # TikTok-artig kurz halten.
        if len(current) >= 5:

            finished = True

        if len(text) >= 34:

            finished = True

        if word["text"].endswith(
            (
                ".",
                "!",
                "?",
                ",",
                ":",
                ";",
            )
        ):

            if len(current) >= 2:

                finished = True

        if not finished:
            continue

        chunks.append({
            "text": text,
            "start":
                current[0]["start"],
            "end":
                current[-1]["end"],
        })

        current = []

    if current:

        chunks.append({
            "text":
                " ".join(
                    item["text"]
                    for item
                    in current
                ),

            "start":
                current[0]["start"],

            "end":
                current[-1]["end"],
        })

    return chunks


# =========================================================
# SPLIT LONG SEGMENTS
# =========================================================

def segment_to_chunks(segment):

    text = segment[
        "text"
    ]

    words = text.split()

    if not words:

        return []

    max_words = 5

    groups = [
        words[i:i + max_words]
        for i in range(
            0,
            len(words),
            max_words
        )
    ]

    duration = (
        segment["end"]
        - segment["start"]
    )

    duration = max(
        duration,
        0.5
    )

    chunks = []

    for index, group in enumerate(
        groups
    ):

        start = (
            segment["start"]
            + duration
            * index
            / len(groups)
        )

        end = (
            segment["start"]
            + duration
            * (index + 1)
            / len(groups)
        )

        chunks.append({
            "text":
                " ".join(group),

            "start":
                start,

            "end":
                end,
        })

    return chunks


# =========================================================
# CREATE ASS SUBTITLE FILE
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
            "66,"
            "&H00FFFFFF,"
            "&H00FFFFFF,"
            "&H00000000,"
            "&H80000000,"
            "-1,"
            "0,"
            "0,"
            "0,"
            "100,"
            "100,"
            "0,"
            "0,"
            "1,"
            "5,"
            "1,"
            "2,"
            "80,"
            "80,"
            "340,"
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

    # -----------------------------------------
    # PRIORITÄT 1: Word timestamps
    # -----------------------------------------

    words = extract_words(
        data
    )

    if words:

        captions = words_to_chunks(
            words
        )

    else:

        # -------------------------------------
        # PRIORITÄT 2:
        # Whisper-Segmente.
        # Dadurch bekommen wir auch dann
        # Untertitel, wenn Word-Timestamps
        # fehlen.
        # -------------------------------------

        captions = []

        segments = extract_segments(
            data
        )

        for segment in segments:

            captions.extend(
                segment_to_chunks(
                    segment
                )
            )

    if not captions:

        print(
            "WARNUNG:"
        )

        print(
            "Whisper hat keinen "
            "gesprochenen Text erkannt."
        )

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

    lines = list(
        header
    )

    for caption in captions:

        text = clean_text(
            caption[
                "text"
            ]
        )

        if not text:
            continue

        # ASS reservierte Zeichen.
        text = (
            text
            .replace(
                "\n",
                " "
            )
        )

        lines.append(
            "Dialogue: 0,"
            f"{ass_time(caption['start'])},"
            f"{ass_time(caption['end'])},"
            "TikTok,"
            ","
            "0,"
            "0,"
            "0,"
            ","
            f"{text}"
        )

    with open(
        ass_file,
        "w",
        encoding="utf-8"
    ) as file:

        file.write(
            "\n".join(lines)
        )

    caption_count = (
        len(lines)
        - len(header)
    )

    print(
        f"{caption_count} "
        f"Untertitelblöcke erstellt."
    )

    return (
        caption_count > 0
    )


# =========================================================
# ESCAPE ASS PATH FOR FFMPEG
# =========================================================

def escape_filter_path(path):

    absolute = os.path.abspath(
        path
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

    # =====================================================
    # DESIGN
    #
    # Wir schneiden das Streambild NICHT mehr brutal
    # auf 9:16 zurecht.
    #
    # Ebene 1:
    # Source groß + blurred als Hintergrund.
    #
    # Ebene 2:
    # Komplettes Original proportional skaliert darüber.
    #
    # Dadurch bleiben Facecam UND Gameplay sichtbar.
    # =====================================================

    filter_parts = [

        # Background
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

        # Originalvideo komplett erhalten
        (
            "[0:v]"
            "scale=1080:1920:"
            "force_original_aspect_ratio=decrease,"
            "setsar=1"
            "[fg]"
        ),

        # Original mittig auf Background
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

    # Mittelgroß, mittig, halbtransparent.
    #
    # @Clipcrip2 wird dadurch in jedem Export sichtbar,
    # aber soll die Handlung nicht komplett verdecken.

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
    index
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

    print(
        f"Quelle: {source}"
    )

    # -----------------------------------------
    # 1. WHISPER
    # -----------------------------------------

    json_file = create_transcription(
        source
    )

    # -----------------------------------------
    # 2. ASS
    # -----------------------------------------

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
            else "NEIN / KEINE SPRACHE"
        )
    )

    # -----------------------------------------
    # 3. VIDEO FILTER
    # -----------------------------------------

    filter_complex, final_stream = (
        create_filter(
            ass_file,
            has_subtitles
        )
    )

    # -----------------------------------------
    # 4. FINAL EXPORT
    # -----------------------------------------

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

    run(
        command
    )

    if not os.path.exists(
        output
    ):

        raise RuntimeError(
            f"Finales Video fehlt: "
            f"{output}"
        )

    size = os.path.getsize(
        output
    )

    if size < 100000:

        raise RuntimeError(
            f"Finales Video ist "
            f"verdächtig klein: "
            f"{size} Bytes"
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

                os.remove(
                    path
                )

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
        "CLIPCRIP2 PROCESSOR V2"
    )

    print(
        "========================================"
    )

    print(
        "Features:"
    )

    print(
        "- komplette Streamansicht erhalten"
    )

    print(
        "- blurred 9:16 Hintergrund"
    )

    print(
        "- automatische Whisper-Untertitel"
    )

    print(
        "- @Clipcrip2 Wasserzeichen"
    )

    clean_output()

    videos = find_videos()

    if not videos:

        raise RuntimeError(
            "Keine Videos in "
            "selected_clips gefunden."
        )

    videos = videos[
        :MAX_VIDEOS
    ]

    print("")
    print(
        f"{len(videos)} Videos "
        f"werden verarbeitet."
    )

    if len(videos) != 5:

        raise RuntimeError(
            "Es wurden nicht genau "
            f"5 Input-Videos gefunden. "
            f"Gefunden: {len(videos)}"
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

        try:

            result = process_video(
                source,
                output,
                index
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
                str(error)
            )

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

    # Jetzt nicht mehr stillschweigend
    # mit 1/5 oder 3/5 weitermachen.
    #
    # Der Drive-Step soll nur dann laufen,
    # wenn wirklich alle fünf fertigen
    # Videos existieren.

    if (
        len(successful)
        != 5
    ):

        print("")
        print(
            "FEHLERLISTE:"
        )

        for item in failed:

            print(
                item["video"]
            )

            print(
                item["error"]
            )

        raise RuntimeError(
            "Nicht alle 5 Videos "
            "konnten verarbeitet werden."
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
        "PROCESSING V2 ERFOLGREICH"
    )

    print(
        "5/5 TikTok-Videos erstellt."
    )

    print(
        "@Clipcrip2 auf jedem Video."
    )

    print(
        "========================================"
    )


if __name__ == "__main__":

    main()