import os
import glob
import subprocess
import sys
import json
import re

import cv2
import numpy as np


INPUT_DIR = "selected_clips"
OUTPUT_DIR = "tiktok_ready"

MAX_VIDEOS = 5

WHISPER_MODEL = "small"

OUTPUT_PREFIX = "jussef_tiktok"


# =========================================================
# COMMAND
# =========================================================

def run(command):

    print("RUN:", " ".join(command))

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

    return sorted(videos)


# =========================================================
# VIDEO INFO
# =========================================================

def get_video_info(video):

    cap = cv2.VideoCapture(
        video
    )

    if not cap.isOpened():
        return None

    width = int(
        cap.get(
            cv2.CAP_PROP_FRAME_WIDTH
        )
    )

    height = int(
        cap.get(
            cv2.CAP_PROP_FRAME_HEIGHT
        )
    )

    frames = int(
        cap.get(
            cv2.CAP_PROP_FRAME_COUNT
        )
    )

    fps = float(
        cap.get(
            cv2.CAP_PROP_FPS
        )
    )

    cap.release()

    if fps <= 0:
        fps = 30

    if width <= 0 or height <= 0:
        return None

    duration = (
        frames / fps
        if frames > 0
        else 0
    )

    return {
        "width": width,
        "height": height,
        "frames": frames,
        "fps": fps,
        "duration": duration
    }


# =========================================================
# PERSON / FACE DETECTION
# =========================================================

def detect_people(video):

    print(
        "Analysiere Person/Gesicht..."
    )

    try:

        from ultralytics import YOLO

        model = YOLO(
            "yolo11n.pt"
        )

    except Exception as error:

        print(
            "YOLO nicht verfügbar:"
            f" {error}"
        )

        return 0.5

    info = get_video_info(
        video
    )

    if info is None:
        return 0.5

    cap = cv2.VideoCapture(
        video
    )

    if not cap.isOpened():
        return 0.5

    width = info["width"]
    height = info["height"]
    duration = info["duration"]

    positions = []
    weights = []

    # -----------------------------------------------------
    # Face detector als zusätzliche Hilfe
    # -----------------------------------------------------

    face_detector = None

    try:

        face_detector = cv2.CascadeClassifier(
            cv2.data.haarcascades
            + "haarcascade_frontalface_default.xml"
        )

    except Exception:

        face_detector = None

    # -----------------------------------------------------
    # Mehrere Zeitpunkte analysieren
    # -----------------------------------------------------

    sample_count = 16

    for i in range(
        sample_count
    ):

        timestamp = (
            duration
            * (i + 0.5)
            / sample_count
        )

        cap.set(
            cv2.CAP_PROP_POS_MSEC,
            timestamp * 1000
        )

        success, frame = cap.read()

        if not success:
            continue

        frame_height, frame_width = (
            frame.shape[:2]
        )

        # -------------------------------------------------
        # ZUERST Gesicht suchen
        # -------------------------------------------------

        face_found = False

        if (
            face_detector is not None
            and not face_detector.empty()
        ):

            try:

                gray = cv2.cvtColor(
                    frame,
                    cv2.COLOR_BGR2GRAY
                )

                faces = face_detector.detectMultiScale(
                    gray,
                    scaleFactor=1.1,
                    minNeighbors=5,
                    minSize=(30, 30)
                )

                if len(faces) > 0:

                    face = max(
                        faces,
                        key=lambda box:
                        box[2] * box[3]
                    )

                    x, y, w, h = face

                    center_x = (
                        x + w / 2
                    )

                    area = (
                        w * h
                    )

                    if area > 0:

                        positions.append(
                            center_x
                            / frame_width
                        )

                        # Gesicht besonders stark gewichten
                        weights.append(
                            area * 5
                        )

                        face_found = True

            except Exception:
                pass

        if face_found:
            continue

        # -------------------------------------------------
        # FALLBACK: GANZE PERSON
        # -------------------------------------------------

        try:

            results = model(
                frame,
                verbose=False
            )

            best_person = None

            for result in results:

                if result.boxes is None:
                    continue

                for box in result.boxes:

                    class_id = int(
                        box.cls[0].item()
                    )

                    # COCO:
                    # 0 = person
                    if class_id != 0:
                        continue

                    confidence = float(
                        box.conf[0].item()
                    )

                    if confidence < 0.40:
                        continue

                    x1, y1, x2, y2 = (
                        box.xyxy[0].tolist()
                    )

                    box_width = (
                        x2 - x1
                    )

                    box_height = (
                        y2 - y1
                    )

                    area = (
                        box_width
                        * box_height
                    )

                    if (
                        best_person is None
                        or area
                        > best_person[0]
                    ):

                        best_person = (
                            area,
                            (x1 + x2) / 2
                        )

            if best_person is not None:

                area, center_x = (
                    best_person
                )

                positions.append(
                    center_x
                    / frame_width
                )

                weights.append(
                    max(
                        area,
                        1
                    )
                )

        except Exception as error:

            print(
                "Personenerkennung "
                f"fehlgeschlagen: {error}"
            )

    cap.release()

    # -----------------------------------------------------
    # Keine Person gefunden
    # -----------------------------------------------------

    if not positions:

        print(
            "Keine Person gefunden."
        )

        print(
            "Verwende Bildmitte."
        )

        return 0.5

    # -----------------------------------------------------
    # Gewichtete Position
    # -----------------------------------------------------

    weighted_position = (
        sum(
            p * w
            for p, w in zip(
                positions,
                weights
            )
        )
        /
        sum(weights)
    )

    position = max(
        0.05,
        min(
            0.95,
            weighted_position
        )
    )

    print(
        "Ermittelte "
        "Personenposition: "
        f"{position:.3f}"
    )

    return position


