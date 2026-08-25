import os
import glob
import subprocess
import sys
import json
import re
INPUT_DIR = "selected_clips"
OUTPUT_DIR = "tiktok_ready"
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
        return 0.5
    print(
        "Analysiere Person/Face..."
    )
    model = YOLO(
        "yolo11n.pt"
    )
    cap = cv2.VideoCapture(
        video
    )
    if not cap.isOpened():
        return 0.5
    total_frames = int(
        cap.get(
            cv2.CAP_PROP_FRAME_COUNT
        )
    )
    fps = float(
        cap.get(
            cv2.CAP_PROP_FPS
        )
    )
    if fps <= 0:
        fps = 30
    if total_frames <= 0:
        cap.release()
        return 0.5
    duration = (
        total_frames / fps
    )
    positions = []
    weights = []
    # Gesichtserkennung zusätzlich
    face_detector = None
    try:
        face_detector = (
            cv2.CascadeClassifier(
                cv2.data.haarcascades
                +
                "haarcascade_frontalface_default.xml"
            )
        )
    except Exception:
        face_detector = None
    for i in range(12):
        timestamp = (
            duration
            * (i + 0.5)
            / 12
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
        # -------------------------
        # Gesicht bevorzugen
        # -------------------------
        if (
            face_detector is not None
            and not face_detector.empty()
        ):
            try:
                gray = cv2.cvtColor(
                    frame,
                    cv2.COLOR_BGR2GRAY
                )
                faces = (
                    face_detector
                    .detectMultiScale(
                        gray,
                        scaleFactor=1.1,
                        minNeighbors=5,
                        minSize=(30, 30)
                    )
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
                    ) / frame_width
                    area = (
                        w * h
                    )
                    if area > 0:
                        positions.append(
                            center_x
                        )
                        weights.append(
                            area * 3
                        )
                        continue
            except Exception:
                pass
        # -------------------------
        # Fallback: Person
        # -------------------------
        try:
            results = model(
                frame,
                verbose=False
            )
            best = None
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
                    width = (
                        x2 - x1
                    )
                    height = (
                        y2 - y1
                    )
                    area = (
                        width
                        * height
                    )
                    if (
                        best is None
                        or area > best[0]
                    ):
                        best = (
                            area,
                            (x1 + x2) / 2
                        )
            if best is not None:
                area, center = best
                positions.append(
                    center
                    / frame_width
                )
                weights.append(
                    max(
                        area,
                        1
                    )
                )
        except Exception:
            pass
    cap.release()
    if not positions:
        print(
            "Keine Person gefunden. "
            "Verwende Mitte."
        )
        return 0.5
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
        0.15,
        min(
            0.85,
            weighted_position
        )
    )
    print(
        f"Ermittelte Crop-Position: "
        f"{position:.3f}"
    )
    return position
def create_word_timestamps(
    video
):
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
            words.append({
                "word": text,
                "start": float(
                    word["start"]
                ),
                "end": float(
                    word["end"]
                )
            })
    def ass_time(seconds):
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
            )
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
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        "Style: TikTok,Arial,62,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,5,2,2,80,80,260,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"
    ]
    # Keine brauchbaren Wörter:
    # leere ASS-Datei erzeugen,
    # damit der Clip trotzdem verarbeitet wird.
    if not words:
        print(
            "Keine Word-Timestamps."
        )
        with open(
            ass_file,
            "w",
            encoding="utf-8"
        ) as file:
            file.write(
                "\n".join(lines)
            )
        return
    chunk = []
    for word in words:
        chunk.append(
            word
        )
        punctuation = (
            ".",
            "!",
            "?",
            ","
        )
        should_finish = (
            len(chunk) >= 4
            or word["word"].endswith(
                punctuation
            )
        )
        if should_finish:
            start = (
                chunk[0]["start"]
            )
            end = (
                chunk[-1]["end"]
            )
            caption = " ".join(
                w["word"]
                for w in chunk
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
            w["word"]
            for w in chunk
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
def create_video(
    video,
    ass_file,
    output,
    crop_position
):
    # Wir lesen die tatsächliche
    # Auflösung des Videos.
    import cv2
    cap = cv2.VideoCapture(
        video
    )
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
    cap.release()
    if width <= 0 or height <= 0:
        width = 1920
        height = 1080
    # 9:16 Crop.
    crop_width = int(
        height * 9 / 16
    )
    crop_width = min(
        crop_width,
        width
    )
    max_x = (
        width
        - crop_width
    )
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
    ass_path = (
        ass_file
        .replace(
            "\\",
            "/"
        )
        .replace(
            ":",
            "\\:"
        )
    )
    video_filter = (
        f"scale={width}:{height},"
        f"crop={crop_width}:{height}:{crop_x}:0,"
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
    crop_position = detect_people(
        video
    )
    print(
        f"Crop Position: "
        f"{crop_position:.3f}"
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
            "Keine ausgewählten Videos "
            "in selected_clips gefunden."
        )
    print(
        "================================"
    )
    print(
        f"{len(videos)} ausgewählte "
        "Clips gefunden."
    )
    print(
        "Bearbeite maximal 5."
    )
    print(
        "================================"
    )
    successful = 0
    for number, video in enumerate(
        videos[:5],
        start=1
    ):
        try:
            process_video(
                video,
                number
            )
            successful += 1
        except Exception as error:
            print(
                ""
            )
            print(
                "WARNUNG:"
            )
            print(
                f"Clip konnte nicht "
                f"verarbeitet werden: "
                f"{video}"
            )
            print(
                f"Fehler: {error}"
            )
            print(
                "Clip wird übersprungen."
            )
            print(
                ""
            )
    print(
        "================================"
    )
    print(
        f"{successful} von "
        f"{min(len(videos), 5)} "
        "Videos erfolgreich."
    )
    print(
        "================================"
    )
    if successful == 0:
        raise RuntimeError(
            "Keines der ausgewählten "
            "Videos konnte verarbeitet "
            "werden."
        )
if __name__ == "__main__":
    main()