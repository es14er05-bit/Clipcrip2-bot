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

# Strenger als vorher.
GOOD_SCORE = 48

# Unterhalb davon sollte ein Clip eigentlich
# niemals Finalist werden.
HARD_MIN_SCORE = 18

DUPLICATE_THRESHOLD = 0.115

SAMPLE_COUNT = 18

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

    if (
        frames <= 0
        or width <= 0
        or height <= 0
    ):
        return None

    return {
        "frames": frames,
        "fps": fps,
        "width": width,
        "height": height,
        "duration": frames / fps,
    }


# =========================================================
# SAMPLE FRAMES
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

    for i in range(count):

        position = (
            (i + 0.5)
            / count
        )

        frame_number = int(
            info["frames"]
            * position
        )

        cap.set(
            cv2.CAP_PROP_POS_FRAMES,
            frame_number
        )

        success, frame = cap.read()

        if success:
            frames.append(frame)

    cap.release()

    return frames


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
            f"YOLO Fehler: {error}"
        )

        return None


# =========================================================
# FACE DETECTOR
# =========================================================

def face_analysis(frames):

    if not frames:

        return {
            "presence": 0.0,
            "size": 0.0,
            "largest": 0.0,
        }

    detector = cv2.CascadeClassifier(
        cv2.data.haarcascades
        + "haarcascade_frontalface_default.xml"
    )

    detected_frames = 0

    sizes = []

    largest = 0

    for frame in frames:

        try:

            height, width = frame.shape[:2]

            gray = cv2.cvtColor(
                frame,
                cv2.COLOR_BGR2GRAY
            )

            faces = detector.detectMultiScale(
                gray,
                scaleFactor=1.08,
                minNeighbors=4,
                minSize=(22, 22)
            )

            if len(faces) == 0:
                continue

            detected_frames += 1

            best = max(
                faces,
                key=lambda box:
                box[2] * box[3]
            )

            x, y, w, h = best

            ratio = (
                (w * h)
                /
                (width * height)
            )

            sizes.append(
                ratio
            )

            largest = max(
                largest,
                ratio
            )

        except Exception:

            continue

    presence = (
        detected_frames
        / max(len(frames), 1)
    )

    average_size = (
        float(np.mean(sizes))
        if sizes
        else 0
    )

    # Facecams sind oft klein.
    if average_size >= 0.025:
        size_score = 1.0

    elif average_size >= 0.012:
        size_score = 0.85

    elif average_size >= 0.006:
        size_score = 0.65

    elif average_size >= 0.0025:
        size_score = 0.40

    elif average_size > 0:
        size_score = 0.20

    else:
        size_score = 0.0

    return {
        "presence": float(presence),
        "size": float(size_score),
        "largest": float(largest),
    }


# =========================================================
# PERSON ANALYSIS
# =========================================================

def person_analysis(frames):

    model = get_yolo()

    if (
        model is None
        or not frames
    ):

        return {
            "presence": 0,
            "size": 0,
            "movement": 0,
        }

    detections = []

    centers = []

    sizes = []

    for frame in frames:

        height, width = frame.shape[:2]

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

                if class_id != 0:
                    continue

                confidence = float(
                    box.conf[0].item()
                )

                if confidence < 0.32:
                    continue

                x1, y1, x2, y2 = (
                    box.xyxy[0].tolist()
                )

                area = max(
                    0,
                    (x2 - x1)
                    * (y2 - y1)
                )

                if (
                    best is None
                    or area > best["area"]
                ):

                    best = {
                        "area": area,
                        "center_x":
                            (x1 + x2)
                            / 2,
                    }

        if best is None:
            continue

        detections.append(best)

        sizes.append(
            best["area"]
            / (width * height)
        )

        centers.append(
            best["center_x"]
            / width
        )

    presence = (
        len(detections)
        / max(len(frames), 1)
    )

    average_size = (
        float(np.mean(sizes))
        if sizes
        else 0
    )

    if average_size >= 0.12:
        size_score = 1.0

    elif average_size >= 0.06:
        size_score = 0.85

    elif average_size >= 0.03:
        size_score = 0.65

    elif average_size >= 0.012:
        size_score = 0.40

    elif average_size > 0:
        size_score = 0.15

    else:
        size_score = 0

    if len(centers) >= 3:

        diffs = np.abs(
            np.diff(
                np.array(centers)
            )
        )

        movement = min(
            1.0,
            float(
                np.mean(diffs)
                * 7
            )
        )

    else:

        movement = 0

    return {
        "presence": float(presence),
        "size": float(size_score),
        "movement": float(movement),
    }


