import os
import glob
import subprocess
import sys
import json
import re
import shutil

INPUT_DIR = "downloaded_clips"
OUTPUT_DIR = "tiktok_ready"

MAX_CLIPS = 5


def run(command):
    print("RUN:", " ".join(command))

    result = subprocess.run(command)

    if result.returncode != 0:
        raise RuntimeError(
            "Befehl fehlgeschlagen: "
            + " ".join(command)
        )


def find_videos():
    videos = []

    for extension in (
        "mp4",
        "webm",
        "mkv",
        "mov",
    ):
        videos.extend(
            glob.glob(
                os.path.join(
                    INPUT_DIR,
                    f"*.{extension}",
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
        return 0.5

    print(
        "Analysiere Personen..."
    )

    model = YOLO("yolo11n.pt")

    cap = cv2.VideoCapture(video)

    if not cap.isOpened():
        return 0.5

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

    duration = total_frames / fps

    positions = []
    weights = []

    for i in range(10):

        timestamp = (
            duration * (i + 0.5) / 10
        )

        cap.set(
            cv2.CAP_PROP_POS_MSEC,
            timestamp * 1000,
        )

        success, frame = cap.read()

        if not success:
            continue

        results = model(
            frame,
            verbose=False,
        )

        frame_width = frame.shape[1]

        for result in results:

            if result.boxes is None:
                continue

            for box in result.boxes:

                class_id = int(
                    box.cls[0].item()
                )

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

                width = max(
                    1,
                    x2 - x1,
                )

                height = max(
                    1,
                    y2 - y1,
                )

                center_x = (
                    x1 + x2
                ) / 2

                area = width * height

                normalized_x = (
                    center_x / frame_width
                )

                positions.append(
                    normalized_x
                )

                # Große Personen bekommen mehr Gewicht
                weights.append(
                    area * confidence
                )

    cap.release()

    if not positions:
        print(
            "Keine Person erkannt."
        )
        return 0.5

    weighted_position = (
        sum(
            p * w
            for p, w in zip(
                positions,
                weights,
            )
        )
        / sum(weights)
    )

    position = max(
        0.15,
        min(
            0.85,
            weighted_position,
        ),
    )

    print(
        f"Personenposition: {position:.3f}"
    )

    return position


def create_word_timestamps(video):

    base_name = os.path.splitext(
        os.path.basename(video)
    )[0]

    print(
        f"Whisper analysiert: {video}"
    )

    run(
        [
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
            OUTPUT_DIR,
        ]
    )

    json_file = os.path.join(
        OUTPUT_DIR,
        f"{base_name}.json",
    )

    if not os.path.exists(json_file):
        return None

    return json_file


def clean_text(text):

    text = text.strip()

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text


def create_ass(
    json_file,
    ass_file,
):

    if not json_file:
        return False

    try:
        with open(
            json_file,
            "r",
            encoding="utf-8",
        ) as file:
            data = json.load(file)
    except Exception:
        return False

    words = []

    for segment in data.get(
        "segments",
        [],
    ):

        for word in segment.get(
            "words",
            [],
        ):

            text = clean_text(
                word.get(
                    "word",
                    "",
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
            except Exception:
                continue

            if end <= start:
                continue

            words.append(
                {
                    "word": text,
                    "start": start,
                    "end": end,
                }
            )

    if not words:
        print(
            "WARNUNG: Keine Word-Timestamps."
        )
        return False

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
            (seconds - int(seconds))
            * 100
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
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        "Style: TikTok,Arial,64,&H00FFFFFF,&H00FFFFFF,&H00000000,&H90000000,1,0,0,0,100,100,0,0,1,4,2,2,70,70,300,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]

    chunk = []

    for word in words:

        chunk.append(word)

        text = word["word"]

        finish = (
            len(chunk) >= 4
            or text.endswith(
                (".", "!", "?", ",")
            )
        )

        if finish:

            start = chunk[0]["start"]
            end = chunk[-1]["end"]

            caption = " ".join(
                x["word"]
                for x in chunk
            )

            caption = (
                caption
                .replace(
                    "{",
                    "(",
                )
                .replace(
                    "}",
                    ")",
                )
            )

            lines.append(
                "Dialogue: 0,"
                f"{ass_time(start)},"
                f"{ass_time(end)},"
                "TikTok,,70,70,300,,"
                f"{caption}"
            )

            chunk = []

    if chunk:

        start = chunk[0]["start"]
        end = chunk[-1]["end"]

        caption = " ".join(
            x["word"]
            for x in chunk
        )

        lines.append(
            "Dialogue: 0,"
            f"{ass_time(start)},"
            f"{ass_time(end)},"
            "TikTok,,70,70,300,,"
            f"{caption}"
        )

    with open(
        ass_file,
        "w",
        encoding="utf-8",
    ) as file:
        file.write(
            "\n".join(lines)
        )

    return True


def create_video(
    video,
    ass_file,
    output,
    crop_position,
):

    crop_width = 608
    crop_height = 1080

    max_x = 1920 - crop_width

    crop_x = int(
        (max_x * crop_position)
        - (crop_width / 2)
    )

    crop_x = max(
        0,
        min(
            max_x,
            crop_x,
        ),
    )

    # Falls keine Untertitel existieren:
    if ass_file:

        ass_path = ass_file.replace(
            "\\",
            "/",
        )

        video_filter = (
            "scale=1920:1080,"
            f"crop={crop_width}:{crop_height}:{crop_x}:0,"
            "scale=1080:1920,"
            "setsar=1,"
            f"ass='{ass_path}'"
        )

    else:

        video_filter = (
            "scale=1920:1080,"
            f"crop={crop_width}:{crop_height}:{crop_x}:0,"
            "scale=1080:1920,"
            "setsar=1"
        )

    run(
        [
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
            output,
        ]
    )


def process_video(
    video,
    number,
):

    base_name = os.path.splitext(
        os.path.basename(video)
    )[0]

    output = os.path.join(
        OUTPUT_DIR,
        f"{number:02d}_jussef_tiktok.mp4",
    )

    json_file = create_word_timestamps(
        video
    )

    ass_file = os.path.join(
        OUTPUT_DIR,
        f"{base_name}.ass",
    )

    subtitles_ok = create_ass(
        json_file,
        ass_file,
    )

    if not subtitles_ok:

        print(
            "Untertitel konnten nicht "
            "erstellt werden."
        )

        # Kein Absturz!
        # Video wird trotzdem erstellt.
        ass_file = None

    crop_position = detect_people(
        video
    )

    create_video(
        video,
        ass_file,
        output,
        crop_position,
    )

    print(
        f"FERTIG: {output}"
    )


def main():

    os.makedirs(
        OUTPUT_DIR,
        exist_ok=True,
    )

    videos = find_videos()

    if not videos:
        raise FileNotFoundError(
            "Keine Videos in "
            "downloaded_clips gefunden."
        )

    # Alte fertige Videos entfernen,
    # damit keine doppelten Ergebnisse bleiben.
    for file in glob.glob(
        os.path.join(
            OUTPUT_DIR,
            "*_jussef_tiktok.mp4",
        )
    ):
        try:
            os.remove(file)
        except Exception:
            pass

    print("================================")
    print(
        f"{len(videos)} Clips gefunden."
    )
    print(
        f"Bearbeite maximal {MAX_CLIPS}."
    )
    print("================================")

    successful = 0

    for video in videos[:MAX_CLIPS]:

        number = (
            successful + 1
        )

        try:

            process_video(
                video,
                number,
            )

            successful += 1

        except Exception as error:

            print("")
            print(
                "WARNUNG: Clip konnte nicht "
                "verarbeitet werden:"
            )

            print(video)
            print(error)

            print(
                "Nächster Clip wird verarbeitet."
            )

    if successful == 0:
        raise RuntimeError(
            "Keiner der Clips konnte "
            "verarbeitet werden."
        )

    print("")
    print("================================")
    print(
        f"{successful} Videos erfolgreich erstellt."
    )
    print("================================")


if __name__ == "__main__":
    main()
