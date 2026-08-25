import os
import glob
import json
import shutil
import subprocess

import cv2
import numpy as np


INPUT_DIR = "downloaded_clips"
FINAL_DIR = "selected_clips"

INPUT_JSON = "clips_today.json"

USED_FILE = "used_clips.json"
HISTORY_FILE = "clip_history.json"

FINAL_COUNT = 5

# Wir prüfen viele Kandidaten und wählen daraus 5.
# get_clips.py liefert aktuell 40.
MIN_ACCEPTABLE_SCORE = 25

# Je kleiner der Wert, desto ähnlicher sind zwei Videos.
DUPLICATE_THRESHOLD = 0.13

# Anzahl der Frames für die verschiedenen Analysen.
SAMPLE_COUNT = 16

# YOLO einmal laden und für alle Clips wiederverwenden.
YOLO_MODEL_NAME = "yolo11n.pt"

YOLO_MODEL = None


# =========================================================
# JSON
# =========================================================

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

    except Exception as error:

        print(
            f"JSON konnte nicht gelesen werden "
            f"({filename}): {error}"
        )

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


# =========================================================
# VIDEO INFO
# =========================================================

def get_video_info(path):

    cap = cv2.VideoCapture(path)

    if not cap.isOpened():
        return None

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

    if fps <= 0:
        fps = 30

    if frames <= 0:
        return None

    if width <= 0 or height <= 0:
        return None

    return {
        "frames": frames,
        "fps": fps,
        "width": width,
        "height": height,
        "duration": frames / fps,
    }


# =========================================================
# FRAME SAMPLING
# =========================================================

def read_sample_frames(
    path,
    count=SAMPLE_COUNT
):

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
            (i + 0.5)
            / count
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


# =========================================================
# SHARPNESS
# =========================================================

def sharpness_score(frame):

    gray = cv2.cvtColor(
        frame,
        cv2.COLOR_BGR2GRAY
    )

    return float(
        cv2.Laplacian(
            gray,
            cv2.CV_64F
        ).var()
    )


def average_sharpness(frames):

    if not frames:
        return 0

    values = [
        sharpness_score(frame)
        for frame in frames
    ]

    return float(
        np.mean(values)
    )


# =========================================================
# MOTION
# =========================================================

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


# =========================================================
# ACTION / TEMPORAL CHANGE
# =========================================================

def action_score(frames):

    if len(frames) < 4:
        return 0

    changes = []

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

        gray = cv2.GaussianBlur(
            gray,
            (5, 5),
            0
        )

        if previous is not None:

            diff = np.mean(
                cv2.absdiff(
                    previous,
                    gray
                )
            )

            changes.append(
                float(diff)
            )

        previous = gray

    if not changes:
        return 0

    changes = np.array(
        changes,
        dtype=np.float32
    )

    # Nicht nur Durchschnitt betrachten.
    # Ein deutlicher Peak ist interessant.
    average = float(
        np.mean(changes)
    )

    peak = float(
        np.percentile(
            changes,
            85
        )
    )

    maximum = float(
        np.max(changes)
    )

    return (
        average * 0.35
        + peak * 0.45
        + maximum * 0.20
    )


# =========================================================
# SCENE CHANGE
# =========================================================

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

    return float(
        np.percentile(
            values,
            80
        )
    )


# =========================================================
# YOLO
# =========================================================

def get_yolo():

    global YOLO_MODEL

    if YOLO_MODEL is not None:
        return YOLO_MODEL

    try:

        from ultralytics import YOLO

        print(
            "YOLO-Modell wird geladen..."
        )

        YOLO_MODEL = YOLO(
            YOLO_MODEL_NAME
        )

        return YOLO_MODEL

    except Exception as error:

        print(
            "YOLO konnte nicht geladen "
            f"werden: {error}"
        )

        return None


# =========================================================
# PERSON ANALYSIS
# =========================================================

