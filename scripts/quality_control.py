"""Precision-first content gate shared by all ClipCrip streamers.

The gate intentionally returns a variable number of videos. Zero strong clips
is a valid, green result; weak material is never added just to hit a quota.
Cheap media analysis runs across the full pool, Whisper is loaded once for a
balanced shortlist, and a transcript-backed content gate decides whether a
clip contains an actual moment. Loud, continuous speech is never sufficient.
"""

from __future__ import annotations

import difflib
import glob
import json
import math
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import cv2
import numpy as np


INPUT_DIR = "downloaded_clips"
FINAL_DIR = "selected_clips"
INPUT_JSON = "clips_today.json"
USED_FILE = "used_clips.json"
HISTORY_FILE = "clip_history.json"
REPORT_FILE = "selection_report.json"

STREAMER_NAME = "Jussef"
WHISPER_MODEL = "turbo"
WHISPER_PROMPT = (
    "Deutscher Twitch-Stream von Jussef. Die Sprecher reden schnell, locker "
    "und umgangssprachlich. Namen und Wörter: Jussef, Yussef, Yavuz, Chat, "
    "Bro, Bruder, Digga, Wallah, crashout. Transkribiere wortgetreu und "
    "behalte Jugendsprache bei."
)

MAX_FINAL_COUNT = 5
SEMANTIC_POOL_SIZE = 14
MIN_VIRAL_SCORE = 68.0
MAX_OUTPUT_DURATION = 30.0
TARGET_EVENT_DURATION = 22.0
MIN_OUTPUT_DURATION = 10.0

SAMPLE_COUNT = 15
VOD_DUPLICATE_WINDOW_SECONDS = 75
LEGACY_HARD_DISTANCE = 0.040
LEGACY_FUZZY_DISTANCE = 0.075


CATEGORY_SIGNALS: dict[str, list[tuple[str, float]]] = {
    "laugh": [
        ("hahahaha", 4.0),
        ("hahaha", 3.2),
        ("haha", 2.0),
        ("ich kann nicht mehr", 3.2),
        ("kann nicht mehr", 2.5),
        ("lach", 2.0),
        ("lustig", 1.5),
    ],
    "rage": [
        ("crashout", 4.0),
        ("rastet aus", 4.0),
        ("ausgerast", 3.5),
        ("halt die fresse", 3.5),
        ("halt dein maul", 3.5),
        ("reicht mir", 2.5),
        ("schrei", 2.2),
        ("rage", 2.5),
    ],
    "surprise": [
        ("oh mein gott", 3.5),
        ("was zur hölle", 3.5),
        ("nicht dein ernst", 3.0),
        ("ist das dein ernst", 3.0),
        ("niemals", 2.5),
        ("wtf", 2.5),
        ("was war das", 2.5),
        ("oha", 1.5),
        ("sprachlos", 2.5),
    ],
    "fail": [
        ("verkackt", 3.5),
        ("reingeschissen", 3.5),
        ("gefailt", 3.0),
        ("nicht geklappt", 2.5),
        ("verloren", 1.5),
        ("gestorben", 1.5),
        ("cooked", 2.5),
        ("fail", 2.0),
    ],
    "chat": [
        ("der chat", 3.0),
        ("mein chat", 3.0),
        ("chat sagt", 3.0),
        ("chat schreibt", 3.0),
        ("trollt", 2.5),
        ("getrollt", 2.5),
        ("donation", 2.0),
        ("spende", 2.0),
    ],
    "roast": [
        ("hops genommen", 4.0),
        ("auseinander genommen", 3.5),
        ("keine antwort", 2.5),
        ("zerlegt", 2.5),
        ("roast", 2.5),
        ("erwischt", 2.0),
    ],
}

STOPWORDS = {
    "aber",
    "auch",
    "dann",
    "dass",
    "denn",
    "der",
    "die",
    "das",
    "eine",
    "einen",
    "einer",
    "für",
    "hab",
    "haben",
    "hier",
    "ich",
    "ist",
    "jetzt",
    "mal",
    "man",
    "mit",
    "nicht",
    "noch",
    "schon",
    "sie",
    "sind",
    "und",
    "von",
    "war",
    "was",
    "wie",
    "wir",
    "zu",
}

GENERIC_TITLES = {"", "clip", "clips", "lol", "haha", "hahaha", "w", "l"}

# These are not banned topics. They are signals that the clip is mostly an
# announcement, follow request or stream administration instead of a payoff.
# A genuinely strong reaction can still override a weak single signal, but the
# run-65 follow/upload clips are intentionally rejected.
PROMO_SIGNALS: list[tuple[str, float]] = [
    ("morgen neuer upload", 4.5),
    ("neuer upload", 3.5),
    ("neues video", 2.5),
    ("video abchecken", 3.0),
    ("alle einmal folgen", 4.0),
    ("einfolgen", 4.0),
    ("folgt ihm", 3.5),
    ("folgt alle", 3.5),
    ("followt", 3.0),
    ("abo da lassen", 3.5),
    ("abonnieren", 3.0),
    ("link in bio", 4.0),
    ("grußvideo", 3.5),
    ("grussvideo", 3.5),
    ("spenden aus", 3.0),
    ("miete zahlen", 2.5),
    ("werbung", 2.5),
    ("sponsor", 2.5),
    ("gewinnspiel", 3.0),
]


def load_json(path: str | Path, default: Any) -> Any:
    file_path = Path(path)
    if not file_path.exists():
        return default
    try:
        with file_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError, TypeError):
        return default


def save_json(path: str | Path, data: Any) -> None:
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with file_path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)


def clean_directory(path: str | Path) -> None:
    directory = Path(path)
    directory.mkdir(parents=True, exist_ok=True)
    for item in directory.iterdir():
        if item.is_file() or item.is_symlink():
            item.unlink()
        elif item.is_dir():
            shutil.rmtree(item)


