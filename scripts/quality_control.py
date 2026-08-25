import os
import glob
import json
import shutil

import cv2
import numpy as np


INPUT_DIR = "downloaded_clips"
FINAL_DIR = "selected_clips"

INPUT_JSON = "clips_today.json"

USED_FILE = "used_clips.json"
HISTORY_FILE = "clip_history.json"

FINAL_COUNT = 5


# ---------------------------------------------------------
# JSON
# ---------------------------------------------------------

def load_json(filename, default):

    if not os.path.exists(filename):
        return default

    try:
        with open(
            filename,
            "r",
            encoding="utf-8"
        ) as file:
            return json.load(file)

    except Exception:
        return default


def save_json(filename, data):

    with open(
        filename,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            data,
            file,
            indent=2,
            ensure_ascii=False
        )


# ---------------------------------------------------------
# VIDEO INFORMATION
# ---------------------------------------------------------

def get_video_info(path):

    cap = cv2.VideoCapture(path)

    if not cap.isOpened():
        return None

    frames = int(
        cap.get(cv2.CAP_PROP_FRAME_COUNT)
    )

    fps = float(
        cap.get(cv2.CAP_PROP_FPS)
    )

    width = int(
        cap.get(cv2.CAP_PROP_FRAME_WIDTH)
    )

    height = int(
        cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
    )

    if fps <= 0:
        fps = 30

    if frames <= 0:
        cap.release()
        return None

    duration = frames / fps

    cap.release()

    return {
        "frames": frames,
        "fps": fps,
        "width": width,
        "height": height,
        "duration": duration,
    }


# ---------------------------------------------------------
# FRAME SAMPLING
# ---------------------------------------------------------

def read_sample_frames(path, count=12):

    info = get_video_info(path)

    if info is None:
        return []

    cap = cv2.VideoCapture(path)

    if not cap.isOpened():
        return []

    frames = []

    total = info["frames"]

    for i in range(count):

        position = (
            (i + 0.5) / count
        )

        frame_number = int(
            total * position
        )

        cap.set(
            cv2.CAP_PROP_POS_FRAMES,
            frame_number
        )

        success, frame = cap.read()

        if not success:
            continue

        frames.append(frame)

    cap.release()

    return frames


# ---------------------------------------------------------
# SHARPNESS
# ---------------------------------------------------------

def sharpness_score(frame):

    gray = cv2.cvtColor(
        frame,
        cv2.COLOR_BGR2GRAY
    )

    value = cv2.Laplacian(
        gray,
        cv2.CV_64F
    ).var()

    return float(value)


def average_sharpness(frames):

    if not frames:
        return 0

    values = []

    for frame in frames:

        values.append(
            sharpness_score(frame)
        )

    return float(
        np.mean(values)
    )


# ---------------------------------------------------------
# MOTION
# ---------------------------------------------------------

def motion_score(frames):

    if len(frames) < 2:
        return 0

    values = []

    previous = None

    for frame in frames:

        gray = cv2.cvtColor(
            frame,
            cv2.COLOR_BGR2GRAY
        )

        gray = cv2.resize(
            gray,
            (320, 180)
        )

        if previous is not None:

            difference = np.mean(
                cv2.absdiff(
                    previous,
                    gray
                )
            )

            values.append(
                float(difference)
            )

        previous = gray

    if not values:
        return 0

    return float(
        np.mean(values)
    )


# ---------------------------------------------------------
# SCENE CHANGE
# ---------------------------------------------------------

def scene_change_score(frames):

    if len(frames) < 3:
        return 0

    values = []

    previous = None

    for frame in frames:

        gray = cv2.cvtColor(
            frame,
            cv2.COLOR_BGR2GRAY
        )

        gray = cv2.resize(
            gray,
            (160, 90)
        )

        if previous is not None:

            difference = np.mean(
                cv2.absdiff(
                    previous,
                    gray
                )
            )

            values.append(
                float(difference)
            )

        previous = gray

    if not values:
        return 0

    # Große Änderungen zwischen Szenen
    # sind ein gutes Signal.
    return float(
        np.percentile(
            values,
            75
        )
    )


# ---------------------------------------------------------
# PERSON DETECTION
# ---------------------------------------------------------

