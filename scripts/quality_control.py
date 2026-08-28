from __future__ import annotations

import glob
import json
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
    "Deutscher Twitch-Stream von Jussef. "
    "Die Sprecher reden schnell, locker und umgangssprachlich. "
    "Transkribiere wortgetreu. Behalte Jugendsprache, Namen und Slang bei."
)

TARGET_COUNT = 5
MIN_COUNT = 3
MAX_FINAL_COUNT = 5

# Wir prüfen bewusst mehr Kandidaten als vorher.
SEMANTIC_POOL_SIZE = 24

# Qualitätsstufen.
PREMIUM_SCORE = 68.0
GOOD_SCORE = 54.0
FALLBACK_SCORE = 40.0

MIN_DURATION = 8.0
MAX_REASONABLE_DURATION = 60.5
VOD_DUPLICATE_WINDOW_SECONDS = 75


REACTION_TERMS = {
    "haha": 2.0,
    "hahaha": 3.0,
    "lach": 2.0,
    "ausrast": 4.0,
    "crashout": 4.0,
    "rage": 3.0,
    "schrei": 2.5,
    "wtf": 3.0,
    "oh mein gott": 3.0,
    "niemals": 2.0,
    "oha": 1.5,
    "verkackt": 3.0,
    "reingeschissen": 3.0,
    "fail": 2.0,
    "hops": 2.5,
    "troll": 2.0,
    "sprachlos": 2.5,
    "ernst": 1.0,
    "digga": 0.5,
    "bro": 0.5,
}

PROMO_TERMS = {
    "alle folgen": 4.0,
    "folgt ihm": 4.0,
    "followt": 4.0,
    "abonnieren": 4.0,
    "abo da lassen": 4.0,
    "link in bio": 4.0,
    "neuer upload": 3.0,
    "neues video": 2.5,
    "werbung": 2.5,
    "sponsor": 2.5,
    "gewinnspiel": 3.0,
}


def load_json(path: str | Path, default: Any) -> Any:
    path = Path(path)
    if not path.exists():
        return default

    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return default