def get_video_info(path: str | Path) -> dict[str, float] | None:
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        return None
    frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = float(cap.get(cv2.CAP_PROP_FPS)) or 30.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    if frames <= 0 or width <= 0 or height <= 0 or fps <= 0:
        return None
    return {
        "frames": float(frames),
        "fps": fps,
        "width": float(width),
        "height": float(height),
        "duration": frames / fps,
    }


def read_sample_frames(path: str | Path, count: int = SAMPLE_COUNT) -> list[np.ndarray]:
    info = get_video_info(path)
    if not info:
        return []
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        return []
    frames: list[np.ndarray] = []
    total = int(info["frames"])
    for index in range(count):
        frame_number = min(total - 1, int(total * ((index + 0.5) / count)))
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
        ok, frame = cap.read()
        if ok and frame is not None:
            frames.append(frame)
    cap.release()
    return frames


def face_analysis(frames: list[np.ndarray]) -> dict[str, float]:
    if not frames:
        return {"presence": 0.0, "largest": 0.0, "center_stability": 0.0}
    cascade_path = str(Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml")
    detector = cv2.CascadeClassifier(cascade_path)
    if detector.empty():
        return {"presence": 0.0, "largest": 0.0, "center_stability": 0.0}

    detected = 0
    largest_ratios: list[float] = []
    centers: list[float] = []
    for frame in frames:
        height, width = frame.shape[:2]
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        scale = min(1.0, 640.0 / max(width, 1))
        if scale < 1.0:
            gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        faces = detector.detectMultiScale(
            gray,
            scaleFactor=1.12,
            minNeighbors=5,
            minSize=(28, 28),
        )
        if len(faces) == 0:
            continue
        x, y, w, h = max(faces, key=lambda box: box[2] * box[3])
        detected += 1
        area_ratio = (w * h) / max(gray.shape[0] * gray.shape[1], 1)
        largest_ratios.append(float(area_ratio))
        centers.append(float((x + w / 2) / max(gray.shape[1], 1)))

    presence = detected / max(len(frames), 1)
    largest = max(largest_ratios, default=0.0)
    stability = 0.0
    if len(centers) >= 2:
        stability = max(0.0, 1.0 - float(np.std(centers)) * 4.0)
    return {
        "presence": float(presence),
        "largest": float(largest),
        "center_stability": float(stability),
    }


def motion_analysis(frames: list[np.ndarray]) -> dict[str, float]:
    if len(frames) < 2:
        return {"average": 0.0, "peak": 0.0}
    values: list[float] = []
    previous: np.ndarray | None = None
    for frame in frames:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.resize(gray, (192, 108), interpolation=cv2.INTER_AREA)
        gray = cv2.GaussianBlur(gray, (5, 5), 0)
        if previous is not None:
            values.append(float(np.mean(cv2.absdiff(previous, gray))))
        previous = gray
    return {
        "average": float(np.mean(values)) if values else 0.0,
        "peak": float(np.percentile(values, 90)) if values else 0.0,
    }


def sharpness_analysis(frames: list[np.ndarray]) -> float:
    if not frames:
        return 0.0
    values = [
        float(cv2.Laplacian(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var())
        for frame in frames
    ]
    return float(np.median(values))


def audio_analysis(path: str | Path) -> dict[str, Any]:
    command = [
        "ffmpeg",
        "-v",
        "error",
        "-i",
        str(path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-f",
        "s16le",
        "-",
    ]
    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=90,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"present": False, "energy": 0.0, "peakiness": 0.0}
    if result.returncode != 0 or not result.stdout:
        return {"present": False, "energy": 0.0, "peakiness": 0.0}

    samples = np.frombuffer(result.stdout, dtype=np.int16).astype(np.float32) / 32768.0
    if samples.size < 4000:
        return {"present": False, "energy": 0.0, "peakiness": 0.0}

    window = 4000
    rms_values: list[float] = []
    for start in range(0, samples.size - window + 1, window):
        chunk = samples[start : start + window]
        rms_values.append(float(np.sqrt(np.mean(chunk * chunk) + 1e-9)))
    rms = np.asarray(rms_values, dtype=np.float32)
    average = float(np.mean(rms))
    percentile_90 = float(np.percentile(rms, 90))
    deviation = float(np.std(rms))
    activity_threshold = max(0.012, float(np.median(rms)) * 0.55)
    activity = float(np.mean(rms >= activity_threshold))
    silence_ratio = float(np.mean(rms < 0.008))
    opening_windows = max(1, min(len(rms), 6))
    opening_average = float(np.mean(rms[:opening_windows]))
    opening_activity = min(1.0, opening_average / max(average * 1.15, 0.025))
    peakiness = min(1.0, ((percentile_90 - average) + deviation) / 0.09)
    energy = min(1.0, average / 0.095)
    peak_index = int(np.argmax(rms)) if rms.size else 0
    peak_time = peak_index * (window / 16000.0) + (window / 32000.0)
    clipping = float(np.mean(np.abs(samples) >= 0.985))

    return {
        "present": True,
        "energy": energy,
        "peakiness": peakiness,
        "activity": activity,
        "silence_ratio": silence_ratio,
        "opening_activity": opening_activity,
        "peak_time": peak_time,
        "clipping_ratio": clipping,
        "rms_average": average,
        "timeline": [round(float(value), 6) for value in rms_values],
        "window_seconds": window / 16000.0,
    }


def dhash(frame: np.ndarray) -> str:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    resized = cv2.resize(gray, (9, 8), interpolation=cv2.INTER_AREA)
    bits = (resized[:, 1:] > resized[:, :-1]).flatten()
    value = 0
    for bit in bits:
        value = (value << 1) | int(bit)
    return f"{value:016x}"


def create_frame_hashes(frames: list[np.ndarray]) -> list[str]:
    return [dhash(frame) for frame in frames[::2]]


def hamming_fraction(value_a: str, value_b: str) -> float:
    try:
        return (int(value_a, 16) ^ int(value_b, 16)).bit_count() / 64.0
    except (TypeError, ValueError):
        return 1.0


def aligned_hash_distance(hashes_a: list[str], hashes_b: list[str]) -> float:
    if not hashes_a or not hashes_b:
        return 1.0
    count = min(len(hashes_a), len(hashes_b))
    if count <= 0:
        return 1.0
    distances = []
    for index in range(count):
        pos_a = round(index * (len(hashes_a) - 1) / max(count - 1, 1))
        pos_b = round(index * (len(hashes_b) - 1) / max(count - 1, 1))
        distances.append(hamming_fraction(hashes_a[pos_a], hashes_b[pos_b]))
    return float(np.median(distances))


def create_legacy_signature(frames: list[np.ndarray]) -> list[tuple[np.ndarray, np.ndarray]]:
    signatures: list[tuple[np.ndarray, np.ndarray]] = []
    for frame in frames[::2]:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        small = cv2.resize(gray, (24, 24), interpolation=cv2.INTER_AREA).astype(
            np.float32
        ) / 255.0
        hist = cv2.calcHist([gray], [0], None, [32], [0, 256])
        cv2.normalize(hist, hist)
        signatures.append((hist.flatten(), small.flatten()))
    return signatures


def legacy_signature_from_json(entry: dict[str, Any]) -> list[tuple[np.ndarray, np.ndarray]]:
    stored = entry.get("signatures", []) if isinstance(entry, dict) else []
    result: list[tuple[np.ndarray, np.ndarray]] = []
    if not isinstance(stored, list):
        return result
    for item in stored:
        if not isinstance(item, dict):
            continue
        try:
            hist = np.asarray(item["hist"], dtype=np.float32).flatten()
            image = np.asarray(item["image"], dtype=np.float32).flatten()
            side = int(round(math.sqrt(image.size)))
            if side * side != image.size or hist.size == 0:
                continue
            normalized = cv2.resize(
                image.reshape(side, side), (24, 24), interpolation=cv2.INTER_AREA
            ).flatten()
            result.append((hist, normalized))
        except (KeyError, TypeError, ValueError):
            continue
    return result


def legacy_aligned_distance(
    signature_a: list[tuple[np.ndarray, np.ndarray]],
    signature_b: list[tuple[np.ndarray, np.ndarray]],
) -> float:
    if not signature_a or not signature_b:
        return 1.0
    count = min(len(signature_a), len(signature_b))
    distances: list[float] = []
    for index in range(count):
        pos_a = round(index * (len(signature_a) - 1) / max(count - 1, 1))
        pos_b = round(index * (len(signature_b) - 1) / max(count - 1, 1))
        hist_a, image_a = signature_a[pos_a]
        hist_b, image_b = signature_b[pos_b]
        hist_distance = 1.0
        if hist_a.size == hist_b.size:
            hist_distance = float(
                cv2.compareHist(hist_a, hist_b, cv2.HISTCMP_BHATTACHARYYA)
            )
        image_distance = float(np.mean(np.abs(image_a - image_b)))
        distances.append(hist_distance * 0.40 + image_distance * 0.60)
    return float(np.median(distances))


def normalize_text(value: Any) -> str:
    text = re.sub(r"[^a-z0-9äöüß' -]+", " ", str(value or "").lower())
    return re.sub(r"\s+", " ", text).strip()


def content_tokens(value: Any) -> set[str]:
    return {
        token
        for token in normalize_text(value).split()
        if len(token) >= 3 and token not in STOPWORDS
    }


def transcript_similarity(value_a: Any, value_b: Any) -> float:
    tokens_a = content_tokens(value_a)
    tokens_b = content_tokens(value_b)
    if len(tokens_a) < 3 or len(tokens_b) < 3:
        return 0.0
    return len(tokens_a & tokens_b) / max(len(tokens_a | tokens_b), 1)


def meaningful_title_similarity(value_a: Any, value_b: Any) -> float:
    title_a = normalize_text(value_a)
    title_b = normalize_text(value_b)
    if (
        title_a in GENERIC_TITLES
        or title_b in GENERIC_TITLES
        or len(title_a) < 6
        or len(title_b) < 6
    ):
        return 0.0
    return difflib.SequenceMatcher(None, title_a, title_b).ratio()


def same_vod_region(metadata: dict[str, Any], entry: dict[str, Any]) -> bool:
    video_id = str(metadata.get("video_id", "")).strip()
    old_video_id = str(entry.get("video_id", "")).strip()
    if not video_id or video_id != old_video_id:
        return False
    try:
        offset = int(metadata.get("vod_offset"))
        old_offset = int(entry.get("vod_offset"))
    except (TypeError, ValueError):
        return False
    return abs(offset - old_offset) <= VOD_DUPLICATE_WINDOW_SECONDS


def duplicate_reason(candidate: dict[str, Any], entry: dict[str, Any]) -> str | None:
    if same_vod_region(candidate["metadata"], entry):
        return "gleiche VOD-Position"

    new_hashes = candidate.get("frame_hashes", [])
    old_hashes = entry.get("frame_hashes", []) if isinstance(entry, dict) else []
    if isinstance(old_hashes, list) and old_hashes:
        visual = aligned_hash_distance(new_hashes, old_hashes)
        text = transcript_similarity(
            candidate.get("transcript_text", ""),
            entry.get("transcript_excerpt", ""),
        )
        title = meaningful_title_similarity(
            candidate["metadata"].get("title", ""), entry.get("title", "")
        )
        # A repeated stream layout can produce almost identical frames while
        # the conversation is completely different. Visual similarity alone
        # is therefore never enough for a cross-ID duplicate decision.
        if visual <= 0.035 and (text >= 0.25 or title >= 0.75):
            return f"Frames+Inhalt ({visual:.3f}/{max(text, title):.2f})"
        if visual <= 0.11 and text >= 0.52:
            return f"Frames+Transkript ({visual:.3f}/{text:.2f})"
        if visual <= 0.14 and title >= 0.92:
            return f"Frames+Titel ({visual:.3f}/{title:.2f})"

    old_legacy = legacy_signature_from_json(entry)
    if old_legacy:
        legacy = legacy_aligned_distance(candidate.get("legacy_signature", []), old_legacy)
        title = meaningful_title_similarity(
            candidate["metadata"].get("title", ""), entry.get("title", "")
        )
        # Legacy history has no transcript. Requiring a meaningful matching
        # title prevents the old common-layout false positives from returning.
        if legacy <= LEGACY_HARD_DISTANCE and title >= 0.75:
            return f"Legacy-Frames+Titel ({legacy:.3f}/{title:.2f})"
        if legacy <= LEGACY_FUZZY_DISTANCE and title >= 0.92:
            return f"Legacy-Frames+Titel ({legacy:.3f}/{title:.2f})"

    return None


def preliminary_score(result: dict[str, Any]) -> tuple[float, dict[str, float], list[str]]:
    audio = result["audio"]
    motion = result["motion"]
    face = result["face"]
    info = result["info"]
    metadata = result["metadata"]
    warnings: list[str] = []

    # Twitch audio is commonly normalized and made the old values saturate at
    # 1.0. Keep media signals useful for triage, but cap their influence. The
    # transcript-backed content gate below owns the publish decision.
    metadata_points = min(20.0, float(metadata.get("metadata_score", 0.0)) / 2.7)
    energy_points = float(audio.get("energy", 0.0)) * 4.0
    peak_points = float(audio.get("peakiness", 0.0)) * 8.0
    activity_points = float(audio.get("activity", 0.0)) * 4.0
    opening_points = float(audio.get("opening_activity", 0.0)) * 4.0
    motion_points = min(1.0, float(motion.get("peak", 0.0)) / 24.0) * 8.0
    face_points = min(
        1.0,
        float(face.get("presence", 0.0)) * 0.70
        + min(1.0, float(face.get("largest", 0.0)) / 0.055) * 0.30,
    ) * 5.0
    sharpness_points = min(1.0, float(result["sharpness"]) / 140.0) * 5.0

    duration = float(info["duration"])
    if 12.0 <= duration <= 45.0:
        duration_points = 8.0
    elif 8.0 <= duration <= 60.5:
        duration_points = 4.0
    else:
        duration_points = 0.0

    penalties = 0.0
    if not audio.get("present"):
        penalties += 35.0
        warnings.append("kein Audio")
    if float(audio.get("silence_ratio", 1.0)) > 0.72:
        penalties += 24.0
        warnings.append("zu viel Stille")
    if (
        float(audio.get("peakiness", 0.0)) < 0.18
        and float(audio.get("energy", 0.0)) < 0.28
        and float(motion.get("peak", 0.0)) < 5.0
    ):
        penalties += 28.0
        warnings.append("audio-visuell ereignisarm")
    if float(audio.get("opening_activity", 0.0)) < 0.22:
        penalties += 8.0
        warnings.append("schwacher Einstieg")
    if float(audio.get("clipping_ratio", 0.0)) > 0.02:
        penalties += 5.0
        warnings.append("Audio übersteuert")
    if float(result["sharpness"]) < 35.0:
        penalties += 5.0
        warnings.append("unscharf")

    breakdown = {
        "metadata": metadata_points,
        "audio_energy": energy_points,
        "audio_dynamics": peak_points,
        "audio_activity": activity_points,
        "opening": opening_points,
        "motion": motion_points,
        "face": face_points,
        "sharpness": sharpness_points,
        "duration": duration_points,
        "penalties": -penalties,
    }
    score = sum(breakdown.values())
    return round(score, 3), {key: round(value, 3) for key, value in breakdown.items()}, warnings


def analyze_video(path: str | Path, metadata: dict[str, Any]) -> dict[str, Any] | None:
    info = get_video_info(path)
    frames = read_sample_frames(path)
    if not info or not frames:
        return None
    result: dict[str, Any] = {
        "path": str(path),
        "metadata": metadata,
        "info": info,
        "face": face_analysis(frames),
        "motion": motion_analysis(frames),
        "audio": audio_analysis(path),
        "sharpness": sharpness_analysis(frames),
        "frame_hashes": create_frame_hashes(frames),
        "legacy_signature": create_legacy_signature(frames),
        "transcript_text": "",
        "transcript": None,
        "category": "",
        "category_strength": 0.0,
    }
    score, breakdown, warnings = preliminary_score(result)
    result["preliminary_score"] = score
    result["score_breakdown"] = breakdown
    result["warnings"] = warnings
    result["hard_reject"] = (
        not bool(result["audio"].get("present"))
        or float(result["info"]["duration"]) < 8.0
        or (
            float(result["audio"].get("silence_ratio", 1.0)) > 0.82
            and float(result["motion"].get("peak", 0.0)) < 7.0
        )
    )
    return result


def compact_transcript(raw: dict[str, Any]) -> dict[str, Any]:
    segments: list[dict[str, Any]] = []
    for segment in raw.get("segments", []):
        if not isinstance(segment, dict):
            continue
        words: list[dict[str, Any]] = []
        for word in segment.get("words", []) or []:
            if not isinstance(word, dict):
                continue
            words.append(
                {
                    "word": str(word.get("word", "")),
                    "start": round(float(word.get("start", 0.0)), 3),
                    "end": round(float(word.get("end", 0.0)), 3),
                }
            )
        segments.append(
            {
                "start": round(float(segment.get("start", 0.0)), 3),
                "end": round(float(segment.get("end", 0.0)), 3),
                "text": str(segment.get("text", "")).strip(),
                "words": words,
            }
        )
    return {"text": str(raw.get("text", "")).strip(), "segments": segments}


def load_whisper_model():
    import whisper

    print(f"Whisper-Modell wird einmal geladen: {WHISPER_MODEL}")
    return whisper.load_model(WHISPER_MODEL)


def transcribe_candidate(model: Any, candidate: dict[str, Any]) -> dict[str, Any]:
    raw = model.transcribe(
        candidate["path"],
        language="de",
        task="transcribe",
        word_timestamps=True,
        initial_prompt=WHISPER_PROMPT,
        temperature=0.0,
        condition_on_previous_text=False,
        fp16=False,
        verbose=False,
    )
    return compact_transcript(raw)


def score_signals(text: str) -> dict[str, float]:
    normalized = normalize_text(text)
    return {
        category: sum(weight for phrase, weight in signals if phrase in normalized)
        for category, signals in CATEGORY_SIGNALS.items()
    }


def phrase_score(text: str, signals: list[tuple[str, float]]) -> float:
    normalized = normalize_text(text)
    return sum(weight for phrase, weight in signals if phrase in normalized)


def audience_quality(metadata: dict[str, Any]) -> float:
    """Return a streamer-independent 0..1 audience-evidence score."""

    breakdown = metadata.get("metadata_score_breakdown", {})
    if not isinstance(breakdown, dict):
        breakdown = {}
    views = min(1.0, max(0.0, float(breakdown.get("views", 0.0))) / 24.0)
    velocity = min(
        1.0, max(0.0, float(breakdown.get("view_velocity", 0.0))) / 18.0
    )
    return views * 0.60 + velocity * 0.40


def meaningful_title(value: Any) -> bool:
    title = normalize_text(value)
    words = title.split()
    return title not in GENERIC_TITLES and len(title) >= 7 and 2 <= len(words) <= 10


def strongest_segment_signal(
    candidate: dict[str, Any], category: str = ""
) -> tuple[float, float | None]:
    transcript = candidate.get("transcript") or {}
    best_score = 0.0
    best_time: float | None = None
    for segment in transcript.get("segments", []) if isinstance(transcript, dict) else []:
        scores = score_signals(str(segment.get("text", "")))
        score = scores.get(category, 0.0) if category else max(scores.values(), default=0.0)
        if score > best_score:
            best_score = score
            best_time = (
                float(segment.get("start", 0.0)) + float(segment.get("end", 0.0))
            ) / 2
    return best_score, best_time


def evaluate_content_gate(candidate: dict[str, Any]) -> tuple[bool, str, dict[str, Any]]:
    """Demand evidence of a real, understandable moment before publishing."""

    text = str(candidate.get("transcript_text", ""))
    words = normalize_text(text).split()
    content_word_list = [
        word for word in words if len(word) >= 3 and word not in STOPWORDS
    ]
    unique_content_words = set(content_word_list)
    content_diversity = len(unique_content_words) / max(len(content_word_list), 1)
    metadata = candidate["metadata"]
    duration = float(candidate["info"]["duration"])
    category = str(candidate.get("category", ""))
    transcript_strength = float(candidate.get("transcript_category_strength", 0.0))
    title_strength = float(candidate.get("title_category_strength", 0.0))
    event_score, event_time = strongest_segment_signal(candidate, category)
    promo_strength = phrase_score(text, PROMO_SIGNALS)
    audience = audience_quality(metadata)
    try:
        views = int(metadata.get("view_count", 0) or 0)
    except (TypeError, ValueError):
        views = 0

    reaction_route = transcript_strength >= 4.5 or (
        transcript_strength >= 3.5 and title_strength >= 2.0
    )
    audience_transcript_ok = (
        len(unique_content_words) >= 7 and content_diversity >= 0.22
    )
    audience_route = (
        audience >= 0.68
        and views >= 500
        and meaningful_title(metadata.get("title", ""))
        and duration <= 40.0
        and audience_transcript_ok
    )

    details = {
        "reaction_route": reaction_route,
        "audience_route": audience_route,
        "audience_quality": round(audience, 3),
        "transcript_reaction": round(transcript_strength, 3),
        "title_reaction": round(title_strength, 3),
        "event_score": round(event_score, 3),
        "event_time": None if event_time is None else round(event_time, 3),
        "promo_strength": round(promo_strength, 3),
        "word_count": len(words),
        "unique_content_words": len(unique_content_words),
        "content_diversity": round(content_diversity, 3),
    }

    if len(words) < 10 or float(candidate.get("speech_ratio", 0.0)) < 0.18:
        return False, "zu wenig verständlicher Inhalt", details
    if promo_strength >= 3.5 and transcript_strength < 6.5:
        return False, "hauptsächlich Follow-, Upload- oder Stream-Logistik", details
    if not reaction_route and not audience_transcript_ok:
        return False, "zu repetitives oder unverständliches Transkript", details
    if not reaction_route and not audience_route:
        return False, "kein klarer starker Moment oder belastbares Zuschauer-Signal", details
    if reaction_route and event_time is not None and event_time > duration - 1.8:
        return False, "Reaktion kommt erst am Ende; kein sichtbarer Payoff", details
    if duration > 34.0 and not reaction_route and audience < 0.78:
        return False, "zu lang und ohne klar lokalisierbares Ereignis", details
    return True, "reaction" if reaction_route else "audience_proven", details


def semantic_analysis(candidate: dict[str, Any]) -> tuple[float, dict[str, float]]:
    transcript = candidate.get("transcript") or {"text": "", "segments": []}
    text = str(transcript.get("text", ""))
    normalized = normalize_text(text)
    words = normalized.split()
    segments = transcript.get("segments", []) if isinstance(transcript, dict) else []
    title = str(candidate["metadata"].get("title", ""))
    transcript_scores = score_signals(text)
    title_scores = score_signals(title)
    combined_scores = {
        category: transcript_scores.get(category, 0.0)
        + min(2.0, title_scores.get(category, 0.0) * 0.60)
        for category in CATEGORY_SIGNALS
    }
    category = max(combined_scores, key=combined_scores.get) if combined_scores else ""
    category_strength = combined_scores.get(category, 0.0) if category else 0.0
    transcript_strength = transcript_scores.get(category, 0.0) if category else 0.0
    title_strength = title_scores.get(category, 0.0) if category else 0.0

    first_speech = 999.0
    last_speech = 0.0
    speech_seconds = 0.0
    for segment in segments:
        try:
            start = float(segment.get("start", 0.0))
            end = float(segment.get("end", start))
        except (TypeError, ValueError):
            continue
        if str(segment.get("text", "")).strip():
            first_speech = min(first_speech, start)
            last_speech = max(last_speech, end)
            speech_seconds += max(0.0, end - start)

    duration = max(float(candidate["info"]["duration"]), 0.1)
    speech_ratio = min(1.0, speech_seconds / duration)
    reaction_points = min(22.0, transcript_strength * 3.0)
    context_points = min(4.0, len(words) / 12.0)
    speech_points = min(3.0, speech_ratio * 4.0)
    opening_points = 3.0 if first_speech <= 0.65 else max(0.0, 3.0 - first_speech * 1.2)
    diversity_points = min(1.5, len(content_tokens(text)) / 20.0)
    audience_points = audience_quality(candidate["metadata"]) * 8.0

    candidate["transcript_text"] = text
    candidate["category"] = category if category_strength >= 2.2 else ""
    candidate["category_strength"] = category_strength
    candidate["transcript_category_strength"] = transcript_strength
    candidate["title_category_strength"] = title_strength
    candidate["speech_start"] = 0.0 if first_speech == 999.0 else first_speech
    candidate["speech_end"] = last_speech
    candidate["speech_ratio"] = speech_ratio
    candidate["signal_scores"] = combined_scores

    if len(words) < 5 and float(candidate["audio"].get("peakiness", 0.0)) < 0.70:
        candidate["warnings"].append("zu wenig verständlicher Inhalt")
    if first_speech > 1.6:
        candidate["warnings"].append("Sprache startet zu spät")

    gate_passed, gate_reason, gate_details = evaluate_content_gate(candidate)
    candidate["content_gate_passed"] = gate_passed
    candidate["content_gate_reason"] = gate_reason
    candidate["content_gate"] = gate_details

    event_bonus = 6.0 if gate_passed and gate_reason == "reaction" else 0.0
    if gate_passed and gate_reason == "audience_proven":
        event_bonus = 4.0
    promo_penalty = min(20.0, float(gate_details["promo_strength"]) * 3.0)
    ramble_penalty = 8.0 if duration > 32.0 and transcript_strength < 4.0 else 0.0
    late_speech_penalty = (
        min(10.0, (first_speech - 1.6) * 3.0) if first_speech > 1.6 else 0.0
    )
    semantic_points = (
        reaction_points
        + context_points
        + speech_points
        + opening_points
        + diversity_points
        + audience_points
        + event_bonus
        - promo_penalty
        - ramble_penalty
        - late_speech_penalty
    )
    if not gate_passed:
        candidate["warnings"].append("Content Gate: " + gate_reason)

    breakdown = {
        "reaction": reaction_points,
        "context": context_points,
        "speech": speech_points,
        "spoken_opening": opening_points,
        "word_diversity": diversity_points,
        "audience_evidence": audience_points,
        "event_bonus": event_bonus,
        "promo_penalty": -promo_penalty,
        "ramble_penalty": -ramble_penalty,
        "late_speech_penalty": -late_speech_penalty,
    }
    return round(semantic_points, 3), {
        key: round(value, 3) for key, value in breakdown.items()
    }


def strongest_segment_time(candidate: dict[str, Any]) -> float | None:
    return strongest_segment_signal(candidate, str(candidate.get("category", "")))[1]


def choose_trim_window(candidate: dict[str, Any]) -> tuple[float, float]:
    duration = float(candidate["info"]["duration"])
    speech_start = float(candidate.get("speech_start", 0.0))
    speech_end = float(candidate.get("speech_end", 0.0))
    start = max(0.0, speech_start - 0.35) if speech_start > 0.55 else 0.0
    end = duration
    if speech_end > 0.0 and duration - speech_end > 1.0:
        end = min(duration, speech_end + 0.65)

    event_time = strongest_segment_time(candidate)
    if end - start <= MAX_OUTPUT_DURATION and event_time is None:
        if end - start < MIN_OUTPUT_DURATION:
            end = min(duration, start + MIN_OUTPUT_DURATION)
            start = max(0.0, end - MIN_OUTPUT_DURATION)
        return round(start, 3), round(end, 3)

    if event_time is None:
        event_time = float(candidate["audio"].get("peak_time", duration / 2.0))
    target_duration = min(MAX_OUTPUT_DURATION, max(MIN_OUTPUT_DURATION, TARGET_EVENT_DURATION))
    start = max(0.0, min(duration - target_duration, event_time - 7.0))
    if speech_start > start and speech_start - start < 2.0:
        start = max(0.0, speech_start - 0.35)
    end = min(duration, start + target_duration)
    return round(start, 3), round(end, 3)


def enrich_with_transcripts(analyzed: list[dict[str, Any]]) -> bool:
    pool = [item for item in analyzed if not item["hard_reject"]]
    by_media = sorted(pool, key=lambda item: item["preliminary_score"], reverse=True)
    by_audience = sorted(
        pool,
        key=lambda item: (
            float(item["metadata"].get("metadata_score", 0.0)),
            int(item["metadata"].get("view_count", 0) or 0),
        ),
        reverse=True,
    )
    balanced: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index in range(max(len(by_media), len(by_audience))):
        for ranking in (by_audience, by_media):
            if index >= len(ranking):
                continue
            item = ranking[index]
            identity = str(item["metadata"].get("id", item["path"]))
            if identity in seen:
                continue
            seen.add(identity)
            balanced.append(item)
            if len(balanced) >= SEMANTIC_POOL_SIZE:
                break
        if len(balanced) >= SEMANTIC_POOL_SIZE:
            break
    pool = balanced
    if not pool:
        return False

    try:
        model = load_whisper_model()
    except Exception as error:
        print(f"WARNUNG: Whisper-Modell konnte nicht geladen werden: {error}")
        return False

    for index, candidate in enumerate(pool, start=1):
        print(
            f"TRANSKRIPTION {index}/{len(pool)} | "
            f"Pre-Score {candidate['preliminary_score']:.1f} | "
            f"{candidate['metadata'].get('title', '')}"
        )
        try:
            candidate["transcript"] = transcribe_candidate(model, candidate)
            semantic_score, semantic_breakdown = semantic_analysis(candidate)
            candidate["semantic_score"] = semantic_score
            candidate["score_breakdown"].update(semantic_breakdown)
            candidate["viral_score"] = round(
                candidate["preliminary_score"] + semantic_score, 3
            )
        except Exception as error:
            candidate["warnings"].append(f"Transkription fehlgeschlagen: {error}")
            candidate["semantic_score"] = 0.0
            candidate["viral_score"] = candidate["preliminary_score"]
    return True


def select_candidates(
    analyzed: list[dict[str, Any]], history: dict[str, Any], transcripts_available: bool
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    threshold = MIN_VIRAL_SCORE
    for candidate in analyzed:
        candidate.setdefault("viral_score", candidate["preliminary_score"])
        candidate.setdefault("semantic_score", 0.0)
        candidate["trim_start"], candidate["trim_end"] = choose_trim_window(candidate)

    ranked = sorted(analyzed, key=lambda item: item["viral_score"], reverse=True)
    selected: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for candidate in ranked:
        reason = ""
        if candidate["hard_reject"]:
            reason = "Hard Reject"
        elif not transcripts_available:
            reason = "Whisper nicht verfügbar; keine blinde Veröffentlichung"
        elif not candidate.get("transcript"):
            reason = "nicht im ausgewogenen semantischen Prüfpool"
        elif not candidate.get("content_gate_passed", False):
            reason = "Content Gate: " + str(
                candidate.get("content_gate_reason", "kein klarer Moment")
            )
        elif candidate["viral_score"] < threshold:
            reason = f"unter Mindestscore {threshold:.1f}"
        else:
            for existing in selected:
                duplicate = duplicate_reason(candidate, history_entry(existing))
                if duplicate:
                    reason = f"Duplikat aktueller Run: {duplicate}"
                    break
            if not reason:
                for old_id, entry in history.items():
                    if not isinstance(entry, dict):
                        continue
                    duplicate = duplicate_reason(candidate, entry)
                    if duplicate:
                        reason = f"History-Duplikat {old_id}: {duplicate}"
                        break
            if not reason and len(selected) >= MAX_FINAL_COUNT:
                reason = "qualifiziert, aber außerhalb der stärksten Top 5"

        if reason:
            rejected.append(
                {
                    "id": candidate["metadata"].get("id", ""),
                    "title": candidate["metadata"].get("title", ""),
                    "viral_score": round(float(candidate["viral_score"]), 3),
                    "preliminary_score": round(
                        float(candidate.get("preliminary_score", 0.0)), 3
                    ),
                    "semantic_score": round(
                        float(candidate.get("semantic_score", 0.0)), 3
                    ),
                    "reason": reason,
                    "warnings": candidate["warnings"],
                    "content_gate": candidate.get("content_gate", {}),
                }
            )
            continue

        selected.append(candidate)

    return selected, rejected


def history_entry(candidate: dict[str, Any]) -> dict[str, Any]:
    metadata = candidate["metadata"]
    transcript = candidate.get("transcript_text", "")
    return {
        "clip_id": str(metadata.get("id", "")),
        "title": metadata.get("title", ""),
        "created_at": metadata.get("created_at", ""),
        "duration": metadata.get("duration", candidate["info"]["duration"]),
        "video_id": metadata.get("video_id", ""),
        "vod_offset": metadata.get("vod_offset"),
        "viral_score": round(float(candidate.get("viral_score", 0.0)), 3),
        "preliminary_score": round(float(candidate.get("preliminary_score", 0.0)), 3),
        "category": candidate.get("category", ""),
        "category_strength": round(float(candidate.get("category_strength", 0.0)), 3),
        "content_gate_reason": candidate.get("content_gate_reason", ""),
        "trim_start": candidate.get("trim_start", 0.0),
        "trim_end": candidate.get("trim_end", candidate["info"]["duration"]),
        "audio_energy": round(float(candidate["audio"].get("energy", 0.0)), 4),
        "audio_dynamics": round(float(candidate["audio"].get("peakiness", 0.0)), 4),
        "audio_activity": round(float(candidate["audio"].get("activity", 0.0)), 4),
        "motion_peak": round(float(candidate["motion"].get("peak", 0.0)), 4),
        "face_presence": round(float(candidate["face"].get("presence", 0.0)), 4),
        "frame_hashes": candidate.get("frame_hashes", []),
        "transcript_excerpt": transcript[:900],
        "fingerprint_version": 4,
    }


def metadata_for_output(candidate: dict[str, Any], output_number: int) -> dict[str, Any]:
    metadata = dict(candidate["metadata"])
    metadata.update(
        {
            "output_number": output_number,
            "viral_score": round(float(candidate["viral_score"]), 3),
            "preliminary_score": round(float(candidate["preliminary_score"]), 3),
            "semantic_score": round(float(candidate.get("semantic_score", 0.0)), 3),
            "score_breakdown": candidate["score_breakdown"],
            "hook_category": candidate.get("category", ""),
            "hook_confidence": min(
                1.0, float(candidate.get("transcript_category_strength", 0.0)) / 7.0
            ),
            "content_gate": candidate.get("content_gate", {}),
            "content_gate_reason": candidate.get("content_gate_reason", ""),
            "trim_start": candidate["trim_start"],
            "trim_end": candidate["trim_end"],
            "selected_by": "viral_quality_gate_v4_precision_first",
        }
    )
    return metadata


def find_input_videos() -> list[Path]:
    videos: list[Path] = []
    for extension in ("mp4", "webm", "mkv", "mov", "m4v"):
        videos.extend(Path(path) for path in glob.glob(str(Path(INPUT_DIR) / f"*.{extension}")))

    def number(path: Path) -> int:
        match = re.search(r"clip_(\d+)", path.stem, re.IGNORECASE)
        return int(match.group(1)) if match else 999999

    return sorted(set(videos), key=lambda path: (number(path), path.name.lower()))


def candidate_index(path: Path) -> int | None:
    match = re.search(r"clip_(\d+)", path.stem, re.IGNORECASE)
    return int(match.group(1)) - 1 if match else None


def main() -> None:
    print("=" * 64)
    print(f"CLIPCRIP VIRAL QUALITY GATE V4 | {STREAMER_NAME}")
    print("Variable Ausgabe: 0 bis 5; kein erzwungener Füll-Clip")
    print("=" * 64)

    clean_directory(FINAL_DIR)
    candidates = load_json(INPUT_JSON, [])
    if not isinstance(candidates, list):
        raise RuntimeError(f"{INPUT_JSON} ist keine Liste.")

    if not candidates:
        save_json(INPUT_JSON, [])
        save_json(
            REPORT_FILE,
            {
                "streamer": STREAMER_NAME,
                "status": "no_candidates",
                "selected_count": 0,
                "selected": [],
                "rejected": [],
            },
        )
        print("Keine Kandidaten. Der Run endet erfolgreich ohne Output.")
        return

    videos = find_input_videos()
    analyzed: list[dict[str, Any]] = []
    for path in videos:
        index = candidate_index(path)
        if index is None or index < 0 or index >= len(candidates):
            print(f"Übersprungen ohne passende Metadaten: {path.name}")
            continue
        metadata = candidates[index]
        if not isinstance(metadata, dict):
            continue
        result = analyze_video(path, metadata)
        if result:
            analyzed.append(result)
            print(
                f"MEDIA {path.name} | {result['preliminary_score']:5.1f} | "
                f"Audio {result['audio'].get('peakiness', 0.0):.2f} | "
                f"Opening {result['audio'].get('opening_activity', 0.0):.2f} | "
                f"{metadata.get('title', '')}"
            )

    if not analyzed:
        raise RuntimeError("Kein heruntergeladenes Video konnte analysiert werden.")

    transcripts_available = enrich_with_transcripts(analyzed)
    history_raw = load_json(HISTORY_FILE, {})
    history = history_raw if isinstance(history_raw, dict) else {}
    selected, rejected = select_candidates(analyzed, history, transcripts_available)

    used_raw = load_json(USED_FILE, [])
    used = {str(value) for value in used_raw} if isinstance(used_raw, list) else set()
    final_metadata: list[dict[str, Any]] = []
    selected_report: list[dict[str, Any]] = []

    for output_number, candidate in enumerate(selected, start=1):
        source = Path(candidate["path"])
        destination = Path(FINAL_DIR) / f"clip_{output_number}.mp4"
        transcript_destination = Path(FINAL_DIR) / f"clip_{output_number}.transcript.json"
        shutil.copy2(source, destination)
        if candidate.get("transcript"):
            save_json(transcript_destination, candidate["transcript"])

        metadata = metadata_for_output(candidate, output_number)
        final_metadata.append(metadata)
        clip_id = str(metadata.get("id", "")).strip()
        if clip_id:
            used.add(clip_id)
            history[clip_id] = history_entry(candidate)

        selected_report.append(
            {
                "id": clip_id,
                "title": metadata.get("title", ""),
                "viral_score": metadata["viral_score"],
                "category": metadata["hook_category"],
                "hook_confidence": metadata["hook_confidence"],
                "trim_start": metadata["trim_start"],
                "trim_end": metadata["trim_end"],
                "warnings": candidate["warnings"],
                "content_gate_reason": metadata["content_gate_reason"],
                "content_gate": metadata["content_gate"],
            }
        )
        print(
            f"AUSGEWÄHLT {output_number}: {metadata['viral_score']:.1f} | "
            f"{metadata.get('title', '')}"
        )

    save_json(INPUT_JSON, final_metadata)
    save_json(USED_FILE, sorted(used))
    save_json(HISTORY_FILE, history)
    save_json(
        REPORT_FILE,
        {
            "streamer": STREAMER_NAME,
            "status": "selected" if selected else "no_clip_above_threshold",
            "transcripts_available": transcripts_available,
            "candidate_count": len(candidates),
            "analyzed_count": len(analyzed),
            "selected_count": len(selected),
            "selected": selected_report,
            "rejected": rejected,
        },
    )

    print("=" * 64)
    print(f"QUALITY GATE FERTIG | {len(selected)} starke Clips")
    if not selected:
        print("Kein Clip erreichte die Qualitätsgrenze. Kein Füllmaterial erzeugt.")
    print("=" * 64)


if __name__ == "__main__":
    main()