# =========================================================
# WHISPER
# =========================================================

def create_word_timestamps(
    video
):

    print(
        f"Whisper analysiert: "
        f"{video}"
    )

    base_name = os.path.splitext(
        os.path.basename(video)
    )[0]

    json_file = os.path.join(
        OUTPUT_DIR,
        f"{base_name}.json"
    )

    # Alte Whisper-Datei entfernen
    if os.path.exists(
        json_file
    ):

        os.remove(
            json_file
        )

    run([
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
        OUTPUT_DIR
    ])

    if not os.path.exists(
        json_file
    ):

        print(
            "Whisper hat keine "
            "JSON-Datei erzeugt."
        )

        return None

    return json_file


# =========================================================
# TEXT CLEANING
# =========================================================

def clean_text(text):

    text = text.strip()

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text


# =========================================================
# ASS TIME
# =========================================================

def ass_time(seconds):

    seconds = max(
        0,
        float(seconds)
    )

    hours = int(
        seconds // 3600
    )

    minutes = int(
        (seconds % 3600)
        // 60
    )

    secs = int(
        seconds % 60
    )

    centiseconds = int(
        (
            seconds
            - int(seconds)
        ) * 100
    )

    return (
        f"{hours}:"
        f"{minutes:02d}:"
        f"{secs:02d}."
        f"{centiseconds:02d}"
    )


# =========================================================
# CREATE ASS
# =========================================================

def create_ass(
    json_file,
    ass_file
):

    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        "PlayResX: 1080",
        "PlayResY: 1920",
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
            "Style: TikTok,Arial,62,"
            "&H00FFFFFF,&H00FFFFFF,"
            "&H00000000,&H80000000,"
            "1,0,0,0,100,100,0,0,"
            "1,5,2,2,80,80,260,1"
        ),
        "",
        "[Events]",
        (
            "Format: Layer, Start, End, "
            "Style, Name, MarginL, MarginR, "
            "MarginV, Effect, Text"
        )
    ]

    # -----------------------------------------------------
    # Kein Whisper
    # -----------------------------------------------------

    if json_file is None:

        print(
            "Keine Untertitel."
        )

        with open(
            ass_file,
            "w",
            encoding="utf-8"
        ) as file:

            file.write(
                "\n".join(lines)
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
            "Whisper JSON konnte "
            f"nicht gelesen werden: "
            f"{error}"
        )

        with open(
            ass_file,
            "w",
            encoding="utf-8"
        ) as file:

            file.write(
                "\n".join(lines)
            )

        return False

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

            if (
                "start" not in word
                or "end" not in word
            ):
                continue

            start = float(
                word["start"]
            )

            end = float(
                word["end"]
            )

            if end <= start:
                continue

            words.append({
                "word": text,
                "start": start,
                "end": end
            })

    # -----------------------------------------------------
    # WICHTIG:
    # Kein Timestamp = kein Fehler
    # -----------------------------------------------------

    if not words:

        print(
            "Keine brauchbaren "
            "Word-Timestamps."
        )

        print(
            "Clip wird OHNE "
            "Untertitel verarbeitet."
        )

        with open(
            ass_file,
            "w",
            encoding="utf-8"
        ) as file:

            file.write(
                "\n".join(lines)
            )

        return False

    # -----------------------------------------------------
    # Untertitel in kurze Gruppen teilen
    # -----------------------------------------------------

    chunk = []

    for word in words:

        chunk.append(
            word
        )

        text = word["word"]

        punctuation = (
            ".",
            "!",
            "?",
            ",",
            ":",
            ";"
        )

        finish = False

        if len(chunk) >= 4:
            finish = True

        if text.endswith(
            punctuation
        ):
            finish = True

        # zu lange Untertitel vermeiden
        if len(
            " ".join(
                item["word"]
                for item in chunk
            )
        ) > 34:

            finish = True

        if not finish:
            continue

        start = chunk[0][
            "start"
        ]

        end = chunk[-1][
            "end"
        ]

        caption = " ".join(
            item["word"]
            for item in chunk
        )

        caption = (
            caption
            .replace(
                "{",
                "("
            )
            .replace(
                "}",
                ")"
            )
        )

        lines.append(
            "Dialogue: 0,"
            f"{ass_time(start)},"
            f"{ass_time(end)},"
            "TikTok,,80,80,260,,"
            f"{caption}"
        )

        chunk = []

    if chunk:

        start = chunk[0][
            "start"
        ]

        end = chunk[-1][
            "end"
        ]

        caption = " ".join(
            item["word"]
            for item in chunk
        )

        caption = (
            caption
            .replace(
                "{",
                "("
            )
            .replace(
                "}",
                ")"
            )
        )

        lines.append(
            "Dialogue: 0,"
            f"{ass_time(start)},"
            f"{ass_time(end)},"
            "TikTok,,80,80,260,,"
            f"{caption}"
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
        f"{len(words)} Wörter "
        "für Untertitel verarbeitet."
    )

    return True


