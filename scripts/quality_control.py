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
def load_detectors():
    detectors = {}
    # Gesichtserkennung
    try:
        face_path = cv2.data.haarcascades + (
            "haarcascade_frontalface_default.xml"
        )
        face_detector = cv2.CascadeClassifier(
            face_path
        )
        if not face_detector.empty():
            detectors["face"] = face_detector
    except Exception:
        pass
    # YOLO
    try:
        from ultralytics import YOLO
        detectors["yolo"] = YOLO(
            "yolo11n.pt"
        )
    except Exception:
        print(
            "YOLO konnte nicht geladen werden."
        )
    return detectors
def analyze_video(path, detectors):
    info = get_video_info(path)
    if info is None:
        return None
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        return None
    sample_count = 12
    face_hits = 0
    person_hits = 0
    face_positions = []
    person_positions = []
    motion_values = []
    previous_gray = None
    for i in range(sample_count):
        position = (
            (i + 0.5)
            / sample_count
        )
        frame_number = int(
            info["frames"] * position
        )
        cap.set(
            cv2.CAP_PROP_POS_FRAMES,
            frame_number
        )
        success, frame = cap.read()
        if not success:
            continue
        height, width = frame.shape[:2]
        gray = cv2.cvtColor(
            frame,
            cv2.COLOR_BGR2GRAY
        )
        small_gray = cv2.resize(
            gray,
            (160, 90)
        )
        if previous_gray is not None:
            difference = np.mean(
                cv2.absdiff(
                    previous_gray,
                    small_gray
                )
            )
            motion_values.append(
                float(difference)
            )
        previous_gray = small_gray
        # -------------------------
        # Gesicht erkennen
        # -------------------------
        if "face" in detectors:
            try:
                faces = detectors[
                    "face"
                ].detectMultiScale(
                    gray,
                    scaleFactor=1.1,
                    minNeighbors=5,
                    minSize=(30, 30)
                )
                if len(faces) > 0:
                    # Größtes Gesicht bevorzugen
                    face = max(
                        faces,
                        key=lambda box:
                        box[2] * box[3]
                    )
                    x, y, w, h = face
                    center_x = (
                        x + w / 2
                    ) / width
                    area_ratio = (
                        w * h
                    ) / (
                        width * height
                    )
                    # Sehr kleine zufällige
                    # Erkennungen ignorieren
                    if area_ratio >= 0.002:
                        face_hits += 1
                        face_positions.append(
                            (
                                center_x,
                                area_ratio
                            )
                        )
            except Exception:
                pass
        # -------------------------
        # Person mit YOLO erkennen
        # -------------------------
        if "yolo" in detectors:
            try:
                results = detectors[
                    "yolo"
                ](
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
                        # COCO 0 = person
                        if class_id != 0:
                            continue
                        confidence = float(
                            box.conf[0].item()
                        )
                        if confidence < 0.50:
                            continue
                        x1, y1, x2, y2 = (
                            box.xyxy[0].tolist()
                        )
                        area = (
                            max(0, x2 - x1)
                            *
                            max(0, y2 - y1)
                        )
                        area_ratio = (
                            area
                            /
                            (width * height)
                        )
                        center_x = (
                            (x1 + x2) / 2
                        ) / width
                        candidate = (
                            area_ratio,
                            confidence,
                            center_x
                        )
                        if (
                            best_person is None
                            or candidate[0]
                            > best_person[0]
                        ):
                            best_person = candidate
                if best_person is not None:
                    area_ratio, confidence, center_x = (
                        best_person
                    )
                    if area_ratio >= 0.015:
                        person_hits += 1
                        person_positions.append(
                            (
                                center_x,
                                area_ratio
                            )
                        )
            except Exception:
                pass
    cap.release()
    face_ratio = (
        face_hits / sample_count
    )
    person_ratio = (
        person_hits / sample_count
    )
    if motion_values:
        motion = float(
            np.mean(motion_values)
        )
        motion_peak = float(
            np.max(motion_values)
        )
    else:
        motion = 0
        motion_peak = 0
    # Gesicht bevorzugen.
    # Falls kein Gesicht gefunden wurde,
    # Personenerkennung verwenden.
    if face_positions:
        positions = [
            p[0]
            for p in face_positions
        ]
        areas = [
            p[1]
            for p in face_positions
        ]
        weighted_position = np.average(
            positions,
            weights=areas
        )
    elif person_positions:
        positions = [
            p[0]
            for p in person_positions
        ]
        areas = [
            p[1]
            for p in person_positions
        ]
        weighted_position = np.average(
            positions,
            weights=areas
        )
    else:
        weighted_position = 0.5
    return {
        "info": info,
        "face_ratio": face_ratio,
        "person_ratio": person_ratio,
        "motion": motion,
        "motion_peak": motion_peak,
        "position": float(
            max(
                0.15,
                min(
                    0.85,
                    weighted_position
                )
            )
        ),
    }
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
def sample_signatures(path):
    info = get_video_info(path)
    if info is None:
        return []
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        return []
    signatures = []
    for i in range(8):
        frame_number = int(
            info["frames"]
            * ((i + 0.5) / 8)
        )
        cap.set(
            cv2.CAP_PROP_POS_FRAMES,
            frame_number
        )
        success, frame = cap.read()
        if not success:
            continue
        signatures.append(
            frame_signature(frame)
        )
    cap.release()
    return signatures
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
        +
        image_distance * 0.4
    )