def analyze_person(frames):

    model = get_yolo()

    if model is None:

        return {
            "presence": 0.5,
            "size": 0.5,
            "center": 0.5,
            "stability": 0.5,
            "action": 0.5,
        }

    if not frames:

        return {
            "presence": 0,
            "size": 0,
            "center": 0,
            "stability": 0,
            "action": 0,
        }

    detections = []

    for frame in frames:

        frame_height, frame_width = (
            frame.shape[:2]
        )

        best = None

        try:

            results = model(
                frame,
                verbose=False
            )

        except Exception:

            continue

        for result in results:

            if result.boxes is None:
                continue

            for box in result.boxes:

                class_id = int(
                    box.cls[0].item()
                )

                # COCO: 0 = person
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

                box_width = max(
                    0,
                    x2 - x1
                )

                box_height = max(
                    0,
                    y2 - y1
                )

                area = (
                    box_width
                    * box_height
                )

                if best is None or area > best["area"]:

                    center_x = (
                        x1 + x2
                    ) / 2

                    center_y = (
                        y1 + y2
                    ) / 2

                    best = {
                        "area": area,
                        "area_ratio": (
                            area
                            /
                            (
                                frame_width
                                * frame_height
                            )
                        ),
                        "center_x": (
                            center_x
                            / frame_width
                        ),
                        "center_y": (
                            center_y
                            / frame_height
                        ),
                        "confidence": confidence,
                    }

        detections.append(
            best
        )

    detected = [
        item
        for item in detections
        if item is not None
    ]

    if not detected:

        return {
            "presence": 0,
            "size": 0,
            "center": 0,
            "stability": 0,
            "action": 0,
        }

    # -----------------------------------------------------
    # Präsenz
    # -----------------------------------------------------

    presence = (
        len(detected)
        /
        max(
            len(frames),
            1
        )
    )

    # -----------------------------------------------------
    # Personengröße
    # -----------------------------------------------------

    sizes = [
        item["area_ratio"]
        for item in detected
    ]

    average_size = float(
        np.mean(sizes)
    )

    # Zu kleine Person = schlecht.
    # Extrem große Person = ebenfalls nicht ideal.
    if average_size < 0.015:

        size_score = 0.05

    elif average_size < 0.03:

        size_score = 0.30

    elif average_size < 0.06:

        size_score = 0.60

    elif average_size < 0.30:

        size_score = 1.0

    else:

        size_score = 0.75

    # -----------------------------------------------------
    # Position
    # -----------------------------------------------------

    centers = [
        item["center_x"]
        for item in detected
    ]

    average_center = float(
        np.mean(centers)
    )

    # Für TikTok ist es grundsätzlich
    # gut, wenn die Person nicht ganz
    # am Rand klebt.
    distance_from_center = abs(
        average_center - 0.5
    )

    center_score = max(
        0.0,
        1.0
        - distance_from_center * 1.8
    )

    # -----------------------------------------------------
    # Stabilität
    # -----------------------------------------------------

    if len(centers) >= 2:

        center_std = float(
            np.std(centers)
        )

        stability = max(
            0.0,
            min(
                1.0,
                1.0
                - center_std * 4
            )
        )

    else:

        stability = 0.5

    # -----------------------------------------------------
    # Person bewegt sich?
    # -----------------------------------------------------

    if len(centers) >= 3:

        movement = float(
            np.std(centers)
        )

        person_action = min(
            1.0,
            movement * 8
        )

    else:

        person_action = 0.5

    return {
        "presence": float(
            presence
        ),
        "size": float(
            size_score
        ),
        "center": float(
            center_score
        ),
        "stability": float(
            stability
        ),
        "action": float(
            person_action
        ),
    }


# =========================================================
# VISIBILITY
# =========================================================

def visibility_score(frames):

    if not frames:
        return 0

    brightness = []

    contrast = []

    for frame in frames:

        gray = cv2.cvtColor(
            frame,
            cv2.COLOR_BGR2GRAY
        )

        brightness.append(
            float(
                np.mean(gray)
            )
        )

        contrast.append(
            float(
                np.std(gray)
            )
        )

    avg_brightness = float(
        np.mean(brightness)
    )

    avg_contrast = float(
        np.mean(contrast)
    )

    if avg_brightness < 25:
        brightness_score = 0

    elif avg_brightness < 45:
        brightness_score = 0.30

    elif avg_brightness < 70:
        brightness_score = 0.70

    elif avg_brightness <= 210:
        brightness_score = 1.0

    elif avg_brightness <= 235:
        brightness_score = 0.70

    else:
        brightness_score = 0.30

    contrast_score = min(
        1.0,
        max(
            0.0,
            avg_contrast / 65
        )
    )

    return float(
        brightness_score * 0.65
        + contrast_score * 0.35
    )


# =========================================================
# AUDIO
# =========================================================

def audio_score(path):

    try:

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
                "default="
                "noprint_wrappers=1:"
                "nokey=1",
                path,
            ],
            capture_output=True,
            text=True,
        )

        if (
            result.returncode == 0
            and result.stdout.strip()
        ):

            return 1.0

        return 0

    except Exception:

        return 0.5


# =========================================================
# SIGNATURE
# =========================================================

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


def get_signatures(path):

    frames = read_sample_frames(
        path,
        count=8
    )

    return [
        frame_signature(frame)
        for frame in frames
    ]


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