# =========================================================
# CREATE VIDEO
# =========================================================

def create_video(
    video,
    ass_file,
    output,
    crop_position
):

    info = get_video_info(
        video
    )

    if info is None:

        raise RuntimeError(
            "Videoauflösung konnte "
            "nicht gelesen werden."
        )

    width = info[
        "width"
    ]

    height = info[
        "height"
    ]

    # -----------------------------------------------------
    # Zielverhältnis 9:16
    # -----------------------------------------------------

    target_ratio = 9 / 16

    current_ratio = (
        width / height
    )

    # -----------------------------------------------------
    # Bei Landscape:
    # vertikal aus der Breite ausschneiden
    # -----------------------------------------------------

    if current_ratio > target_ratio:

        crop_width = int(
            height
            * target_ratio
        )

        crop_height = height

    else:

        # Falls das Original schon
        # vertikal/nahezu vertikal ist
        crop_width = width
        crop_height = int(
            width
            / target_ratio
        )

        crop_height = min(
            crop_height,
            height
        )

    # -----------------------------------------------------
    # ENTSCHEIDENDER FIX:
    #
    # Position = Mittelpunkt der Person.
    #
    # Deshalb:
    #
    # crop_x =
    # Personenmittelpunkt
    # - halbe Cropbreite
    #
    # NICHT:
    # max_x * position
    #
    # -----------------------------------------------------

    if crop_width < width:

        person_center_x = (
            width
            * crop_position
        )

        crop_x = int(
            person_center_x
            - crop_width / 2
        )

        max_x = (
            width
            - crop_width
        )

        crop_x = max(
            0,
            min(
                max_x,
                crop_x
            )
        )

    else:

        crop_x = 0

    if crop_height < height:

        crop_y = int(
            (
                height
                - crop_height
            ) / 2
        )

    else:

        crop_y = 0

    # -----------------------------------------------------
    # ASS-Pfad
    # -----------------------------------------------------

    ass_path = (
        os.path.abspath(
            ass_file
        )
        .replace(
            "\\",
            "/"
        )
        .replace(
            ":",
            "\\:"
        )
    )

    # -----------------------------------------------------
    # Filter
    # -----------------------------------------------------

    video_filter = (
        f"crop="
        f"{crop_width}:"
        f"{crop_height}:"
        f"{crop_x}:"
        f"{crop_y},"
        "scale=1080:1920,"
        "setsar=1,"
        f"ass='{ass_path}'"
    )

    print(
        "Crop:"
        f" width={crop_width}"
        f" height={crop_height}"
        f" x={crop_x}"
        f" y={crop_y}"
    )

    # -----------------------------------------------------
    # FFmpeg
    # -----------------------------------------------------

    run([
        "ffmpeg",
        "-y",
        "-i",
        video,

        "-vf",
        video_filter,

        "-map",
        "0:v:0",

        "-map",
        "0:a?",

        "-c:v",
        "libx264",

        "-preset",
        "fast",

        "-crf",
        "20",

        "-c:a",
        "aac",

        "-b:a",
        "192k",

        "-movflags",
        "+faststart",

        output
    ])