def person_score(frames):

    try:

        from ultralytics import YOLO

        model = YOLO(
            "yolo11n.pt"
        )

    except Exception:

        print(
            "YOLO nicht verfügbar. "
            "Personenprüfung wird übersprungen."
        )

        return 0.5

    if not frames:
        return 0.5

    detected_frames = 0

    person_sizes = []

    person_centers = []

    for frame in frames:

        results = model(
            frame,
            verbose=False
        )

        found_person = False

        frame_height, frame_width = (
            frame.shape[:2]
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

                if confidence < 0.40:
                    continue

                x1, y1, x2, y2 = (
                    box.xyxy[0].tolist()
                )

                width = max(
                    0,
                    x2 - x1
                )

                height = max(
                    0,
                    y2 - y1
                )

                area_ratio = (
                    width * height
                ) / (
                    frame_width
                    * frame_height
                )

                center_x = (
                    x1 + x2
                ) / 2

                center_normalized = (
                    center_x / frame_width
                )

                person_sizes.append(
                    area_ratio
                )

                person_centers.append(
                    center_normalized
                )

                found_person = True

                break

            if found_person:
                break

        if found_person:
            detected_frames += 1

    if not person_sizes:
        return 0

    presence = (
        detected_frames
        / len(frames)
    )

    average_size = float(
        np.mean(person_sizes)
    )

    # Person sollte sichtbar sein,
    # aber nicht das komplette Bild bedecken.
    size_score = min(
        average_size / 0.15,
        1.0
    )

    return float(
        presence * 0.65
        + size_score * 0.35
    )


# ---------------------------------------------------------
# DARK / BAD FRAMES
# ---------------------------------------------------------

def visibility_score(frames):

    if not frames:
        return 0

    values = []

    for frame in frames:

        gray = cv2.cvtColor(
            frame,
            cv2.COLOR_BGR2GRAY
        )

        brightness = float(
            np.mean(gray)
        )

        values.append(
            brightness
        )

    average = float(
        np.mean(values)
    )

    # Extrem dunkle Bilder bestrafen.
    if average < 35:
        return 0

    if average < 55:
        return 0.35

    if average < 80:
        return 0.65

    return 1.0


# ---------------------------------------------------------
# AUDIO
# ---------------------------------------------------------

def audio_score(path):

    try:

        import subprocess

        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "a:0",
                "-show_entries",
                "stream=codec_name",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                path,
            ],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            return 0

        if not result.stdout.strip():
            return 0

        return 1.0

    except Exception:

        return 0.5


# ---------------------------------------------------------
# DUPLICATE SIGNATURE
# ---------------------------------------------------------

def frame_signature(frame):

    gray = cv2.cvtColor(
        frame,
        cv2.COLOR_BGR2GRAY
    )

    gray = cv2.resize(
        gray,
        (32, 32)
    )

    hist = cv2.calcHist(
        [gray],
        [0],
        None,
        [32],
        [0, 256]
    )

    cv2.normalize(
        hist,
        hist
    )

    small = cv2.resize(
        gray,
        (16, 16)
    ).astype(
        np.float32
    ) / 255.0

    return (
        hist.flatten(),
        small.flatten()
    )


def compare_signature(a, b):

    hist_a, image_a = a
    hist_b, image_b = b

    hist_distance = cv2.compareHist(
        hist_a.astype(np.float32),
        hist_b.astype(np.float32),
        cv2.HISTCMP_BHATTACHARYYA
    )

    image_distance = float(
        np.mean(
            np.abs(
                image_a - image_b
            )
        )
    )

    return (
        hist_distance * 0.6
        + image_distance * 0.4
    )


def sample_signature(path):

    frames = read_sample_frames(
        path,
        count=8
    )

    signatures = []

    for frame in frames:

        signatures.append(
            frame_signature(frame)
        )

    return signatures


def compare_videos(signatures_a, signatures_b):

    if not signatures_a or not signatures_b:
        return 999

    distances = []

    for sig_a in signatures_a:

        best = 999

        for sig_b in signatures_b:

            distance = compare_signature(
                sig_a,
                sig_b
            )

            best = min(
                best,
                distance
            )

        distances.append(
            best
        )

    if not distances:
        return 999

    return float(
        np.mean(distances)
    )


# ---------------------------------------------------------
# CONTENT SCORE
# ---------------------------------------------------------

