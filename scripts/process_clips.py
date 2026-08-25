import os
import glob
import subprocess
import sys
import json
import re
import shutil

INPUT_DIR = "downloaded_clips"
OUTPUT_DIR = "tiktok_ready"

MAX_OUTPUTS = 5


def run(command):

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


def clean_output_directory():

    os.makedirs(
        OUTPUT_DIR,
        exist_ok=True
    )

    for filename in os.listdir(
        OUTPUT_DIR
    ):

        path = os.path.join(
            OUTPUT_DIR,
            filename
        )

        if os.path.isfile(path):
            os.remove(path)

        elif os.path.isdir(path):
            shutil.rmtree(path)


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


def detect_people(video):

    try:

        from ultralytics import YOLO
        import cv2

    except ImportError:

        print(
            "YOLO/OpenCV nicht verfügbar."
        )

        return 0.5, 0.0

    print(
        "Analysiere Personen..."
    )

    model = YOLO(
        "yolo11n.pt"
    )

    cap = cv2.VideoCapture(
        video
    )

    if not cap.isOpened():

        print(
            "Video konnte nicht geöffnet werden."
        )

        return 0.5, 0.0

    total_frames = int(
        cap.get(
            cv2.CAP_PROP_FRAME_COUNT
        )
    )

    fps = cap.get(
        cv2.CAP_PROP_FPS
    )

    if fps <= 0:
        fps = 30

    duration = (
        total_frames / fps
    )

    positions = []
    weights = []

    # Mehrere Stellen im Video untersuchen.
    sample_count = 12

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

        results = model(
            frame,
            verbose=False
        )

        frame_width = frame.shape[1]
        frame_height = frame.shape[0]

        for result in results:

            if result.boxes is None:
                continue

            for box in result.boxes:

                class_id = int(
                    box.cls[0].item()
                )

                # Person
                if class_id != 0:
                    continue

                confidence = float(
                    box.conf[0].item()
                )

                if confidence < 0.45:
                    continue

                x1, y1, x2, y2 = (
                    box.xyxy[0].tolist()
                )

                person_width = (
                    x2 - x1
                )

                person_height = (
                    y2 - y1
                )

                center_x = (
                    x1 + x2
                ) / 2

                normalized_x = (
                    center_x
                    / frame_width
                )

                normalized_area = (
                    person_width
                    * person_height
                ) / (
                    frame_width
                    * frame_height
                )

                # Größere Personen bekommen
                # mehr Gewicht.
                weight = max(
                    normalized_area,
                    0.01
                )

                positions.append(
                    normalized_x
                )

                weights.append(
                    weight
                )

    cap.release()

    if not positions:

        print(
            "Keine Person erkannt."
        )

        return 0.5, 0.0

    weighted_position = (
        sum(
            p * w
            for p, w in zip(
                positions,
                weights
            )
        )
        / sum(weights)
    )

    confidence_score = min(
        1.0,
        len(positions) / 12
    )

    position = max(
        0.15,
        min(
            0.85,
            weighted_position
        )
    )

    print(
        f"Personenposition: "
        f"{position:.3f}"
    )

    print(
        f"Personen-Erkennungswert: "
        f"{confidence_score:.2f}"
    )

    return (
        position,
        confidence_score
    )