# =========================================================
# MOTION
# =========================================================

def motion_analysis(frames):

    if len(frames) < 2:

        return {
            "average": 0,
            "peak": 0,
        }

    values = []

    previous = None

    for frame in frames:

        gray = cv2.cvtColor(
            frame,
            cv2.COLOR_BGR2GRAY
        )

        gray = cv2.resize(
            gray,
            (192, 108)
        )

        gray = cv2.GaussianBlur(
            gray,
            (5, 5),
            0
        )

        if previous is not None:

            difference = float(
                np.mean(
                    cv2.absdiff(
                        previous,
                        gray
                    )
                )
            )

            values.append(
                difference
            )

        previous = gray

    if not values:

        return {
            "average": 0,
            "peak": 0,
        }

    return {
        "average":
            float(np.mean(values)),

        "peak":
            float(
                np.percentile(
                    values,
                    90
                )
            ),
    }


# =========================================================
# SHARPNESS
# =========================================================

def sharpness_analysis(frames):

    if not frames:
        return 0

    values = []

    for frame in frames:

        gray = cv2.cvtColor(
            frame,
            cv2.COLOR_BGR2GRAY
        )

        value = cv2.Laplacian(
            gray,
            cv2.CV_64F
        ).var()

        values.append(
            float(value)
        )

    return float(
        np.mean(values)
    )


# =========================================================
# AUDIO
# =========================================================

def audio_analysis(path):

    try:

        command = [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            path,
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-f",
            "s16le",
            "-"
        ]

        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=60
        )

        if (
            result.returncode != 0
            or not result.stdout
        ):

            return {
                "present": 0,
                "energy": 0,
                "peakiness": 0,
            }

        samples = np.frombuffer(
            result.stdout,
            dtype=np.int16
        ).astype(
            np.float32
        )

        if len(samples) < 16000:

            return {
                "present": 0.2,
                "energy": 0,
                "peakiness": 0,
            }

        samples /= 32768.0

        window = 4000

        rms_values = []

        for start in range(
            0,
            len(samples) - window,
            window
        ):

            chunk = samples[
                start:start + window
            ]

            rms = float(
                np.sqrt(
                    np.mean(
                        chunk * chunk
                    )
                    + 1e-9
                )
            )

            rms_values.append(
                rms
            )

        if not rms_values:

            return {
                "present": 0.5,
                "energy": 0,
                "peakiness": 0,
            }

        average = float(
            np.mean(rms_values)
        )

        peak = float(
            np.percentile(
                rms_values,
                90
            )
        )

        std = float(
            np.std(rms_values)
        )

        energy = min(
            1.0,
            average / 0.10
        )

        peakiness = min(
            1.0,
            (
                (peak - average)
                + std
            )
            / 0.10
        )

        return {
            "present": 1.0,
            "energy": energy,
            "peakiness": peakiness,
        }

    except Exception as error:

        print(
            f"Audioanalyse Fehler: {error}"
        )

        return {
            "present": 0.5,
            "energy": 0,
            "peakiness": 0,
        }


# =========================================================
# TITLE
# =========================================================

def title_score(metadata):

    title = str(
        metadata.get(
            "title",
            ""
        )
    ).lower()

    strong_words = [
        "wtf",
        "fail",
        "rage",
        "rastet",
        "eskaliert",
        "lacht",
        "lachen",
        "lustig",
        "crazy",
        "bruder",
        "jussef",
        "reaction",
        "reaktion",
        "schreit",
        "schrei",
        "was",
        "digga",
        "haha",
        "lol",
    ]

    score = 0

    for word in strong_words:

        if word in title:
            score += 2.5

    return min(
        score,
        12
    )


