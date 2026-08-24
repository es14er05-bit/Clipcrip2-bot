import os
import glob
import subprocess
import sys
import json

INPUT_DIR = "downloaded_clips"
OUTPUT_DIR = "tiktok_ready"
ANALYSIS_DIR = "analysis"


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
    """
    Erkennt Personen mit YOLO in mehreren Frames.
    Gibt eine optimale X-Position für den 9:16-Crop zurück.
    """

    try:
        from ultralytics import YOLO
        import cv2
    except ImportError:
        print("YOLO/OpenCV nicht verfügbar.")
        return 0.5

    print("Lade Personen-Erkennung...")

    model = YOLO("yolo11n.pt")

    cap = cv2.VideoCapture(video)

    if not cap.isOpened():
        print("Video konnte nicht geöffnet werden.")
        return 0.5

    total_frames = int(
        cap.get(cv2.CAP_PROP_FRAME_COUNT)
    )

    fps = cap.get(cv2.CAP_PROP_FPS)

    if fps <= 0:
        fps = 30

    duration = total_frames / fps

    # Maximal 8 Analysepunkte
    sample_times = []

    for i in range(8):
        sample_times.append(
            duration * (i + 0.5) / 8
        )

    centers = []
    areas = []

    for time_position in sample_times:

        cap.set(
            cv2.CAP_PROP_POS_MSEC,
            time_position * 1000
        )

        success, frame = cap.read()

        if not success:
            continue

        results = model(
            frame,
            verbose=False
        )

        for result in results:

            if result.boxes is None:
                continue

            for box in result.boxes:

                class_id = int(
                    box.cls[0].item()
                )

                # COCO class 0 = person
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
                    (x1 + x2) / 2
                )

                width = (
                    x2 - x1
                )

                height = (
                    y2 - y1
                )

                area = width * height

                frame_width = frame.shape[1]

                normalized_x = (
                    center_x / frame_width
                )

                centers.append(
                    normalized_x
                )

                areas.append(area)

    cap.release()

    if not centers:
        print(
            "Keine Person zuverlässig erkannt."
        )
        print(
            "Verwende mittleren Crop."
        )
        return 0.5

    # Größere Personen bekommen mehr Gewicht.
    weighted_x = 0
    total_weight = 0

    for x, area in zip(centers, areas):

        weight = max(
            area,
            1
        )

        weighted_x += x * weight
        total_weight += weight

    position = (
        weighted_x / total_weight
    )

    # Sicherheitsbereich
    position = max(
        0.20,
        min(0.80, position)
    )

    print(
        f"Ermittelte Personenposition: "
        f"{position:.3f}"
    )

    return position


def create_subtitles(video):

    print(
        f"Erstelle deutsche Untertitel für {video}"
    )

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
        "--output_format",
        "srt",
        "--output_dir",
        OUTPUT_DIR,
    ])


def create_video(
    video,
    subtitle_file,
    output,
    crop_position
):

    # Original 16:9:
    # 1920x1080
    #
    # Ziel:
    # 1080x1920
    #
    # Wir skalieren zuerst auf 1920x1080
    # und verschieben anschließend den
    # vertikalen Ausschnitt abhängig von
    # der erkannten Person.

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

    print(
        f"Crop X: {crop_x}"
    )

    # Untertitel werden nach dem Crop
    # auf das 1080x1920 Video gelegt.

    subtitle_path = subtitle_file.replace(
        "\\",
        "/"
    )

    filter_complex = (
        f"scale=1920:1080,"
        f"crop={crop_width}:{crop_height}:{crop_x}:0,"
        f"scale=1080:1920,"
        f"setsar=1,"
        f"subtitles='{subtitle_path}':"
        "force_style='"
        "FontName=Arial,"
        "FontSize=20,"
        "Bold=1,"
        "PrimaryColour=&HFFFFFF,"
        "OutlineColour=&H000000,"
        "Outline=4,"
        "Shadow=1,"
        "Alignment=2,"
        "MarginV=220"
        "'"
    )

    run([
        "ffmpeg",
        "-y",
        "-i",
        video,
        "-vf",
        filter_complex,
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
    ])


def process_video(video, number):

    filename = os.path.splitext(
        os.path.basename(video)
    )[0]

    subtitle_file = os.path.join(
        OUTPUT_DIR,
        f"{filename}.srt"
    )

    output = os.path.join(
        OUTPUT_DIR,
        f"{number:02d}_jussef_tiktok.mp4"
    )

    print("")
    print("==============================")
    print(
        f"VIDEO {number}: {video}"
    )
    print("==============================")

    # 1. Personen erkennen
    crop_position = detect_people(video)

    # 2. Untertitel erzeugen
    create_subtitles(video)

    if not os.path.exists(
        subtitle_file
    ):
        raise FileNotFoundError(
            f"SRT nicht gefunden: "
            f"{subtitle_file}"
        )

    # 3. 9:16 + Captions
    create_video(
        video,
        subtitle_file,
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

    os.makedirs(
        ANALYSIS_DIR,
        exist_ok=True
    )

    videos = find_videos()

    if not videos:
        raise FileNotFoundError(
            "Keine Videos in downloaded_clips gefunden."
        )

    print(
        f"{len(videos)} Videos gefunden."
    )

    # Für den ersten Test NUR EIN Video.
    test_videos = videos[:1]

    for number, video in enumerate(
        test_videos,
        start=1
    ):
        process_video(
            video,
            number
        )

    print("")
    print("==============================")
    print("TESTVIDEO FERTIG")
    print("==============================")


if __name__ == "__main__":
    main()