def create_word_timestamps(video):

    print(
        f"Whisper analysiert: {video}"
    )

    base_name = os.path.splitext(
        os.path.basename(video)
    )[0]

    run([
        sys.executable,
        "-m",
        "whisper",
        video,
        "--model",
        "small",
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

    json_file = os.path.join(
        OUTPUT_DIR,
        f"{base_name}.json"
    )

    if not os.path.exists(
        json_file
    ):

        raise FileNotFoundError(
            f"Whisper JSON fehlt: "
            f"{json_file}"
        )

    return json_file


def clean_text(text):

    text = text.strip()

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text


def create_ass(
    json_file,
    ass_file
):

    with open(
        json_file,
        "r",
        encoding="utf-8"
    ) as file:

        data = json.load(file)

    words = []

    for segment in data.get(
        "segments",
        []
    ):

        segment_words = (
            segment.get(
                "words",
                []
            )
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
                    word["start"]
                )

                end = float(
                    word["end"]
                )

            except (
                KeyError,
                TypeError,
                ValueError
            ):

                continue

            if end <= start:
                continue

            words.append({
                "word": text,
                "start": start,
                "end": end
            })

    if not words:

        raise RuntimeError(
            "Whisper hat keine brauchbaren "
            "Wörter mit Zeitstempeln geliefert."
        )

    def ass_time(seconds):

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
            ) * 100
        )

        return (
            f"{hours}:"
            f"{minutes:02d}:"
            f"{secs:02d}."
            f"{centiseconds:02d}"
        )

    lines = [

        "[Script Info]",

        "ScriptType: v4.00+",

        "PlayResX: 1080",

        "PlayResY: 1920",

        "",

        "[V4+ Styles]",

        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",

        "Style: TikTok,Arial,62,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,5,2,2,80,80,260,1",

        "",

        "[Events]",

        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"
    ]

    chunk = []

    for word in words:

        chunk.append(
            word
        )

        punctuation = (
            ".",
            "!",
            "?",
            ",",
            ";",
            ":"
        )

        finish = (
            len(chunk) >= 4
            or word["word"].endswith(
                punctuation
            )
        )

        if finish:

            start = (
                chunk[0]["start"]
            )

            end = (
                chunk[-1]["end"]
            )

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

        start = (
            chunk[0]["start"]
        )

        end = (
            chunk[-1]["end"]
        )

        caption = " ".join(
            item["word"]
            for item in chunk
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


def create_video(
    video,
    ass_file,
    output,
    crop_position
):

    # 16:9 Ausgangsmaterial:
    #
    # 1920x1080
    #
    # Für echtes 9:16:
    #
    # 608x1080
    #
    # Danach auf 1080x1920 skalieren.

    crop_width = 608
    crop_height = 1080

    source_width = 1920

    max_x = (
        source_width
        - crop_width
    )

    # Position des relevanten Bereichs.
    center_x = (
        source_width
        * crop_position
    )

    crop_x = int(
        center_x
        - crop_width / 2
    )

    crop_x = max(
        0,
        min(
            max_x,
            crop_x
        )
    )

    ass_path = ass_file.replace(
        "\\",
        "/"
    )

    video_filter = (
        "scale=1920:1080,"
        f"crop={crop_width}:{crop_height}:{crop_x}:0,"
        "scale=1080:1920,"
        "setsar=1,"
        f"ass='{ass_path}'"
    )

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


def process_video(
    video,
    number
):

    base_name = os.path.splitext(
        os.path.basename(video)
    )[0]

    output = os.path.join(
        OUTPUT_DIR,
        f"{number:02d}_jussef_tiktok.mp4"
    )

    try:

        # --------------------------
        # WHISPER
        # --------------------------

        json_file = (
            create_word_timestamps(
                video
            )
        )

        ass_file = os.path.join(
            OUTPUT_DIR,
            f"{base_name}.ass"
        )

        create_ass(
            json_file,
            ass_file
        )

        # --------------------------
        # PERSONEN
        # --------------------------

        crop_position, person_score = (
            detect_people(
                video
            )
        )

        # --------------------------
        # VIDEO
        # --------------------------

        create_video(
            video,
            ass_file,
            output,
            crop_position
        )

        if not os.path.exists(
            output
        ):

            raise RuntimeError(
                "FFmpeg hat keine "
                "Ausgabedatei erzeugt."
            )

        print(
            f"FERTIG: {output}"
        )

        return True

    except Exception as error:

        print("")
        print(
            "================================"
        )
        print(
            "CLIP ÜBERSPRUNGEN"
        )
        print(
            "================================"
        )

        print(
            f"Video: {video}"
        )

        print(
            f"Grund: {error}"
        )

        print(
            "================================"
        )

        # Falls ein halbfertiges Outputfile existiert,
        # entfernen.
        if os.path.exists(
            output
        ):

            try:
                os.remove(output)
            except OSError:
                pass

        return False


def main():

    # Alte Ergebnisse entfernen,
    # damit garantiert keine alten Videos
    # im Artifact landen.
    clean_output_directory()

    videos = find_videos()

    if not videos:

        raise FileNotFoundError(
            "Keine Videos in downloaded_clips gefunden."
        )

    print(
        "================================"
    )

    print(
        f"{len(videos)} Kandidaten gefunden."
    )

    print(
        f"Maximal {MAX_OUTPUTS} fertige Videos."
    )

    print(
        "================================"
    )

    successful = 0
    failed = 0

    # Wir testen Kandidaten nacheinander,
    # bis wir 5 fertige Videos haben.
    for video in videos:

        if successful >= MAX_OUTPUTS:
            break

        number = successful + 1

        print("")
        print(
            "================================"
        )

        print(
            f"KANDIDAT "
            f"{number}/{MAX_OUTPUTS}"
        )

        print(
            f"Datei: {video}"
        )

        print(
            "================================"
        )

        success = process_video(
            video,
            number
        )

        if success:

            successful += 1

        else:

            failed += 1

    print("")
    print(
        "================================"
    )

    print(
        "BEARBEITUNG ABGESCHLOSSEN"
    )

    print(
        f"Fertig: {successful}"
    )

    print(
        f"Übersprungen: {failed}"
    )

    print(
        "================================"
    )

    if successful == 0:

        raise RuntimeError(
            "Keiner der Kandidaten konnte "
            "erfolgreich verarbeitet werden."
        )

    if successful < MAX_OUTPUTS:

        print("")
        print(
            "WARNUNG:"
        )

        print(
            f"Nur {successful} von "
            f"{MAX_OUTPUTS} Videos konnten "
            "erstellt werden."
        )


if __name__ == "__main__":
    main()