def compare_videos(
    signatures_a,
    signatures_b
):

    if (
        not signatures_a
        or not signatures_b
    ):

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


# =========================================================
# METADATA SCORE
# =========================================================

def metadata_score(metadata):

    score = 0

    views = int(
        metadata.get(
            "view_count",
            0
        )
    )

    score += min(
        views / 2500,
        8
    )

    title = str(
        metadata.get(
            "title",
            ""
        )
    ).lower()

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
        "nein",
        "alter",
        "was",
        "bro",
    ]

    matches = 0

    for word in interesting_words:

        if word in title:
            matches += 1

    score += min(
        matches * 2,
        8
    )

    return float(score)


# =========================================================
# MAIN QUALITY SCORE
# =========================================================

def quality_score(
    path,
    metadata
):

    info = get_video_info(path)

    if info is None:
        return -999, {}

    duration = info["duration"]

    if duration < 8:
        return -999, {}

    frames = read_sample_frames(
        path,
        SAMPLE_COUNT
    )

    if len(frames) < 4:
        return -999, {}

    motion = motion_score(
        frames
    )

    action = action_score(
        frames
    )

    scenes = scene_change_score(
        frames
    )

    sharpness = average_sharpness(
        frames
    )

    person = analyze_person(
        frames
    )

    visibility = visibility_score(
        frames
    )

    audio = audio_score(
        path
    )

    meta = metadata_score(
        metadata
    )

    score = 0.0

    reasons = []

    # =====================================================
    # DURATION
    # =====================================================

    if 12 <= duration <= 45:

        score += 15

    elif 8 <= duration < 12:

        score += 7

    elif 45 < duration <= 60:

        score += 9

    elif duration > 90:

        score -= 12

        reasons.append(
            "zu lang"
        )

    # =====================================================
    # MOTION
    # =====================================================

    if motion >= 2:
        score += 5

    if motion >= 4:
        score += 7

    if motion >= 7:
        score += 8

    # =====================================================
    # ACTION PEAK
    # =====================================================

    if action >= 3:
        score += 5

    if action >= 5:
        score += 7

    if action >= 8:
        score += 8

    # =====================================================
    # SCENE CHANGES
    # =====================================================

    if scenes >= 4:
        score += 4

    if scenes >= 7:
        score += 6

    # =====================================================
    # PERSON
    # =====================================================

    score += (
        person["presence"]
        * 18
    )

    score += (
        person["size"]
        * 12
    )

    score += (
        person["center"]
        * 6
    )

    score += (
        person["action"]
        * 8
    )

    # =====================================================
    # VISIBILITY
    # =====================================================

    score += (
        visibility
        * 8
    )

    # =====================================================
    # AUDIO
    # =====================================================

    score += (
        audio
        * 7
    )

    # =====================================================
    # SHARPNESS
    # =====================================================

    if sharpness >= 60:
        score += 3

    if sharpness >= 120:
        score += 4

    if sharpness >= 220:
        score += 3

    # =====================================================
    # METADATA
    # =====================================================

    score += meta

    # =====================================================
    # HARD PENALTIES
    # =====================================================

    if person["presence"] < 0.20:

        score -= 25

        reasons.append(
            "Jussef kaum sichtbar"
        )

    elif person["presence"] < 0.40:

        score -= 10

        reasons.append(
            "Jussef nicht konstant sichtbar"
        )

    if person["size"] < 0.20:

        score -= 18

        reasons.append(
            "Person zu klein"
        )

    if motion < 1.0:

        score -= 20

        reasons.append(
            "kaum Bewegung"
        )

    if action < 1.5:

        score -= 12

        reasons.append(
            "kaum Action"
        )

    if visibility < 0.25:

        score -= 15

        reasons.append(
            "schlechte Sichtbarkeit"
        )

    if audio == 0:

        score -= 10

        reasons.append(
            "kein Audio"
        )

    if sharpness < 25:

        score -= 15

        reasons.append(
            "sehr unscharf"
        )

    # =====================================================
    # GAME-ONLY / PERSON-ONLY SIGNAL
    #
    # Wenn Bewegung hoch ist, aber Jussef kaum erkannt
    # wird, ist das häufig nur Gameplay.
    # =====================================================

    if (
        motion >= 4
        and action >= 4
        and person["presence"] < 0.30
    ):

        score -= 25

        reasons.append(
            "viel Action aber Person kaum sichtbar"
        )

    details = {

        "duration": duration,

        "motion": motion,

        "action": action,

        "scene_change": scenes,

        "sharpness": sharpness,

        "person_presence":
            person["presence"],

        "person_size":
            person["size"],

        "person_center":
            person["center"],

        "person_action":
            person["action"],

        "visibility":
            visibility,

        "audio":
            audio,

        "metadata":
            meta,

        "reasons":
            reasons,
    }

    return float(
        score
    ), details


