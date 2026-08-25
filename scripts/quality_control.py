import os
import glob
import json
import shutil
import math

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

    if fps <= 0:
        fps = 30

    duration = frames / fps

    cap.release()

    return {
        "frames": frames,
        "fps": fps,
        "width": width,
        "height": height,
        "duration": duration,
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

    # Histogram
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

    # Zusätzlich kleines Bild-Muster
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


def sample_video(path):

    info = get_video_info(path)

    if info is None:
        return None

    cap = cv2.VideoCapture(path)

    if not cap.isOpened():
        return None

    signatures = []

    sample_count = 8

    for i in range(
        sample_count
    ):

        position = (
            (i + 0.5)
            / sample_count
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

        if not success:
            continue

        signature = frame_signature(
            frame
        )

        signatures.append(
            signature
        )

    cap.release()

    if not signatures:
        return None

    return {
        "info": info,
        "signatures": signatures
    }


def compare_videos(a, b):

    signatures_a = a["signatures"]
    signatures_b = b["signatures"]

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

        distances.append(best)

    if not distances:
        return 999

    return sum(
        distances
    ) / len(distances)


def motion_score(path):

    info = get_video_info(path)

    if not info:
        return 0

    cap = cv2.VideoCapture(path)

    if not cap.isOpened():
        return 0

    previous = None
    differences = []

    for i in range(6):

        position = (
            (i + 0.5)
            / 6
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

        if not success:
            continue

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

            differences.append(
                float(difference)
            )

        previous = gray

    cap.release()

    if not differences:
        return 0

    return sum(
        differences
    ) / len(differences)


def quality_score(path, metadata):

    info = get_video_info(path)

    if info is None:
        return -999

    score = 0

    duration = info["duration"]

    width = info["width"]
    height = info["height"]

    # Fehlerhafte / extrem kurze Videos
    if duration < 8:
        return -999

    if duration >= 10:
        score += 10

    if 12 <= duration <= 45:
        score += 20

    elif 45 < duration <= 60:
        score += 10

    elif duration > 90:
        score -= 15

    # Auflösung
    if width >= 1280:
        score += 10

    if height >= 720:
        score += 5

    # Bewegung / Szenenänderung
    motion = motion_score(path)

    if motion >= 3:
        score += 10

    if motion >= 8:
        score += 10

    # Twitch Views
    views = int(
        metadata.get(
            "view_count",
            0
        )
    )

    score += min(
        views / 1000,
        20
    )

    # Titel
    title = str(
        metadata.get(
            "title",
            ""
        )
    ).lower()

    interesting = [
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
        "chat",
        "bruder",
    ]

    for word in interesting:

        if word in title:

            score += 4

    return score


def main():

    print("================================")
    print("QUALITY CONTROL")
    print("================================")

    os.makedirs(
        FINAL_DIR,
        exist_ok=True
    )

    for old in glob.glob(
        os.path.join(
            FINAL_DIR,
            "*"
        )
    ):

        if os.path.isfile(old):
            os.remove(old)

    with open(
        INPUT_JSON,
        "r",
        encoding="utf-8"
    ) as file:

        candidates = json.load(file)

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
        f"{len(video_files)} Videos "
        "werden analysiert."
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
                f"Überspringe unbekannte Datei: "
                f"{filename}"
            )

            continue

        index = number - 1

        if index < 0 or index >= len(candidates):
            continue

        metadata = candidates[index]

        sampled = sample_video(
            video
        )

        if sampled is None:

            print(
                f"FEHLER: {filename}"
            )

            continue

        score = quality_score(
            video,
            metadata
        )

        analyzed.append({
            "path": video,
            "metadata": metadata,
            "sampled": sampled,
            "score": score,
        })

        print(
            f"{filename} → "
            f"Score {score:.1f}"
        )

    # Beste Kandidaten zuerst
    analyzed.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    selected = []

    # Ähnliche Videos aussortieren
    for candidate in analyzed:

        if candidate["score"] < 5:
            continue

        duplicate = False

        for existing in selected:

            similarity = compare_videos(
                candidate["sampled"],
                existing["sampled"]
            )

            # Niedriger Wert = sehr ähnlich
            if similarity < 0.12:

                duplicate = True

                print(
                    "DUPLIKAT ENTFERNT:"
                )

                print(
                    candidate["metadata"].get(
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
            f"Quality Control konnte nur "
            f"{len(selected)} wirklich "
            f"unterschiedliche brauchbare "
            f"Clips finden."
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
    print("FINALE 5")
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

        clip_id = metadata["id"]

        used.add(
            clip_id
        )

        # Signaturen für spätere Vergleiche speichern.
        signatures = []

        for hist, image in candidate[
            "sampled"
        ]["signatures"]:

            signatures.append({
                "hist": hist.tolist(),
                "image": image.tolist(),
            })

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
            "signatures": signatures,
        }

        final_metadata.append(
            metadata
        )

        print(
            f"{number}. "
            f"{metadata.get('title', '')}"
        )

    # clips_today.json wird auf die finalen 5 reduziert.
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
        sorted(list(used))
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
        "5 unterschiedliche Clips ausgewählt."
    )


if __name__ == "__main__":
    main()