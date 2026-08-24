import os
import glob
import subprocess
import sys
import json
import re

INPUT_DIR = "downloaded_clips"
OUTPUT_DIR = "tiktok_ready"


def run(command):
    print("RUN:", " ".join(command))

    result = subprocess.run(command)

    if result.returncode != 0:
        raise RuntimeError(
            "Befehl fehlgeschlagen: " + " ".join(command)
        )


def find_videos():
    videos = []

    for extension in ("mp4", "webm", "mkv", "mov"):
        videos.extend(
            glob.glob(
                os.path.join(INPUT_DIR, f"*.{extension}")
            )
        )

    return sorted(videos)


def detect_people(video):
    try:
        from ultralytics import YOLO
        import cv2
    except ImportError:
        return 0.5

    print("Analysiere Personen im Video...")

    model = YOLO("yolo11n.pt")

    cap = cv2.VideoCapture(video)

    if not cap.isOpened():
        return 0.5

    total_frames = int(
        cap.get(cv2.CAP_PROP_FRAME_COUNT)
    )

    fps = cap.get(cv2.CAP_PROP_FPS)

    if fps <= 0:
        fps = 30

    duration = total_frames / fps

    positions = []
    weights = []

    for i in range(8):

        timestamp = duration * (i + 0.5) / 8

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

                if confidence < 0.45:
                    continue

                x1, y1, x2, y2 = (
                    box.xyxy[0].tolist()
                )

                center_x = (
                    x1 + x2
                ) / 2

                width = x2 - x1
                height = y2 - y1

                area = width * height

                normalized_x = (
                    center_x / frame_width
                )

                positions.append(
                    normalized_x
                )

                weights.append(
                    max(area, 1)
                )

    cap.release()

    if not positions:
        return 0.5

    weighted_position = sum(
        p * w
        for p, w in zip(
            positions,
            weights
        )
    ) / sum(weights)

    return max(
        0.20,
        min(
            0.80,
            weighted_position
        )
    )


def create_word_timestamps(video):

    print("Whisper analysiert Sprache...")

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
        OUTPUT_DIR,
    ])

    json_file = os.path.join(
        OUTPUT_DIR,
        f"{base_name}.json"
    )

    if not os.path.exists(json_file):
        raise FileNotFoundError(
            f"Whisper JSON fehlt: {json_file}"
        )

    return json_file


def clean_text(text):

    text = text.strip()

    # Überflüssige Leerzeichen
    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text


def create_ass(json_file, ass_file):

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

        for word in segment.get(
            "words",
            []
        ):

            text = clean_text(
                word.get("word", "")
            )

            if not text:
                continue

            words.append({
                "word": text,
                "start": float(
                    word["start"]
                ),
                "end": float(
                    word["end"]
                )
            })

    if not words:
        raise RuntimeError(
            "Whisper hat keine Wörter mit Zeitstempeln geliefert."
        )

    # ASS-Zeitformat
    def ass_time(seconds):

        hours = int(seconds // 3600)
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

    # ASS-Datei
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

    # 3-5 Wörter pro Caption
    chunk = []

    for word in words:

        chunk.append(word)

        # Caption beenden:
        # spätestens nach 4 Wörtern
        # oder bei Satzzeichen
        punctuation = (
            ".",
            "!",
            "?",
            ","
        )

        text = word["word"]

        should_finish = (
            len(chunk) >= 4
            or text.endswith(punctuation)
        )

        if should_finish:

            start = chunk[0]["start"]
            end = chunk[-1]["end"]

            caption = " ".join(
                w["word"]
                for w in chunk
            )

            caption = caption.replace(
                "{",
                "("
            ).replace(
                "}",
                ")"
            )

            lines.append(
                "Dialogue: 0,"
                f"{ass_time(start)},"
                f"{ass_time(end)},"
                f"TikTok,,80,80,260,,"
                f"{caption}"
            )

            chunk = []

    if chunk:

        start = chunk[0]["start"]
        end = chunk[-1]["end"]

        caption = " ".join(
            w["word"]
            for w in chunk
        )

        lines.append(
            "Dialogue: 0,"
            f"{ass_time(start)},"
            f"{ass_time(end)},"
            f"TikTok,,80,80,260,,"
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

    crop_width = 608
    crop_height = 1080

    max_x = 1920 - crop_width

    crop_x = int(
        max_x * crop_position
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


def process_video(video):

    base_name = os.path.splitext(
        os.path.basename(video)
    )[0]

    output = os.path.join(
        OUTPUT_DIR,
        "01_jussef_tiktok.mp4"
    )

    json_file = create_word_timestamps(
        video
    )

    ass_file = os.path.join(
        OUTPUT_DIR,
        f"{base_name}.ass"
    )

    create_ass(
        json_file,
        ass_file
    )

    crop_position = detect_people(
        video
    )

    print(
        f"Crop Position: {crop_position:.3f}"
    )

    create_video(
        video,
        ass_file,
        output,
        crop_position
    )

    print(
        f"FERTIG: {output}"
    )


def main():

    os.makedirs(
        OUTPUT_DIR,
        exist_ok=True
    )

    videos = find_videos()

    if not videos:
        raise FileNotFoundError(
            "Keine Videos gefunden."
        )

    # Wieder nur EIN Testclip
    process_video(
        videos[0]
    )

    print(
        "TESTVIDEO ERFOLGREICH ERSTELLT"
    )


if __name__ == "__main__":
    main()