# =========================================================
# VIEWS
# =========================================================

def view_score(metadata):

    try:

        views = int(
            metadata.get(
                "view_count",
                0
            )
        )

    except Exception:

        views = 0

    if views >= 100000:
        return 10

    if views >= 50000:
        return 9

    if views >= 20000:
        return 8

    if views >= 10000:
        return 7

    if views >= 5000:
        return 6

    if views >= 2000:
        return 5

    if views >= 1000:
        return 4

    if views >= 500:
        return 3

    if views >= 100:
        return 2

    return 0


# =========================================================
# SIGNATURE
# =========================================================

def create_signature(frames):

    signatures = []

    for frame in frames[::2]:

        gray = cv2.cvtColor(
            frame,
            cv2.COLOR_BGR2GRAY
        )

        small = cv2.resize(
            gray,
            (24, 24)
        ).astype(
            np.float32
        ) / 255.0

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

        signatures.append(
            (
                hist.flatten(),
                small.flatten()
            )
        )

    return signatures


def signature_distance(
    signature_a,
    signature_b
):

    if (
        not signature_a
        or not signature_b
    ):
        return 999

    results = []

    for hist_a, image_a in signature_a:

        best = 999

        for hist_b, image_b in signature_b:

            hist_distance = (
                cv2.compareHist(
                    hist_a.astype(
                        np.float32
                    ),
                    hist_b.astype(
                        np.float32
                    ),
                    cv2.HISTCMP_BHATTACHARYYA
                )
            )

            image_distance = float(
                np.mean(
                    np.abs(
                        image_a
                        - image_b
                    )
                )
            )

            distance = (
                hist_distance * 0.55
                + image_distance * 0.45
            )

            best = min(
                best,
                distance
            )

        results.append(
            best
        )

    return float(
        np.mean(results)
    )


# =========================================================
# COMPLETE ANALYSIS
# =========================================================

def analyze_video(
    path,
    metadata
):

    info = get_video_info(path)

    if info is None:
        return None

    frames = read_sample_frames(
        path
    )

    if not frames:
        return None

    face = face_analysis(
        frames
    )

    person = person_analysis(
        frames
    )

    motion = motion_analysis(
        frames
    )

    audio = audio_analysis(
        path
    )

    sharpness = sharpness_analysis(
        frames
    )

    # -----------------------------------------------------
    # HUMAN VISIBILITY
    # -----------------------------------------------------

    face_visibility = (
        face["presence"] * 0.65
        + face["size"] * 0.35
    )

    person_visibility = (
        person["presence"] * 0.70
        + person["size"] * 0.30
    )

    human_visibility = max(
        face_visibility,
        person_visibility
    )

    # -----------------------------------------------------
    # SCORE
    # -----------------------------------------------------

    score = 0

    warnings = []

    # Gesicht / Streamer ist unser wichtigstes Signal.
    score += (
        human_visibility
        * 42
    )

    # Gesichtspräsenz extra belohnen.
    score += (
        face["presence"]
        * 14
    )

    # Reaktion / Bewegung der Person.
    score += (
        person["movement"]
        * 7
    )

    # Audio-Spitzen können Lachen,
    # Schreien oder starke Reaktionen sein.
    score += (
        audio["peakiness"]
        * 13
    )

    score += (
        audio["energy"]
        * 5
    )

    # Bewegung zählt nur leicht.
    # Gameplay allein darf keinen Clip retten.
    motion_interest = min(
        1.0,
        motion["peak"]
        / 30
    )

    score += (
        motion_interest
        * 5
    )

    score += title_score(
        metadata
    )

    score += view_score(
        metadata
    )

    # Dauer.
    duration = info[
        "duration"
    ]

    if 12 <= duration <= 45:
        score += 7

    elif 8 <= duration <= 60:
        score += 3

    elif duration > 90:
        score -= 10

    # Sehr unscharf.
    if sharpness < 45:

        score -= 8

        warnings.append(
            "unscharf"
        )

    # -----------------------------------------------------
    # HARTE STRAFEN
    # -----------------------------------------------------

    if human_visibility < 0.08:

        score -= 35

        warnings.append(
            "Jussef praktisch nicht sichtbar"
        )

    elif human_visibility < 0.18:

        score -= 18

        warnings.append(
            "Jussef schlecht sichtbar"
        )

    elif human_visibility < 0.30:

        score -= 7

        warnings.append(
            "Jussef eher klein"
        )

    # Nur viel Gameplay-Bewegung,
    # aber kein Mensch = genau die Clips,
    # die du mit 0/10 bzw. 3/10 bewertet hast.
    if (
        human_visibility < 0.15
        and motion["peak"] > 12
    ):

        score -= 18

        warnings.append(
            "Gameplay-Action ohne sichtbare Reaktion"
        )

    # Lautes Audio ohne sichtbare Person
    # ist ein Backup-Signal, aber kein Topclip.
    if (
        human_visibility < 0.12
        and audio["peakiness"] > 0.55
    ):

        score += 7

        warnings.append(
            "Audio interessant, Person fehlt"
        )

    # Statischer Clip.
    if (
        motion["average"] < 2.0
        and audio["peakiness"] < 0.25
    ):

        score -= 12

        warnings.append(
            "wenig passiert"
        )

    return {
        "path": path,
        "metadata": metadata,
        "info": info,
        "face": face,
        "person": person,
        "human_visibility":
            human_visibility,
        "motion": motion,
        "audio": audio,
        "sharpness": sharpness,
        "score": float(score),
        "warnings": warnings,
        "signature":
            create_signature(frames),
    }