def quality_score(path, metadata):

    info = get_video_info(path)

    if info is None:
        return -999, {}

    duration = info["duration"]

    if duration < 8:
        return -999, {}

    frames = read_sample_frames(
        path,
        count=12
    )

    if not frames:
        return -999, {}

    motion = motion_score(
        frames
    )

    scenes = scene_change_score(
        frames
    )

    sharpness = average_sharpness(
        frames
    )

    person = person_score(
        frames
    )

    visibility = visibility_score(
        frames
    )

    audio = audio_score(
        path
    )

    views = int(
        metadata.get(
            "view_count",
            0
        )
    )

    title = str(
        metadata.get(
            "title",
            ""
        )
    ).lower()

    score = 0.0

    # -----------------------------------------------------
    # Dauer
    # -----------------------------------------------------

    if 12 <= duration <= 45:
        score += 15

    elif 8 <= duration < 12:
        score += 5

    elif 45 < duration <= 60:
        score += 8

    elif duration > 90:
        score -= 10

    # -----------------------------------------------------
    # Bewegung
    # -----------------------------------------------------

    if motion >= 2:
        score += 5

    if motion >= 4:
        score += 8

    if motion >= 8:
        score += 7

    # -----------------------------------------------------
    # Szenenänderungen
    # -----------------------------------------------------

    if scenes >= 4:
        score += 5

    if scenes >= 8:
        score += 7

    # -----------------------------------------------------
    # Person sichtbar
    # -----------------------------------------------------

    score += (
        person * 20
    )

    # -----------------------------------------------------
    # Sichtbarkeit
    # -----------------------------------------------------

    score += (
        visibility * 10
    )

    # -----------------------------------------------------
    # Audio
    # -----------------------------------------------------

    score += (
        audio * 8
    )

    # -----------------------------------------------------
    # Bildqualität
    # -----------------------------------------------------

    if sharpness >= 80:
        score += 5

    if sharpness >= 180:
        score += 5

    # -----------------------------------------------------
    # Twitch Views
    # -----------------------------------------------------

    score += min(
        views / 2000,
        10
    )

    # -----------------------------------------------------
    # Titel-Signale
    # -----------------------------------------------------

    interesting_words = [
        "lol",
        "haha",
        "wtf",
        "crazy",
        "lustig",
        "lachen",
        "eskaliert",
        "reaktion",
        "rage",
        "fail",
        "bruder",
        "chat",
        "krank",
        "was",
        "nein",
        "alter",
    ]

    title_bonus = 0

    for word in interesting_words:

        if word in title:

            title_bonus += 2

    score += min(
        title_bonus,
        10
    )

    # -----------------------------------------------------
    # Harte Ausschlusskriterien
    # -----------------------------------------------------

    reasons = []

    if person < 0.15:

        score -= 25

        reasons.append(
            "Person kaum sichtbar"
        )

    if visibility < 0.25:

        score -= 15

        reasons.append(
            "schlechte Sichtbarkeit"
        )

    if motion < 1.0:

        score -= 20

        reasons.append(
            "sehr wenig Bewegung"
        )

    if audio == 0:

        score -= 10

        reasons.append(
            "kein Audio"
        )

    if sharpness < 30:

        score -= 15

        reasons.append(
            "sehr unscharf"
        )

    details = {
        "duration": duration,
        "motion": motion,
        "scene_change": scenes,
        "sharpness": sharpness,
        "person": person,
        "visibility": visibility,
        "audio": audio,
        "views": views,
        "reasons": reasons,
    }

    return score, details


# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------