def save_json(path: str | Path, data: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as handle:
        json.dump(
            data,
            handle,
            indent=2,
            ensure_ascii=False,
        )


def clean_directory(path: str | Path) -> None:
    directory = Path(path)
    directory.mkdir(parents=True, exist_ok=True)

    for item in directory.iterdir():
        if item.is_file() or item.is_symlink():
            item.unlink()
        elif item.is_dir():
            shutil.rmtree(item)


def normalize_text(value: Any) -> str:
    text = str(value or "").lower()
    text = re.sub(r"[^a-z0-9äöüß' -]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def find_input_videos() -> list[Path]:
    videos: list[Path] = []

    for extension in ("mp4", "webm", "mkv", "mov", "m4v"):
        videos.extend(
            Path(path)
            for path in glob.glob(
                str(Path(INPUT_DIR) / f"*.{extension}")
            )
        )

    def number(path: Path) -> int:
        match = re.search(
            r"clip_(\d+)",
            path.stem,
            re.IGNORECASE,
        )
        return int(match.group(1)) if match else 999999

    return sorted(
        set(videos),
        key=lambda path: (
            number(path),
            path.name.lower(),
        ),
    )


def candidate_index(path: Path) -> int | None:
    match = re.search(
        r"clip_(\d+)",
        path.stem,
        re.IGNORECASE,
    )

    if not match:
        return None

    return int(match.group(1)) - 1


def video_info(path: Path) -> dict[str, float] | None:
    cap = cv2.VideoCapture(str(path))

    if not cap.isOpened():
        return None

    frames = int(
        cap.get(cv2.CAP_PROP_FRAME_COUNT)
    )
    fps = float(
        cap.get(cv2.CAP_PROP_FPS)
    ) or 30.0
    width = int(
        cap.get(cv2.CAP_PROP_FRAME_WIDTH)
    )
    height = int(
        cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
    )

    cap.release()

    if (
        frames <= 0
        or fps <= 0
        or width <= 0
        or height <= 0
    ):
        return None

    return {
        "frames": float(frames),
        "fps": fps,
        "width": float(width),
        "height": float(height),
        "duration": frames / fps,
    }


def has_audio(path: Path) -> bool:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "a:0",
        "-show_entries",
        "stream=codec_type",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
    )

    return (
        result.returncode == 0
        and "audio" in result.stdout.lower()
    )


def sample_motion(path: Path) -> float:
    cap = cv2.VideoCapture(str(path))

    if not cap.isOpened():
        return 0.0

    frame_count = int(
        cap.get(cv2.CAP_PROP_FRAME_COUNT)
    )

    if frame_count <= 1:
        cap.release()
        return 0.0

    positions = np.linspace(
        0,
        frame_count - 1,
        10,
        dtype=int,
    )

    previous = None
    differences: list[float] = []

    for position in positions:
        cap.set(
            cv2.CAP_PROP_POS_FRAMES,
            int(position),
        )

        ok, frame = cap.read()

        if not ok or frame is None:
            continue

        gray = cv2.cvtColor(
            frame,
            cv2.COLOR_BGR2GRAY,
        )

        gray = cv2.resize(
            gray,
            (192, 108),
        )

        if previous is not None:
            differences.append(
                float(
                    np.mean(
                        cv2.absdiff(
                            previous,
                            gray,
                        )
                    )
                )
            )

        previous = gray

    cap.release()

    if not differences:
        return 0.0

    return float(
        np.percentile(
            differences,
            85,
        )
    )


def load_whisper():
    import whisper

    print(
        f"Whisper wird geladen: {WHISPER_MODEL}"
    )

    return whisper.load_model(
        WHISPER_MODEL
    )


def compact_transcript(
    raw: dict[str, Any],
) -> dict[str, Any]:

    segments: list[dict[str, Any]] = []

    for segment in raw.get(
        "segments",
        [],
    ):
        if not isinstance(
            segment,
            dict,
        ):
            continue

        words: list[dict[str, Any]] = []

        for word in (
            segment.get(
                "words",
                [],
            )
            or []
        ):
            if not isinstance(
                word,
                dict,
            ):
                continue

            try:
                start = float(
                    word.get(
                        "start",
                        0.0,
                    )
                )
                end = float(
                    word.get(
                        "end",
                        start + 0.2,
                    )
                )
            except Exception:
                continue

            words.append(
                {
                    "word": str(
                        word.get(
                            "word",
                            "",
                        )
                    ),
                    "start": round(
                        start,
                        3,
                    ),
                    "end": round(
                        end,
                        3,
                    ),
                }
            )

        try:
            start = float(
                segment.get(
                    "start",
                    0.0,
                )
            )
            end = float(
                segment.get(
                    "end",
                    start + 0.5,
                )
            )
        except Exception:
            continue

        segments.append(
            {
                "start": round(
                    start,
                    3,
                ),
                "end": round(
                    end,
                    3,
                ),
                "text": str(
                    segment.get(
                        "text",
                        "",
                    )
                ).strip(),
                "words": words,
            }
        )

    return {
        "text": str(
            raw.get(
                "text",
                "",
            )
        ).strip(),
        "segments": segments,
    }


def transcribe(
    model: Any,
    path: Path,
) -> dict[str, Any]:

    raw = model.transcribe(
        str(path),
        language="de",
        task="transcribe",
        word_timestamps=True,
        initial_prompt=WHISPER_PROMPT,
        temperature=0.0,
        condition_on_previous_text=False,
        fp16=False,
        verbose=False,
    )

    return compact_transcript(
        raw
    )


def reaction_score(
    text: str,
) -> float:

    normalized = normalize_text(
        text
    )

    score = 0.0

    for phrase, weight in (
        REACTION_TERMS.items()
    ):
        if phrase in normalized:
            score += weight

    return score


def promo_score(
    text: str,
) -> float:

    normalized = normalize_text(
        text
    )

    score = 0.0

    for phrase, weight in (
        PROMO_TERMS.items()
    ):
        if phrase in normalized:
            score += weight

    return score


def calculate_score(
    metadata: dict[str, Any],
    transcript: dict[str, Any],
    motion: float,
    duration: float,
) -> tuple[float, dict[str, float]]:

    text = str(
        transcript.get(
            "text",
            "",
        )
    )

    words = normalize_text(
        text
    ).split()

    metadata_score = float(
        metadata.get(
            "metadata_score",
            0.0,
        )
        or 0.0
    )

    try:
        views = int(
            metadata.get(
                "view_count",
                0,
            )
            or 0
        )
    except Exception:
        views = 0

    metadata_points = min(
        28.0,
        metadata_score * 0.48,
    )

    view_points = min(
        12.0,
        np.log10(
            max(
                1,
                views + 1,
            )
        )
        * 2.7,
    )

    reaction = reaction_score(
        text
    )

    reaction_points = min(
        24.0,
        reaction * 3.0,
    )

    speech_points = min(
        12.0,
        len(words) / 2.0,
    )

    motion_points = min(
        10.0,
        motion / 2.4,
    )

    if (
        10.0
        <= duration
        <= 35.0
    ):
        duration_points = 10.0
    elif (
        8.0
        <= duration
        <= 45.0
    ):
        duration_points = 7.0
    else:
        duration_points = 3.0

    promo = promo_score(
        text
    )

    promo_penalty = min(
        30.0,
        promo * 5.0,
    )

    empty_penalty = (
        25.0
        if len(words) < 5
        else 0.0
    )

    score = (
        metadata_points
        + view_points
        + reaction_points
        + speech_points
        + motion_points
        + duration_points
        - promo_penalty
        - empty_penalty
    )

    breakdown = {
        "metadata": round(
            metadata_points,
            2,
        ),
        "views": round(
            view_points,
            2,
        ),
        "reaction": round(
            reaction_points,
            2,
        ),
        "speech": round(
            speech_points,
            2,
        ),
        "motion": round(
            motion_points,
            2,
        ),
        "duration": round(
            duration_points,
            2,
        ),
        "promo_penalty": round(
            -promo_penalty,
            2,
        ),
        "empty_penalty": round(
            -empty_penalty,
            2,
        ),
    }

    return (
        round(
            float(score),
            3,
        ),
        breakdown,
    )


def same_vod_region(
    candidate: dict[str, Any],
    history_entry: dict[str, Any],
) -> bool:

    video_id = str(
        candidate.get(
            "video_id",
            "",
        )
    ).strip()

    old_video_id = str(
        history_entry.get(
            "video_id",
            "",
        )
    ).strip()

    if (
        not video_id
        or video_id != old_video_id
    ):
        return False

    try:
        offset = int(
            candidate.get(
                "vod_offset"
            )
        )
        old_offset = int(
            history_entry.get(
                "vod_offset"
            )
        )
    except Exception:
        return False

    return (
        abs(
            offset
            - old_offset
        )
        <= VOD_DUPLICATE_WINDOW_SECONDS
    )


def is_history_duplicate(
    metadata: dict[str, Any],
    history: dict[str, Any],
) -> bool:

    clip_id = str(
        metadata.get(
            "id",
            "",
        )
    )

    if clip_id in history:
        return True

    for entry in history.values():
        if not isinstance(
            entry,
            dict,
        ):
            continue

        if same_vod_region(
            metadata,
            entry,
        ):
            return True

    return False


def choose_trim(
    transcript: dict[str, Any],
    duration: float,
) -> tuple[float, float]:

    segments = [
        segment
        for segment in transcript.get(
            "segments",
            [],
        )
        if isinstance(
            segment,
            dict,
        )
        and str(
            segment.get(
                "text",
                "",
            )
        ).strip()
    ]

    if not segments:
        return (
            0.0,
            round(
                min(
                    duration,
                    30.0,
                ),
                3,
            ),
        )

    try:
        speech_start = float(
            segments[0].get(
                "start",
                0.0,
            )
        )
        speech_end = float(
            segments[-1].get(
                "end",
                duration,
            )
        )
    except Exception:
        return (
            0.0,
            round(
                min(
                    duration,
                    30.0,
                ),
                3,
            ),
        )

    start = max(
        0.0,
        speech_start - 0.35,
    )

    end = min(
        duration,
        speech_end + 0.6,
    )

    if end - start > 30.0:
        end = start + 30.0

    if end - start < 10.0:
        end = min(
            duration,
            start + 10.0,
        )

        start = max(
            0.0,
            end - 10.0,
        )

    return (
        round(
            start,
            3,
        ),
        round(
            end,
            3,
        ),
    )


def build_history_entry(
    candidate: dict[str, Any],
) -> dict[str, Any]:

    metadata = candidate[
        "metadata"
    ]

    return {
        "clip_id": str(
            metadata.get(
                "id",
                "",
            )
        ),
        "title": metadata.get(
            "title",
            "",
        ),
        "created_at": metadata.get(
            "created_at",
            "",
        ),
        "duration": metadata.get(
            "duration",
            candidate["duration"],
        ),
        "video_id": metadata.get(
            "video_id",
            "",
        ),
        "vod_offset": metadata.get(
            "vod_offset",
        ),
        "viral_score": round(
            candidate["score"],
            3,
        ),
        "transcript_excerpt": str(
            candidate["transcript"].get(
                "text",
                "",
            )
        )[:900],
        "selection_tier": candidate[
            "tier"
        ],
        "fingerprint_version": 5,
    }


def select_best(
    analyzed: list[dict[str, Any]],
) -> list[dict[str, Any]]:

    ranked = sorted(
        analyzed,
        key=lambda item: item[
            "score"
        ],
        reverse=True,
    )

    selected: list[
        dict[str, Any]
    ] = []

    selected_ids: set[str] = set()
    selected_vod_positions: list[
        tuple[str, int]
    ] = []

    def already_selected(
        candidate: dict[str, Any],
    ) -> bool:

        metadata = candidate[
            "metadata"
        ]

        clip_id = str(
            metadata.get(
                "id",
                "",
            )
        )

        if clip_id in selected_ids:
            return True

        video_id = str(
            metadata.get(
                "video_id",
                "",
            )
        )

        try:
            offset = int(
                metadata.get(
                    "vod_offset"
                )
            )
        except Exception:
            offset = -999999

        if video_id:
            for (
                old_video_id,
                old_offset,
            ) in selected_vod_positions:

                if (
                    video_id
                    == old_video_id
                    and abs(
                        offset
                        - old_offset
                    )
                    <= VOD_DUPLICATE_WINDOW_SECONDS
                ):
                    return True

        return False

    def add_candidate(
        candidate: dict[str, Any],
        tier: str,
    ) -> None:

        if (
            len(selected)
            >= MAX_FINAL_COUNT
        ):
            return

        if already_selected(
            candidate
        ):
            return

        candidate["tier"] = tier

        selected.append(
            candidate
        )

        metadata = candidate[
            "metadata"
        ]

        selected_ids.add(
            str(
                metadata.get(
                    "id",
                    "",
                )
            )
        )

        video_id = str(
            metadata.get(
                "video_id",
                "",
            )
        )

        try:
            offset = int(
                metadata.get(
                    "vod_offset"
                )
            )
        except Exception:
            offset = -999999

        if video_id:
            selected_vod_positions.append(
                (
                    video_id,
                    offset,
                )
            )

    # STUFE A:
    # Die wirklich stärksten Clips.
    for candidate in ranked:
        if (
            candidate["score"]
            >= PREMIUM_SCORE
            and not candidate[
                "hard_reject"
            ]
        ):
            add_candidate(
                candidate,
                "premium",
            )

        if (
            len(selected)
            >= TARGET_COUNT
        ):
            break

    # STUFE B:
    # Gute Clips ergänzen.
    if (
        len(selected)
        < TARGET_COUNT
    ):
        for candidate in ranked:
            if (
                candidate["score"]
                >= GOOD_SCORE
                and not candidate[
                    "hard_reject"
                ]
            ):
                add_candidate(
                    candidate,
                    "good",
                )

            if (
                len(selected)
                >= TARGET_COUNT
            ):
                break

    # STUFE C:
    # Brauchbarer Fallback.
    # Nur wenn wir sonst nicht einmal
    # unser Tagesminimum erreichen.
    if (
        len(selected)
        < MIN_COUNT
    ):
        for candidate in ranked:
            if (
                candidate["score"]
                >= FALLBACK_SCORE
                and not candidate[
                    "hard_reject"
                ]
            ):
                add_candidate(
                    candidate,
                    "fallback",
                )

            if (
                len(selected)
                >= MIN_COUNT
            ):
                break

    # STUFE D:
    # Letzte Sicherheitsstufe.
    # Keine kaputten Clips, kein fehlendes
    # Audio, keine History-Duplikate.
    # Aber die besten verfügbaren Clips
    # werden verwendet, wenn die Scores
    # ungewöhnlich niedrig ausfallen.
    if (
        len(selected)
        < MIN_COUNT
    ):
        for candidate in ranked:
            if not candidate[
                "hard_reject"
            ]:
                add_candidate(
                    candidate,
                    "best_available",
                )

            if (
                len(selected)
                >= MIN_COUNT
            ):
                break

    return selected


def main() -> None:
    print(
        "=" * 64
    )
    print(
        f"CLIPCRIP QUALITY GATE | {STREAMER_NAME}"
    )
    print(
        "Ziel: 5 | Mindestziel: 3 | Hooks: AUS"
    )
    print(
        "=" * 64
    )

    clean_directory(
        FINAL_DIR
    )

    candidates = load_json(
        INPUT_JSON,
        [],
    )

    if not isinstance(
        candidates,
        list,
    ):
        raise RuntimeError(
            f"{INPUT_JSON} ist keine Liste."
        )

    if not candidates:
        raise RuntimeError(
            "Keine Twitch-Kandidaten gefunden. "
            "Der Bot darf nicht mit 0 Videos grün enden."
        )

    history_raw = load_json(
        HISTORY_FILE,
        {},
    )

    history = (
        history_raw
        if isinstance(
            history_raw,
            dict,
        )
        else {}
    )

    videos = find_input_videos()

    if not videos:
        raise RuntimeError(
            "Keine Kandidaten wurden heruntergeladen."
        )

    prepared: list[
        dict[str, Any]
    ] = []

    for path in videos:
        index = candidate_index(
            path
        )

        if (
            index is None
            or index < 0
            or index >= len(
                candidates
            )
        ):
            continue

        metadata = candidates[
            index
        ]

        if not isinstance(
            metadata,
            dict,
        ):
            continue

        info = video_info(
            path
        )

        if not info:
            print(
                f"REJECT {path.name}: Video defekt"
            )
            continue

        duration = float(
            info[
                "duration"
            ]
        )

        if (
            duration
            < MIN_DURATION
            or duration
            > MAX_REASONABLE_DURATION
        ):
            print(
                f"REJECT {path.name}: Dauer {duration:.1f}s"
            )
            continue

        if not has_audio(
            path
        ):
            print(
                f"REJECT {path.name}: kein Audio"
            )
            continue

        if is_history_duplicate(
            metadata,
            history,
        ):
            print(
                f"REJECT {path.name}: bereits verwendet / gleiche VOD-Stelle"
            )
            continue

        prepared.append(
            {
                "path": path,
                "metadata": metadata,
                "duration": duration,
                "motion": sample_motion(
                    path
                ),
            }
        )

    if not prepared:
        raise RuntimeError(
            "Alle heruntergeladenen Kandidaten waren "
            "defekt, bereits verwendet oder ungeeignet."
        )

    # Beste Kandidaten zuerst transkribieren.
    prepared.sort(
        key=lambda item: float(
            item[
                "metadata"
            ].get(
                "metadata_score",
                0.0,
            )
            or 0.0
        ),
        reverse=True,
    )

    prepared = prepared[
        :SEMANTIC_POOL_SIZE
    ]

    model = load_whisper()

    analyzed: list[
        dict[str, Any]
    ] = []

    for index, candidate in enumerate(
        prepared,
        start=1,
    ):
        print(
            f"TRANSKRIPTION {index}/{len(prepared)} | "
            f"{candidate['metadata'].get('title', '')}"
        )

        try:
            transcript = transcribe(
                model,
                candidate[
                    "path"
                ],
            )
        except Exception as error:
            print(
                f"TRANSKRIPTION FEHLER: {error}"
            )
            continue

        candidate[
            "transcript"
        ] = transcript

        score, breakdown = calculate_score(
            candidate[
                "metadata"
            ],
            transcript,
            candidate[
                "motion"
            ],
            candidate[
                "duration"
            ],
        )

        candidate[
            "score"
        ] = score

        candidate[
            "score_breakdown"
        ] = breakdown

        text = str(
            transcript.get(
                "text",
                "",
            )
        )

        words = normalize_text(
            text
        ).split()

        candidate[
            "hard_reject"
        ] = (
            len(words) < 3
            or promo_score(
                text
            )
            >= 7.0
        )

        (
            candidate[
                "trim_start"
            ],
            candidate[
                "trim_end"
            ],
        ) = choose_trim(
            transcript,
            candidate[
                "duration"
            ],
        )

        analyzed.append(
            candidate
        )

        print(
            f"SCORE {score:.1f} | "
            f"{len(words)} Wörter | "
            f"{candidate['metadata'].get('title', '')}"
        )

    if not analyzed:
        raise RuntimeError(
            "Kein Kandidat konnte erfolgreich transkribiert werden."
        )

    selected = select_best(
        analyzed
    )

    if len(
        selected
    ) < MIN_COUNT:
        raise RuntimeError(
            f"Nur {len(selected)} unterschiedliche technisch "
            f"brauchbare Clips verfügbar. Mindestziel ist {MIN_COUNT}."
        )

    used_raw = load_json(
        USED_FILE,
        [],
    )

    used = (
        {
            str(value)
            for value in used_raw
        }
        if isinstance(
            used_raw,
            list,
        )
        else set()
    )

    final_metadata: list[
        dict[str, Any]
    ] = []

    report: list[
        dict[str, Any]
    ] = []

    for output_number, candidate in enumerate(
        selected,
        start=1,
    ):
        source = candidate[
            "path"
        ]

        destination = (
            Path(
                FINAL_DIR
            )
            / f"clip_{output_number}.mp4"
        )

        transcript_destination = (
            Path(
                FINAL_DIR
            )
            / f"clip_{output_number}.transcript.json"
        )

        shutil.copy2(
            source,
            destination,
        )

        save_json(
            transcript_destination,
            candidate[
                "transcript"
            ],
        )

        metadata = dict(
            candidate[
                "metadata"
            ]
        )

        metadata.update(
            {
                "output_number": output_number,
                "viral_score": round(
                    candidate[
                        "score"
                    ],
                    3,
                ),
                "score_breakdown": candidate[
                    "score_breakdown"
                ],
                "trim_start": candidate[
                    "trim_start"
                ],
                "trim_end": candidate[
                    "trim_end"
                ],
                "selection_tier": candidate[
                    "tier"
                ],
                "selected_by": (
                    "best_available_3_to_5_v5"
                ),
            }
        )

        # Absichtlich KEINE Hook-Daten.
        metadata.pop(
            "hook_category",
            None,
        )
        metadata.pop(
            "hook_confidence",
            None,
        )

        final_metadata.append(
            metadata
        )

        clip_id = str(
            metadata.get(
                "id",
                "",
            )
        ).strip()

        if clip_id:
            used.add(
                clip_id
            )

            history[
                clip_id
            ] = build_history_entry(
                candidate
            )

        report.append(
            {
                "id": clip_id,
                "title": metadata.get(
                    "title",
                    "",
                ),
                "score": metadata[
                    "viral_score"
                ],
                "tier": candidate[
                    "tier"
                ],
                "trim_start": candidate[
                    "trim_start"
                ],
                "trim_end": candidate[
                    "trim_end"
                ],
            }
        )

        print(
            f"AUSGEWÄHLT {output_number}: "
            f"{metadata['viral_score']:.1f} | "
            f"{candidate['tier']} | "
            f"{metadata.get('title', '')}"
        )

    save_json(
        INPUT_JSON,
        final_metadata,
    )

    save_json(
        USED_FILE,
        sorted(
            used
        ),
    )

    save_json(
        HISTORY_FILE,
        history,
    )

    save_json(
        REPORT_FILE,
        {
            "streamer": STREAMER_NAME,
            "status": "ready",
            "target_count": TARGET_COUNT,
            "minimum_count": MIN_COUNT,
            "candidate_count": len(
                candidates
            ),
            "analyzed_count": len(
                analyzed
            ),
            "selected_count": len(
                selected
            ),
            "selected": report,
        },
    )

    print(
        "=" * 64
    )
    print(
        f"QUALITY GATE FERTIG | {len(selected)} Clips"
    )
    print(
        "HOOKS: AUS"
    )
    print(
        "=" * 64
    )


if __name__ == "__main__":
    main()