def compare_videos(a, b):
    if not a or not b:
        return 999
    distances = []
    for sig_a in a:
        best = 999
        for sig_b in b:
            distance = compare_signature(
                sig_a,
                sig_b
            )
            best = min(
                best,
                distance
            )
        distances.append(best)
    if not distances:
        return 999
    return float(
        np.mean(distances)
    )
def quality_score(
    analysis,
    metadata
):
    if analysis is None:
        return -999
    info = analysis["info"]
    duration = info["duration"]
    width = info["width"]
    height = info["height"]
    score = 0
    # -------------------------
    # Länge
    # -------------------------
    if duration < 8:
        return -999
    if 12 <= duration <= 45:
        score += 20
    elif 8 <= duration < 12:
        score += 5
    elif 45 < duration <= 60:
        score += 8
    elif duration > 90:
        score -= 20
    # -------------------------
    # Videoqualität
    # -------------------------
    if width >= 1280:
        score += 8
    if height >= 720:
        score += 5
    # -------------------------
    # Jussef sichtbar
    # -------------------------
    face_ratio = analysis[
        "face_ratio"
    ]
    person_ratio = analysis[
        "person_ratio"
    ]
    # Gesicht ist das stärkste Signal
    if face_ratio >= 0.75:
        score += 30
    elif face_ratio >= 0.50:
        score += 22
    elif face_ratio >= 0.30:
        score += 12
    elif face_ratio >= 0.15:
        score += 3
    else:
        score -= 20
    # Person zusätzlich
    if person_ratio >= 0.70:
        score += 15
    elif person_ratio >= 0.45:
        score += 10
    elif person_ratio >= 0.25:
        score += 5
    else:
        score -= 10
    # -------------------------
    # Bewegung / Action
    # -------------------------
    motion = analysis[
        "motion"
    ]
    peak = analysis[
        "motion_peak"
    ]
    if motion >= 8:
        score += 15
    elif motion >= 5:
        score += 10
    elif motion >= 3:
        score += 5
    else:
        score -= 10
    if peak >= 12:
        score += 8
    # -------------------------
    # Twitch Views
    # -------------------------
    views = int(
        metadata.get(
            "view_count",
            0
        )
    )
    score += min(
        views / 1000,
        15
    )
    # -------------------------
    # Titel-Signale
    # -------------------------
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
        "digga",
        "krank",
        "was",
        "nein",
    ]
    for word in interesting_words:
        if word in title:
            score += 3
    return score
def main():
    print("================================")
    print("CLIPCRİP2 QUALITY CONTROL")
    print("================================")
    os.makedirs(
        FINAL_DIR,
        exist_ok=True
    )
    # Alten Auswahlordner leeren
    for old in glob.glob(
        os.path.join(
            FINAL_DIR,
            "*"
        )
    ):
        if os.path.isfile(old):
            os.remove(old)
    if not os.path.exists(
        INPUT_JSON
    ):
        raise FileNotFoundError(
            f"{INPUT_JSON} fehlt."
        )
    with open(
        INPUT_JSON,
        "r",
        encoding="utf-8"
    ) as file:
        candidates = json.load(file)
    if not candidates:
        raise RuntimeError(
            "Keine Kandidaten vorhanden."
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
        f"{len(video_files)} Kandidaten "
        "werden geprüft."
    )
    detectors = load_detectors()
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
        metadata = candidates[index]
        analysis = analyze_video(
            video,
            detectors
        )
        if analysis is None:
            print(
                f"Analyse fehlgeschlagen: "
                f"{filename}"
            )
            continue
        score = quality_score(
            analysis,
            metadata
        )
        print(
            f"{filename} | "
            f"Score {score:.1f} | "
            f"Gesicht "
            f"{analysis['face_ratio']:.0%} | "
            f"Person "
            f"{analysis['person_ratio']:.0%} | "
            f"Motion "
            f"{analysis['motion']:.1f}"
        )
        # Sehr schlechte Clips sofort raus
        if score < 25:
            print(
                "  → AUSGESONDERT"
            )
            continue
        signatures = sample_signatures(
            video
        )
        analyzed.append({
            "path": video,
            "metadata": metadata,
            "analysis": analysis,
            "signatures": signatures,
            "score": score,
        })
    # Beste zuerst
    analyzed.sort(
        key=lambda x: x["score"],
        reverse=True
    )
    selected = []
    for candidate in analyzed:
        duplicate = False
        for existing in selected:
            similarity = compare_videos(
                candidate["signatures"],
                existing["signatures"]
            )
            if similarity < 0.12:
                duplicate = True
                print(
                    "ÄHNLICHER CLIP ENTFERNT:"
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
            "Quality Control konnte nur "
            f"{len(selected)} statt "
            f"{FINAL_COUNT} wirklich "
            "brauchbare und unterschiedliche "
            "Clips finden."
        )
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
        clip_id = metadata[
            "id"
        ]
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
            "quality_score": candidate[
                "score"
            ],
            "face_ratio": candidate[
                "analysis"
            ]["face_ratio"],
            "person_ratio": candidate[
                "analysis"
            ]["person_ratio"],
            "motion": candidate[
                "analysis"
            ]["motion"],
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
    # WICHTIG:
    # clips_today.json enthält ab jetzt
    # nur noch die finalen 5.
    with open(
        INPUT_JSON,
        "w",
        encoding="utf-8"
    ) as file:
        json.dump(
            final_metadata,
            file,
            indent=2,
            ensure_ascii=False
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
        "QUALITY CONTROL ERFOLGREICH"
    )
    print(
        "5 Clips ausgewählt."
    )
if __name__ == "__main__":
    main()