# =========================================================
# PROCESS ONE VIDEO
# =========================================================

def process_video(
    video,
    number
):

    base_name = os.path.splitext(
        os.path.basename(video)
    )[0]

    output = os.path.join(
        OUTPUT_DIR,
        f"{number:02d}_{OUTPUT_PREFIX}.mp4"
    )

    ass_file = os.path.join(
        OUTPUT_DIR,
        f"{base_name}.ass"
    )

    json_file = os.path.join(
        OUTPUT_DIR,
        f"{base_name}.json"
    )

    # -----------------------------------------------------
    # ALTE DATEIEN DIESES CLIPS LÖSCHEN
    # -----------------------------------------------------

    for old_file in (
        output,
        ass_file,
        json_file
    ):

        if os.path.exists(
            old_file
        ):

            os.remove(
                old_file
            )

    # -----------------------------------------------------
    # Whisper
    # -----------------------------------------------------

    whisper_json = (
        create_word_timestamps(
            video
        )
    )

    # -----------------------------------------------------
    # ASS
    # -----------------------------------------------------

    create_ass(
        whisper_json,
        ass_file
    )

    # -----------------------------------------------------
    # Person erkennen
    # -----------------------------------------------------

    crop_position = detect_people(
        video
    )

    print(
        "Crop Position: "
        f"{crop_position:.3f}"
    )

    # -----------------------------------------------------
    # Video erzeugen
    # -----------------------------------------------------

    create_video(
        video,
        ass_file,
        output,
        crop_position
    )

    # -----------------------------------------------------
    # Kontrolle
    # -----------------------------------------------------

    if not os.path.exists(
        output
    ):

        raise RuntimeError(
            "FFmpeg hat keine "
            "Ausgabedatei erzeugt."
        )

    size = os.path.getsize(
        output
    )

    if size < 100_000:

        raise RuntimeError(
            "Ausgabedatei ist "
            "ungewöhnlich klein."
        )

    print(
        f"FERTIG: {output}"
    )


# =========================================================
# CLEAN OUTPUT DIRECTORY
# =========================================================

def clean_output_directory():

    os.makedirs(
        OUTPUT_DIR,
        exist_ok=True
    )

    patterns = [
        "*.mp4",
        "*.ass",
        "*.json",
    ]

    for pattern in patterns:

        for file in glob.glob(
            os.path.join(
                OUTPUT_DIR,
                pattern
            )
        ):

            try:

                os.remove(
                    file
                )

            except Exception:

                pass


# =========================================================
# MAIN
# =========================================================

def main():

    print("")
    print(
        "================================"
    )
    print(
        "TIKTOK VIDEO PROCESSOR"
    )
    print(
        "================================"
    )

    os.makedirs(
        OUTPUT_DIR,
        exist_ok=True
    )

    videos = find_videos()

    if not videos:

        raise FileNotFoundError(
            "Keine ausgewählten Videos "
            "in selected_clips gefunden."
        )

    # -----------------------------------------------------
    # Nur maximal 5 ausgewählte Clips
    # -----------------------------------------------------

    videos = videos[
        :MAX_VIDEOS
    ]

    print(
        f"{len(videos)} ausgewählte "
        "Clips gefunden."
    )

    # -----------------------------------------------------
    # GANZ WICHTIG:
    # alte Ergebnisse löschen
    #
    # Dadurch können alte Videos,
    # alte ASS-Dateien und alte
    # Whisper-JSONs nicht versehentlich
    # wieder in den neuen Workflow
    # hineinlaufen.
    # -----------------------------------------------------

    clean_output_directory()

    successful = 0

    for number, video in enumerate(
        videos,
        start=1
    ):

        print("")
        print(
            "================================"
        )

        print(
            f"CLIP {number}/{len(videos)}"
        )

        print(
            os.path.basename(
                video
            )
        )

        print(
            "================================"
        )

        try:

            process_video(
                video,
                number
            )

            successful += 1

        except Exception as error:

            print("")
            print(
                "WARNUNG:"
            )

            print(
                f"Clip konnte nicht "
                f"verarbeitet werden:"
            )

            print(
                str(error)
            )

            print(
                "Dieser Clip wird "
                "übersprungen."
            )

    print("")
    print(
        "================================"
    )

    print(
        f"ERFOLG: "
        f"{successful}/{len(videos)}"
    )

    print(
        "================================"
    )

    if successful == 0:

        raise RuntimeError(
            "Kein Clip konnte "
            "erfolgreich verarbeitet werden."
        )


if __name__ == "__main__":

    main()