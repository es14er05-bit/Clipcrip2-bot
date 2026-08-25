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
        "duration": duration
    }


def read_sample_frames(path, count=12):

    info = get_video_info(path)

    if not info:
        return [], None

    cap = cv2.VideoCapture(path)

    if not cap.isOpened():
        return [], info

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

    return frames, info


def frame_signature(frame):

    gray = cv2.cvtColor(
        frame,
        cv2.COLOR_BGR2GRAY
    )

    gray = cv2.resize(
        gray,
        (32, 32)
    )

    histogram = cv2.calcHist(
        [gray],
        [0],
        None,
        [32],
        [0, 256]
    )

    cv2.normalize(
        histogram,
        histogram
    )

    small = cv2.resize(
        gray,
        (16, 16)
    ).astype(
        np.float32
    ) / 255.0

    return (
        histogram.flatten(),
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


def video_signature(path):

    frames, info = read_sample_frames(
        path,
        12
    )

    if not frames:
        return None

    return {
        "info": info,
        "signatures": [
            frame_signature(frame)
            for frame in frames
        ]
    }


def compare_videos(a, b):

    if not a or not b:
        return 999

    distances = []

    for sig_a in a["signatures"]:

        best = 999

        for sig_b in b["signatures"]:

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


def motion_score(path):

    frames, _ = read_sample_frames(
        path,
        10
    )

    if len(frames) < 2:
        return 0

    previous = None
    differences = []

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

            diff = np.mean(
                cv2.absdiff(
                    previous,
                    gray
                )
            )

            differences.append(
                float(diff)
            )

        previous = gray

    if not differences:
        return 0

    return float(
        np.mean(differences)
    )


def sharpness_score(path):

    frames, _ = read_sample_frames(
        path,
        8
    )

    if not frames:
        return 0

    scores = []

    for frame in frames:

        gray = cv2.cvtColor(
            frame,
            cv2.COLOR_BGR2GRAY
        )

        scores.append(
            cv2.Laplacian(
                gray,
                cv2.CV_64F
            ).var()
        )

    return float(
        np.mean(scores)
    )


def scene_change_score(path):

    frames, _ = read_sample_frames(
        path,
        12
    )

    if len(frames) < 2:
        return 0

    differences = []

    previous = None

    for frame in frames:

        gray = cv2.cvtColor(
            frame,
            cv2.COLOR_BGR2GRAY
        )

        gray = cv2.resize(
            gray,
            (128, 72)
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

    if not differences:
        return 0

    return float(
        np.mean(differences)
    )


def quality_score(path, metadata):

    info = get_video_info(path)

    if not info:
        return -999

    duration = info["duration"]

    if duration < 8:
        return -999

    score = 0

    # -------------------------------------------------
    # Dauer
    # -------------------------------------------------

    if 12 <= duration <= 45:
        score += 25

    elif 8 <= duration < 12:
        score += 5

    elif 45 < duration <= 60:
        score += 10

    elif duration > 90:
        score -= 20

    # -------------------------------------------------
    # Auflösung
    # -------------------------------------------------

    width = info["width"]
    height = info["height"]

    if width >= 1280:
        score += 10

    if height >= 720:
        score += 5

    # -------------------------------------------------
    # Bewegung
    # -------------------------------------------------

    motion = motion_score(path)

    if motion >= 2:
        score += 5

    if motion >= 5:
        score += 10

    if motion >= 9:
        score += 5

    # -------------------------------------------------
    # Szenenwechsel
    # -------------------------------------------------

    scene = scene_change_score(path)

    if scene >= 3:
        score += 5

    if scene >= 7:
        score += 5

    # -------------------------------------------------
    # Bildschärfe
    # -------------------------------------------------

    sharpness = sharpness_score(path)

    if sharpness >= 80:
        score += 5

    if sharpness >= 200:
        score += 5

    # -------------------------------------------------
    # Twitch Views
    # -------------------------------------------------

    views = int(
        metadata.get(
            "view_count",
            0
        )
    )

    score += min(
        views / 2000,
        15
    )

    # -------------------------------------------------
    # Titel
    # -------------------------------------------------

    title = str(
        metadata.get(
            "title",
            ""
        )
    ).lower()

    keywords = [
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
        "bro",
        "krank",
        "geil",
        "alter"
    ]

    for word in keywords:

        if word in title:

            score += 3

    return score


def find_video_files():

    videos = []

    for extension in (
        "mp4",
        "mkv",
        "webm",
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


def main():

    print("")
    print("================================")
    print("MULTI-STAGE QUALITY CONTROL")
    print("================================")

    os.makedirs(
        FINAL_DIR,
        exist_ok=True
    )

    # Alte Auswahl löschen
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
            "clips_today.json fehlt."
        )

    with open(
        INPUT_JSON,
        "r",
        encoding="utf-8"
    ) as file:

        candidates = json.load(file)

    videos = find_video_files()

    if not videos:

        raise FileNotFoundError(
            "Keine heruntergeladenen "
            "Videos gefunden."
        )

    print(
        f"{len(videos)} Kandidaten "
        "werden geprüft."
    )

    analyzed = []

    # -------------------------------------------------
    # STUFE 1: Technische Analyse
    # -------------------------------------------------

    for video in videos:

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

            continue

        index = number - 1

        if index < 0:
            continue

        if index >= len(candidates):
            continue

        metadata = candidates[index]

        signature = video_signature(
            video
        )

        if not signature:
            continue

        score = quality_score(
            video,
            metadata
        )

        analyzed.append({
            "path": video,
            "metadata": metadata,
            "signature": signature,
            "score": score
        })

        print(
            f"{filename}: "
            f"Score {score:.1f}"
        )

    # -------------------------------------------------
    # STUFE 2: Sortierung
    # -------------------------------------------------

    analyzed.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    # -------------------------------------------------
    # STUFE 3: Ähnliche Clips entfernen
    # -------------------------------------------------

    selected = []

    for candidate in analyzed:

        if candidate["score"] < 15:
            continue

        duplicate = False

        for existing in selected:

            similarity = compare_videos(
                candidate["signature"],
                existing["signature"]
            )

            if similarity < 0.10:

                duplicate = True

                print(
                    "ÄHNLICHER CLIP ENTFERNT: "
                    + candidate["metadata"].get(
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

    # -------------------------------------------------
    # Ergebnis
    # -------------------------------------------------

    if len(selected) < FINAL_COUNT:

        raise RuntimeError(
            "Quality Control konnte keine "
            "5 ausreichend guten und "
            "unterschiedlichen Clips finden."
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
    print("DIE BESTEN 5")
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

        history[clip_id] = {
            "title": metadata.get(
                "title",
                ""
            ),
            "created_at": metadata.get(
                "created_at",
                ""
            ),
            "score": candidate["score"]
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

    save_json(
        USED_FILE,
        sorted(used)
    )

    save_json(
        HISTORY_FILE,
        history
    )

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

    print("")
    print(
        "QUALITY CONTROL ERFOLGREICH."
    )
    print(
        "5 Kandidaten ausgewählt."
    )


if __name__ == "__main__":
    main()