# =========================================================
# CLIP NUMBER
# =========================================================

def get_clip_number(filename):

    name = os.path.basename(
        filename
    )

    try:

        # clip_1.mp4
        number = int(
            name
            .split("_")[1]
            .split(".")[0]
        )

        return number

    except Exception:

        return None


# =========================================================
# MAIN
# =========================================================

def main():

    print("")
    print(
        "=========================================="
    )
    print(
        "   MULTI-STAGE QUALITY CONTROL"
    )
    print(
        "=========================================="
    )
    print(
        "Prüfe Kandidaten mit visueller Analyse..."
    )
    print("")

    os.makedirs(
        FINAL_DIR,
        exist_ok=True
    )

    # -----------------------------------------------------
    # Alte Auswahl löschen
    # -----------------------------------------------------

    for old_file in glob.glob(
        os.path.join(
            FINAL_DIR,
            "*"
        )
    ):

        if os.path.isfile(old_file):

            try:
                os.remove(old_file)
            except Exception:
                pass

    # -----------------------------------------------------
    # Kandidaten laden
    # -----------------------------------------------------

    if not os.path.exists(
        INPUT_JSON
    ):

        raise FileNotFoundError(
            "clips_today.json fehlt."
        )

    candidates = load_json(
        INPUT_JSON,
        []
    )

    if not candidates:

        raise RuntimeError(
            "Keine Kandidaten vorhanden."
        )

    # -----------------------------------------------------
    # Used History
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

    print(
        f"{len(candidates)} Metadaten-Kandidaten."
    )

    # -----------------------------------------------------
    # Videos suchen
    # -----------------------------------------------------

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

    if not video_files:

        raise RuntimeError(
            "Keine heruntergeladenen Videos."
        )

    print(
        f"{len(video_files)} Dateien gefunden."
    )

    # -----------------------------------------------------
    # Analyse
    # -----------------------------------------------------

    analyzed = []

    for video in video_files:

        filename = os.path.basename(
            video
        )

        number = get_clip_number(
            filename
        )

        if number is None:

            print(
                f"Überspringe: {filename}"
            )

            continue

        index = number - 1

        if (
            index < 0
            or index >= len(candidates)
        ):

            print(
                f"Keine Metadaten für "
                f"{filename}"
            )

            continue

        metadata = candidates[
            index
        ]

        clip_id = str(
            metadata.get(
                "id",
                ""
            )
        )

        # -------------------------------------------------
        # Bereits verwendet
        # -------------------------------------------------

        if (
            clip_id
            and clip_id in used
        ):

            print(
                f"ÜBERSPRUNGEN: {filename} "
                "wurde bereits verwendet."
            )

            continue

        print("")
        print(
            "------------------------------------------"
        )

        print(
            f"ANALYSE: {filename}"
        )

        try:

            score, details = (
                quality_score(
                    video,
                    metadata
                )
            )

        except Exception as error:

            print(
                f"Analysefehler: {error}"
            )

            continue

        if score <= -900:

            print(
                "Ungültiges Video."
            )

            continue

        signatures = get_signatures(
            video
        )

        analyzed.append({

            "path":
                video,

            "metadata":
                metadata,

            "score":
                score,

            "details":
                details,

            "signatures":
                signatures,
        })

        print(
            f"Score: {score:.1f}"
        )

        print(
            f"Person: "
            f"{details['person_presence']:.2f}"
        )

        print(
            f"Action: "
            f"{details['action']:.2f}"
        )

        print(
            f"Motion: "
            f"{details['motion']:.2f}"
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
            "Keiner der Kandidaten konnte "
            "analysiert werden."
        )

    # -----------------------------------------------------
    # Sortieren
    # -----------------------------------------------------

    analyzed.sort(
        key=lambda item:
        item["score"],
        reverse=True
    )

    print("")
    print(
        "=========================================="
    )
    print(
        "BESTE KANDIDATEN NACH SCORE"
    )
    print(
        "=========================================="
    )

    for index, item in enumerate(
        analyzed[:15],
        start=1
    ):

        title = item[
            "metadata"
        ].get(
            "title",
            ""
        )

        print(
            f"{index:02d}. "
            f"{item['score']:.1f} "
            f"| {title}"
        )

    # -----------------------------------------------------
    # FINALE AUSWAHL
    #
    # Nicht einfach Top 5.
    # Ähnliche Clips werden übersprungen.
    # -----------------------------------------------------

    selected = []

    for candidate in analyzed:

        score = candidate[
            "score"
        ]

        if score < MIN_ACCEPTABLE_SCORE:

            print(
                "Überspringe schlechten "
                f"Kandidaten ({score:.1f})"
            )

            continue

        duplicate = False

        for existing in selected:

            similarity = compare_videos(
                candidate[
                    "signatures"
                ],
                existing[
                    "signatures"
                ]
            )

            if similarity < DUPLICATE_THRESHOLD:

                duplicate = True

                print("")
                print(
                    "DUPLIKAT / ÄHNLICHER MOMENT "
                    "ENTFERNT"
                )

                print(
                    "Neu: "
                    + candidate[
                        "metadata"
                    ].get(
                        "title",
                        ""
                    )
                )

                print(
                    "Ähnlich zu: "
                    + existing[
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

    # -----------------------------------------------------
    # Falls 5 zu strenge Kriterien nicht schaffen:
    # nicht einfach Müll erzwingen.
    # -----------------------------------------------------

    if len(selected) < FINAL_COUNT:

        print("")
        print(
            "WARNUNG:"
        )

        print(
            f"Nur {len(selected)} "
            "wirklich gute und "
            "unterschiedliche Clips gefunden."
        )

        # Wir suchen jetzt noch einmal nach
        # Kandidaten, die zwar unter dem normalen
        # Mindestscore liegen, aber trotzdem besser
        # als die schlechtesten bereits ausgewählten
        # sind und nicht doppelt sind.
        #
        # Dadurch kann der Workflow trotzdem
        # 5 Clips liefern, ohne blind die ersten
        # 5 Dateien zu nehmen.

        fallback_candidates = [
            item
            for item in analyzed
            if item not in selected
        ]

        for candidate in fallback_candidates:

            if len(selected) >= FINAL_COUNT:
                break

            duplicate = False

            for existing in selected:

                similarity = compare_videos(
                    candidate[
                        "signatures"
                    ],
                    existing[
                        "signatures"
                    ]
                )

                if similarity < DUPLICATE_THRESHOLD:

                    duplicate = True
                    break

            if duplicate:
                continue

            selected.append(
                candidate
            )

    # -----------------------------------------------------
    # Letzte Sicherheitsprüfung
    # -----------------------------------------------------

    if not selected:

        raise RuntimeError(
            "Quality Control konnte keinen "
            "brauchbaren Clip auswählen."
        )

    # Wir nehmen maximal 5.
    selected = selected[
        :FINAL_COUNT
    ]

    # -----------------------------------------------------
    # FINALE DATEIEN
    # -----------------------------------------------------

    final_metadata = []

    print("")
    print(
        "=========================================="
    )
    print(
        "FINALE AUSWAHL"
    )
    print(
        "=========================================="
    )

    for number, candidate in enumerate(
        selected,
        start=1
    ):

        source = candidate[
            "path"
        ]

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

        clip_id = str(
            metadata.get(
                "id",
                ""
            )
        )

        if clip_id:

            used.add(
                clip_id
            )

            history[
                clip_id
            ] = {

                "title":
                    metadata.get(
                        "title",
                        ""
                    ),

                "created_at":
                    metadata.get(
                        "created_at",
                        ""
                    ),

                "duration":
                    metadata.get(
                        "duration",
                        0
                    ),

                "quality_score":
                    candidate[
                        "score"
                    ],

                "quality_details":
                    candidate[
                        "details"
                    ],
            }

        final_metadata.append(
            metadata
        )

        print("")
        print(
            f"{number}. "
            f"Score {candidate['score']:.1f}"
        )

        print(
            metadata.get(
                "title",
                ""
            )
        )

        print(
            "Person: "
            f"{candidate['details']['person_presence']:.2f}"
        )

        print(
            "Action: "
            f"{candidate['details']['action']:.2f}"
        )

    # -----------------------------------------------------
    # clips_today.json auf finale Clips setzen
    # -----------------------------------------------------

    save_json(
        INPUT_JSON,
        final_metadata
    )

    # -----------------------------------------------------
    # History speichern
    # -----------------------------------------------------

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
    print(
        "=========================================="
    )

    print(
        f"QUALITY CONTROL FERTIG: "
        f"{len(selected)} Clips"
    )

    print(
        "Die ausgewählten Clips liegen in:"
    )

    print(
        FINAL_DIR
    )

    print(
        "=========================================="
    )


if __name__ == "__main__":

    main()