def main():

    print("")
    print("================================")
    print("MULTI-STAGE QUALITY CONTROL")
    print("================================")

    os.makedirs(
        FINAL_DIR,
        exist_ok=True
    )

    # Alten Auswahlordner leeren.
    for old in glob.glob(
        os.path.join(
            FINAL_DIR,
            "*"
        )
    ):

        if os.path.isfile(old):
            os.remove(old)

    if not os.path.exists(INPUT_JSON):

        raise FileNotFoundError(
            f"{INPUT_JSON} fehlt."
        )

    candidates = load_json(
        INPUT_JSON,
        []
    )

    if not candidates:

        raise RuntimeError(
            "Keine Kandidaten in clips_today.json."
        )

    video_files = []

    for extension in (
        "mp4",
        "mkv",
        "webm",
        "mov"
    ):

        video_files.extend(
            glob.glob(
                os.path.join(
                    INPUT_DIR,
                    f"*.{extension}"
                )
            )
        )

    video_files.sort()

    print(
        f"{len(video_files)} heruntergeladene "
        "Videos gefunden."
    )

    analyzed = []

    for video in video_files:

        filename = os.path.basename(
            video
        )

        try:

            number = int(
                filename
                .split("_")[1]
                .split(".")[0]
            )

        except Exception:

            print(
                f"Überspringe: {filename}"
            )

            continue

        index = number - 1

        if (
            index < 0
            or index >= len(candidates)
        ):
            continue

        metadata = candidates[
            index
        ]

        print("")
        print(
            f"ANALYSE: {filename}"
        )

        score, details = quality_score(
            video,
            metadata
        )

        if score <= -900:

            print(
                "→ TECHNISCH UNBRAUCHBAR"
            )

            continue

        signatures = sample_signature(
            video
        )

        analyzed.append({
            "path": video,
            "metadata": metadata,
            "score": score,
            "details": details,
            "signatures": signatures,
        })

        print(
            f"Score: {score:.1f}"
        )

        print(
            f"Person: "
            f"{details['person']:.2f}"
        )

        print(
            f"Motion: "
            f"{details['motion']:.2f}"
        )

        print(
            f"Scenes: "
            f"{details['scene_change']:.2f}"
        )

        print(
            f"Sharpness: "
            f"{details['sharpness']:.1f}"
        )

        if details["reasons"]:

            print(
                "Warnungen: "
                + ", ".join(
                    details["reasons"]
                )
            )

    if not analyzed:

        raise RuntimeError(
            "Kein brauchbarer Kandidat gefunden."
        )

    # Beste zuerst.
    analyzed.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    print("")
    print("================================")
    print("KANDIDATEN NACH SCORE")
    print("================================")

    for number, candidate in enumerate(
        analyzed,
        start=1
    ):

        print(
            f"{number:02d}. "
            f"{candidate['score']:.1f} | "
            f"{candidate['metadata'].get('title', '')}"
        )

    # -----------------------------------------------------
    # DIVERSITÄT / DUPLIKATE
    # -----------------------------------------------------

    selected = []

    for candidate in analyzed:

        # Sehr schlechte Kandidaten nicht erzwingen.
        if candidate["score"] < 20:
            continue

        duplicate = False

        for existing in selected:

            similarity = compare_videos(
                candidate["signatures"],
                existing["signatures"]
            )

            if similarity < 0.12:

                duplicate = True

                print("")
                print(
                    "DUPLIKAT/ÄHNLICHER CLIP "
                    "ENTFERNT:"
                )

                print(
                    candidate[
                        "metadata"
                    ].get(
                        "title",
                        ""
                    )
                )

                break

        if duplicate:
            continue

        selected.append(
            candidate
        )

        if len(selected) >= FINAL_COUNT:
            break

    if len(selected) < FINAL_COUNT:

        raise RuntimeError(
            f"Nur {len(selected)} "
            "wirklich brauchbare und "
            "unterschiedliche Clips gefunden. "
            "Es werden absichtlich nicht "
            "schlechte Clips aufgefüllt."
        )

    # -----------------------------------------------------
    # USED + HISTORY
    # -----------------------------------------------------

    used = set(
        load_json(
            USED_FILE,
            []
        )
    )

    history = load_json(
        HISTORY_FILE,
        {}
    )

    final_metadata = []

    print("")
    print("================================")
    print("FINALE AUSWAHL")
    print("================================")

    for number, candidate in enumerate(
        selected,
        start=1
    ):

        source = candidate["path"]

        destination = os.path.join(
            FINAL_DIR,
            f"clip_{number}.mp4"
        )

        shutil.copy2(
            source,
            destination
        )

        metadata = candidate[
            "metadata"
        ]

        clip_id = metadata.get(
            "id"
        )

        if clip_id:

            used.add(
                clip_id
            )

            history[clip_id] = {
                "title": metadata.get(
                    "title",
                    ""
                ),
                "created_at": metadata.get(
                    "created_at",
                    ""
                ),
                "duration": metadata.get(
                    "duration",
                    0
                ),
                "view_count": metadata.get(
                    "view_count",
                    0
                ),
                "quality_score": candidate[
                    "score"
                ],
                "quality_details": candidate[
                    "details"
                ],
            }

        final_metadata.append(
            metadata
        )

        print(
            f"{number}. "
            f"{metadata.get('title', '')} "
            f"| Score "
            f"{candidate['score']:.1f}"
        )

    # Nur die tatsächlich ausgewählten 5
    # bleiben in clips_today.json.
    save_json(
        INPUT_JSON,
        final_metadata
    )

    save_json(
        USED_FILE,
        sorted(
            list(used)
        )
    )

    save_json(
        HISTORY_FILE,
        history
    )

    print("")
    print("================================")
    print("QUALITY CONTROL ERFOLGREICH")
    print("================================")
    print(
        "5 Clips ausgewählt."
    )
    print(
        "Nur diese 5 wurden als benutzt "
        "gespeichert."
    )


if __name__ == "__main__":
    main()