# =========================================================
# MAIN
# =========================================================

def main():

    print("")
    print(
        "=========================================="
    )

    print(
        "   CLIPCRIP2 QUALITY CONTROL V2"
    )

    print(
        "=========================================="
    )

    os.makedirs(
        FINAL_DIR,
        exist_ok=True
    )

    # Alten Output entfernen.
    for old in glob.glob(
        os.path.join(
            FINAL_DIR,
            "*"
        )
    ):

        if os.path.isfile(old):

            os.remove(old)

    candidates = load_json(
        INPUT_JSON,
        []
    )

    if not candidates:

        raise RuntimeError(
            "clips_today.json ist leer."
        )

    video_files = []

    for extension in (
        "mp4",
        "webm",
        "mkv",
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
        f"{len(candidates)} Metadaten."
    )

    print(
        f"{len(video_files)} Videos."
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
                f"Unbekannte Datei: "
                f"{filename}"
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
            "------------------------------------------"
        )

        print(
            f"ANALYSE: {filename}"
        )

        result = analyze_video(
            video,
            metadata
        )

        if result is None:

            print(
                "Analyse fehlgeschlagen."
            )

            continue

        analyzed.append(
            result
        )

        print(
            f"Score: "
            f"{result['score']:.1f}"
        )

        print(
            "Human visibility: "
            f"{result['human_visibility']:.2f}"
        )

        print(
            "Face presence: "
            f"{result['face']['presence']:.2f}"
        )

        print(
            "Person presence: "
            f"{result['person']['presence']:.2f}"
        )

        print(
            "Audio excitement: "
            f"{result['audio']['peakiness']:.2f}"
        )

        print(
            "Motion peak: "
            f"{result['motion']['peak']:.1f}"
        )

        if result[
            "warnings"
        ]:

            print(
                "Warnungen: "
                + ", ".join(
                    result[
                        "warnings"
                    ]
                )
            )

    if not analyzed:

        raise RuntimeError(
            "Kein Video konnte analysiert werden."
        )

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
        "RANKING"
    )

    print(
        "=========================================="
    )

    for index, item in enumerate(
        analyzed,
        start=1
    ):

        print(
            f"{index:02d}. "
            f"{item['score']:.1f} | "
            f"HUMAN "
            f"{item['human_visibility']:.2f} | "
            f"{item['metadata'].get('title', '')}"
        )

    # =====================================================
    # SELECTION
    # =====================================================

    selected = []

    # Zuerst nur wirklich gute Clips.
    for candidate in analyzed:

        if (
            candidate["score"]
            < GOOD_SCORE
        ):
            continue

        duplicate = False

        for existing in selected:

            distance = signature_distance(
                candidate["signature"],
                existing["signature"]
            )

            if (
                distance
                < DUPLICATE_THRESHOLD
            ):

                duplicate = True

                break

        if duplicate:
            continue

        selected.append(
            candidate
        )

        if (
            len(selected)
            >= FINAL_COUNT
        ):
            break

    # =====================================================
    # FALLBACK
    #
    # Wir garantieren weiterhin 5 Dateien.
    # Aber wir nehmen nicht blind alles.
    # =====================================================

    if len(selected) < FINAL_COUNT:

        print("")
        print(
            "Nicht genug Top-Clips."
        )

        print(
            "Suche beste Backups..."
        )

        for candidate in analyzed:

            if candidate in selected:
                continue

            if (
                candidate["score"]
                < HARD_MIN_SCORE
            ):
                continue

            duplicate = False

            for existing in selected:

                distance = signature_distance(
                    candidate["signature"],
                    existing["signature"]
                )

                if (
                    distance
                    < DUPLICATE_THRESHOLD
                ):

                    duplicate = True

                    break

            if duplicate:
                continue

            selected.append(
                candidate
            )

            if (
                len(selected)
                >= FINAL_COUNT
            ):
                break

    # Falls Twitch an dem Tag wirklich nur
    # schwaches Material hat, nehmen wir die
    # besten verbleibenden, damit die Pipeline
    # nicht komplett stirbt.
    if len(selected) < FINAL_COUNT:

        print("")
        print(
            "WARNUNG: "
            "Nicht genug brauchbare Clips."
        )

        print(
            "Pipeline-Fallback aktiv."
        )

        for candidate in analyzed:

            if candidate in selected:
                continue

            duplicate = False

            for existing in selected:

                distance = signature_distance(
                    candidate["signature"],
                    existing["signature"]
                )

                if (
                    distance
                    < DUPLICATE_THRESHOLD
                ):

                    duplicate = True

                    break

            if duplicate:
                continue

            selected.append(
                candidate
            )

            if (
                len(selected)
                >= FINAL_COUNT
            ):
                break

    if (
        len(selected)
        < FINAL_COUNT
    ):

        raise RuntimeError(
            f"Nur {len(selected)} "
            f"unterschiedliche Clips "
            f"gefunden."
        )

    # =====================================================
    # SAVE
    # =====================================================

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
    print(
        "=========================================="
    )

    print(
        "FINALE 5"
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

        clip_id = metadata[
            "id"
        ]

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

            "human_visibility":
                candidate[
                    "human_visibility"
                ],

            "face_presence":
                candidate[
                    "face"
                ][
                    "presence"
                ],

            "audio_excitement":
                candidate[
                    "audio"
                ][
                    "peakiness"
                ],
        }

        final_metadata.append(
            metadata
        )

        print("")
        print(
            f"{number}. "
            f"Score "
            f"{candidate['score']:.1f}"
        )

        print(
            metadata.get(
                "title",
                ""
            )
        )

        print(
            "Human: "
            f"{candidate['human_visibility']:.2f}"
        )

        print(
            "Audio: "
            f"{candidate['audio']['peakiness']:.2f}"
        )

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
    print(
        "=========================================="
    )

    print(
        "QUALITY CONTROL V2 FERTIG"
    )

    print(
        "5 Clips ausgewählt."
    )

    print(
        "Gameplay ohne sichtbare "
        "Reaktion wird jetzt stark "
        "abgewertet."
    )

    print(
        "=========================================="
    )


if __name__ == "__main__":
    main()