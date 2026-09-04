"""
ClipCrip3 US Discovery

Quellen:
- Kai Cenat -> Twitch Clips
- IShowSpeed -> YouTube Stream-VODs / Most-Replayed Peaks
- IShowSpeed -> Twitch als Fallback
- N3on -> Kick Clips

Alle Kandidaten landen danach in EINEM gemeinsamen Pool.
Die finale Auswahl erfolgt erst im Quality Gate.
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import requests


# ============================================================
# PFADE
# ============================================================

REPO_ROOT = (
    Path(__file__)
    .resolve()
    .parents[2]
)

US_ROOT = (
    REPO_ROOT
    / "us"
)

CORE_FILE = (
    REPO_ROOT
    / "scripts"
    / "get_clips.py"
)

USED_FILE = (
    US_ROOT
    / "used_clips.json"
)

HISTORY_FILE = (
    US_ROOT
    / "clip_history.json"
)

OUTPUT_FILE = (
    US_ROOT
    / "clips_today.json"
)


# ============================================================
# STREAMER
# ============================================================

KAI_TWITCH_LOGIN = "kaicenat"

SPEED_TWITCH_LOGIN = "ishowspeed"

SPEED_YOUTUBE_STREAMS = (
    "https://www.youtube.com/"
    "@IShowSpeed/streams"
)

N3ON_KICK_CHANNEL = "n3on"


# ============================================================
# POOL
# ============================================================

FINAL_CANDIDATE_POOL = 30

MIN_PER_STREAMER_IN_POOL = 6

CANDIDATES_PER_STREAMER = 14


# ============================================================
# SHARED CORE
# ============================================================

def load_core():

    spec = (
        importlib.util
        .spec_from_file_location(
            "clipcrip3_us_discovery_core",
            CORE_FILE,
        )
    )

    if (
        spec is None
        or spec.loader is None
    ):
        raise RuntimeError(
            f"Konnte Core-Datei "
            f"nicht laden: {CORE_FILE}"
        )

    module = (
        importlib.util
        .module_from_spec(
            spec
        )
    )

    spec.loader.exec_module(
        module
    )

    return module


# ============================================================
# JSON
# ============================================================

def load_json(
    path: Path,
    default: Any,
) -> Any:

    if not path.exists():
        return default

    try:

        return json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )

    except Exception:

        return default


def save_json(
    path: Path,
    data: Any,
) -> None:

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_text(
        json.dumps(
            data,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


# ============================================================
# YT-DLP METADATA
# ============================================================

def ytdlp_json(
    url: str,
    *,
    flat: bool = False,
) -> dict[str, Any] | None:

    command = [
        sys.executable,
        "-m",
        "yt_dlp",

        "--dump-single-json",

        "--skip-download",

        "--no-warnings",

        "--ignore-errors",
    ]

    if flat:

        command += [
            "--flat-playlist",

            "--playlist-end",
            "6",
        ]

    command.append(
        url
    )

    try:

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=150,
        )

    except subprocess.TimeoutExpired:

        print(
            f"YT-DLP TIMEOUT: {url}"
        )

        return None


    stdout = (
        result.stdout
        or ""
    ).strip()


    if not stdout:

        stderr = (
            result.stderr
            or ""
        ).strip()

        print(
            "YT-DLP WARNUNG:",
            stderr[-900:],
        )

        return None


    try:

        return json.loads(
            stdout
        )

    except json.JSONDecodeError:

        # Falls yt-dlp irgendwann noch
        # eine zusätzliche Zeile ausgibt.
        for line in reversed(
            stdout.splitlines()
        ):

            line = (
                line.strip()
            )

            if not line.startswith(
                "{"
            ):
                continue

            try:

                return json.loads(
                    line
                )

            except json.JSONDecodeError:

                continue


    return None


# ============================================================
# YOUTUBE DATUM
# ============================================================

def youtube_created_at(
    info: dict[str, Any],
) -> str:

    timestamp = (
        info.get(
            "timestamp"
        )
        or info.get(
            "release_timestamp"
        )
    )


    if isinstance(
        timestamp,
        (int, float),
    ):

        return (
            dt.datetime
            .fromtimestamp(
                timestamp,
                tz=dt.timezone.utc,
            )
            .isoformat()
            .replace(
                "+00:00",
                "Z",
            )
        )


    upload_date = str(
        info.get(
            "upload_date"
        )
        or ""
    ).strip()


    if (
        len(upload_date) == 8
        and upload_date.isdigit()
    ):

        return (
            upload_date[:4]
            + "-"
            + upload_date[4:6]
            + "-"
            + upload_date[6:8]
            + "T12:00:00Z"
        )


    return ""


# ============================================================
# SPEED YOUTUBE
# ============================================================

def speed_youtube_segments() -> list[
    dict[str, Any]
]:

    print(
        ""
    )

    print(
        "=" * 64
    )

    print(
        "ISHOWSPEED | YOUTUBE MOST-REPLAYED"
    )

    print(
        "=" * 64
    )


    playlist = ytdlp_json(
        SPEED_YOUTUBE_STREAMS,
        flat=True,
    )


    if not isinstance(
        playlist,
        dict,
    ):

        print(
            "Speed/YouTube: "
            "Stream-Tab konnte "
            "nicht gelesen werden."
        )

        return []


    entries = (
        playlist.get(
            "entries"
        )
        or []
    )


    if not isinstance(
        entries,
        list,
    ):

        return []


    candidates: list[
        dict[str, Any]
    ] = []


    for entry in entries[:6]:

        if not isinstance(
            entry,
            dict,
        ):
            continue


        video_id = str(
            entry.get(
                "id"
            )
            or ""
        ).strip()


        raw_url = str(
            entry.get(
                "webpage_url"
            )
            or entry.get(
                "url"
            )
            or ""
        ).strip()


        if (
            raw_url
            and not raw_url.startswith(
                "http"
            )
        ):

            if not video_id:

                video_id = (
                    raw_url
                )

            raw_url = (
                "https://www.youtube.com/"
                "watch?v="
                + video_id
            )


        if (
            not raw_url
            and video_id
        ):

            raw_url = (
                "https://www.youtube.com/"
                "watch?v="
                + video_id
            )


        if not raw_url:

            continue


        info = ytdlp_json(
            raw_url
        )


        if not isinstance(
            info,
            dict,
        ):

            continue


        live_status = str(
            info.get(
                "live_status"
            )
            or ""
        ).lower()


        # Keine aktuell laufenden Streams.
        if (
            live_status
            in {
                "is_live",
                "is_upcoming",
            }
            or bool(
                info.get(
                    "is_live"
                )
            )
        ):

            print(
                "Speed/YouTube: "
                "laufender Stream "
                "übersprungen."
            )

            continue


        try:

            duration = float(
                info.get(
                    "duration"
                )
                or 0.0
            )

        except (
            TypeError,
            ValueError,
        ):

            duration = 0.0


        # Nur echte Streams/VODs.
        if duration < 240:

            continue


        video_id = str(
            info.get(
                "id"
            )
            or video_id
        ).strip()


        if not video_id:

            continue


        title = str(
            info.get(
                "title"
            )
            or "IShowSpeed livestream"
        ).strip()


        try:

            views = int(
                info.get(
                    "view_count"
                )
                or 0
            )

        except (
            TypeError,
            ValueError,
        ):

            views = 0


        heatmap = (
            info.get(
                "heatmap"
            )
            or []
        )


        if not isinstance(
            heatmap,
            list,
        ):

            heatmap = []


        peaks: list[
            tuple[
                float,
                float,
            ]
        ] = []


        for heat in heatmap:

            if not isinstance(
                heat,
                dict,
            ):
                continue


            try:

                start = float(
                    heat.get(
                        "start_time"
                    )
                    or 0.0
                )

                end = float(
                    heat.get(
                        "end_time"
                    )
                    or start
                )

                value = float(
                    heat.get(
                        "value"
                    )
                    or 0.0
                )

            except (
                TypeError,
                ValueError,
            ):

                continue


            center = (
                start
                + end
            ) / 2.0


            # Intro / Outro vermeiden.
            if center < 45:

                continue


            if center > (
                duration
                - 45
            ):

                continue


            peaks.append(
                (
                    value,
                    center,
                )
            )


        peaks.sort(
            key=lambda item: (
                item[0]
            ),
            reverse=True,
        )


        selected_centers: list[
            float
        ] = []


        for (
            heat_value,
            center,
        ) in peaks:


            # Keine nahezu identischen
            # Momente aus demselben Stream.
            if any(

                abs(
                    center
                    - previous
                )
                < 90

                for previous
                in selected_centers

            ):

                continue


            # Etwas Kontext VOR dem Peak.
            section_start = max(
                0.0,
                center - 9.0,
            )


            section_end = min(
                duration,
                section_start + 34.0,
            )


            if (
                section_end
                - section_start
                < 12
            ):

                continue


            selected_centers.append(
                center
            )


            candidates.append(
                {

                    "id": (
                        "yt_speed_"
                        + video_id
                        + "_"
                        + str(
                            int(
                                section_start
                            )
                        )
                    ),

                    "title": (
                        title
                        + " | Most replayed"
                    ),

                    "url": (
                        "https://www.youtube.com/"
                        "watch?v="
                        + video_id
                    ),

                    "view_count": views,

                    "creator_name": (
                        "IShowSpeed"
                    ),

                    "created_at": (
                        youtube_created_at(
                            info
                        )
                    ),

                    "duration": round(
                        section_end
                        - section_start,
                        3,
                    ),

                    "broadcaster_name": (
                        "IShowSpeed"
                    ),

                    "video_id": (
                        "youtube:"
                        + video_id
                    ),

                    "vod_offset": int(
                        section_start
                    ),

                    "is_featured": True,

                    "source": (
                        "youtube"
                    ),

                    "section_start": round(
                        section_start,
                        3,
                    ),

                    "section_end": round(
                        section_end,
                        3,
                    ),

                    "heat_value": round(
                        heat_value,
                        6,
                    ),
                }
            )


            # Maximal 4 Stellen pro VOD.
            if len(
                selected_centers
            ) >= 4:

                break


    print(
        "Speed/YouTube: "
        f"{len(candidates)} "
        "Most-Replayed-Segmente."
    )


    return candidates


# ============================================================
# TWITCH
# ============================================================

def twitch_clips(
    core: Any,
    session: requests.Session,
    token: str,
    login: str,
    label: str,
) -> list[
    dict[str, Any]
]:

    core.BROADCASTER_LOGIN = (
        login
    )


    broadcaster_id = (
        core.get_broadcaster_id(
            session,
            token,
        )
    )


    clips = (
        core.get_all_clips(
            token,
            broadcaster_id,
            session=session,
        )
    )


    for clip in clips:

        clip[
            "broadcaster_name"
        ] = label

        clip[
            "source"
        ] = "twitch"


    print(
        f"Twitch/{label}: "
        f"{len(clips)} Clips."
    )


    return clips


# ============================================================
# KICK HELPERS
# ============================================================

def kick_value(
    item: dict[str, Any],
    *keys: str,
    default: Any = "",
) -> Any:

    for key in keys:

        value = (
            item.get(
                key
            )
        )

        if value not in (
            None,
            "",
        ):

            return value


    return default


# ============================================================
# N3ON KICK
# ============================================================

def n3on_kick_clips() -> list[
    dict[str, Any]
]:

    print(
        ""
    )

    print(
        "=" * 64
    )

    print(
        "N3ON | KICK CLIPS"
    )

    print(
        "=" * 64
    )


    endpoint = (
        "https://kick.com/"
        "api/v2/channels/"
        + N3ON_KICK_CHANNEL
        + "/clips"
    )


    headers = {

        "User-Agent": (
            "Mozilla/5.0 "
            "(Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/126.0 Safari/537.36"
        ),

        "Accept": (
            "application/json,"
            "text/plain,*/*"
        ),

        "Accept-Language": (
            "en-US,en;q=0.9"
        ),

        "Referer": (
            "https://kick.com/"
            + N3ON_KICK_CHANNEL
        ),
    }


    merged: dict[
        str,
        dict[str, Any],
    ] = {}


    searches = [

        (
            "view",
            "week",
        ),

        (
            "date",
            "week",
        ),

        (
            "view",
            "month",
        ),
    ]


    for (
        sort,
        time_filter,
    ) in searches:


        try:

            response = requests.get(
                endpoint,
                params={
                    "cursor": 0,
                    "sort": sort,
                    "time": time_filter,
                },
                headers=headers,
                timeout=35,
            )


            response.raise_for_status()


            payload = (
                response.json()
            )


        except Exception as error:

            print(
                "N3on/Kick WARNUNG "
                f"({sort}/{time_filter}): "
                f"{error}"
            )

            continue


        clips = (

            payload.get(
                "clips",
                [],
            )

            if isinstance(
                payload,
                dict,
            )

            else []
        )


        if not isinstance(
            clips,
            list,
        ):

            continue


        for item in clips:

            if not isinstance(
                item,
                dict,
            ):

                continue


            raw_id = str(
                kick_value(
                    item,
                    "id",
                    "uuid",
                    "slug",
                    default="",
                )
            ).strip()


            if not raw_id:

                continue


            try:

                duration = float(
                    kick_value(
                        item,
                        "duration",
                        "clip_duration",
                        default=0.0,
                    )
                    or 0.0
                )

            except (
                TypeError,
                ValueError,
            ):

                duration = 0.0


            # Alte Responses können
            # Millisekunden enthalten.
            if duration > 1000:

                duration /= 1000.0


            # Unser TikTok-System soll
            # kurze Clips auswählen.
            if (
                duration
                and not (
                    8.0
                    <= duration
                    <= 60.5
                )
            ):

                continue


            if duration <= 0:

                # Echte Dauer wird später
                # über die Datei geprüft.
                duration = 30.0


            try:

                views = int(
                    kick_value(
                        item,
                        "view_count",
                        "views",
                        "views_count",
                        default=0,
                    )
                    or 0
                )

            except (
                TypeError,
                ValueError,
            ):

                views = 0


            # yt-dlp unterstützt
            # Kick Clip URLs direkt.
            if raw_id.startswith(
                "clip_"
            ):

                webpage_url = (
                    "https://kick.com/"
                    + N3ON_KICK_CHANNEL
                    + "/clips/"
                    + raw_id
                )

            else:

                webpage_url = str(
                    kick_value(
                        item,
                        "clip_url",
                        "url",
                        "webpage_url",
                        default="",
                    )
                ).strip()


            if not webpage_url:

                continue


            raw_video_id = str(
                kick_value(
                    item,
                    "livestream_id",
                    "video_id",
                    default="",
                )
            ).strip()


            clip_id = (
                "kick_n3on_"
                + raw_id
            )


            merged[
                clip_id
            ] = {

                "id": clip_id,

                "title": str(
                    kick_value(
                        item,
                        "title",
                        "clip_title",
                        default="N3on clip",
                    )
                ).strip(),

                "url": webpage_url,

                "view_count": views,

                "creator_name": "",

                "created_at": str(
                    kick_value(
                        item,
                        "created_at",
                        "createdAt",
                        default="",
                    )
                ),

                "duration": (
                    duration
                ),

                "broadcaster_name": (
                    "N3on"
                ),

                "video_id": (
                    (
                        "kick:"
                        + raw_video_id
                    )
                    if raw_video_id
                    else (
                        "kickclip:"
                        + raw_id
                    )
                ),

                "vod_offset": None,

                "is_featured": False,

                "source": (
                    "kick"
                ),
            }


    print(
        "N3on/Kick: "
        f"{len(merged)} "
        "eindeutige Clips."
    )


    return list(
        merged.values()
    )


# ============================================================
# SOURCE FIELDS WIEDERHERSTELLEN
# ============================================================

def rank_streamer_group(
    core: Any,
    raw_clips: list[
        dict[str, Any]
    ],
    used_ids: set[str],
    history: dict[str, Any],
) -> list[
    dict[str, Any]
]:

    if not raw_clips:

        return []


    raw_by_id = {

        str(
            item.get(
                "id"
            )
            or ""
        ): item

        for item in raw_clips

        if str(
            item.get(
                "id"
            )
            or ""
        ).strip()
    }


    core.CANDIDATE_COUNT = (
        CANDIDATES_PER_STREAMER
    )


    candidates = (
        core.build_candidates(
            raw_clips,
            used_ids,
            history,
        )
    )


    for candidate in candidates:


        source_item = (
            raw_by_id.get(
                str(
                    candidate.get(
                        "id"
                    )
                    or ""
                ),
                {},
            )
        )


        source = str(
            source_item.get(
                "source"
            )
            or "twitch"
        )


        candidate[
            "source"
        ] = source


        candidate[
            "broadcaster_name"
        ] = str(
            source_item.get(
                "broadcaster_name"
            )
            or candidate.get(
                "broadcaster_name"
            )
            or ""
        )


        for field in (

            "section_start",

            "section_end",

            "heat_value",

        ):

            if field in source_item:

                candidate[
                    field
                ] = (
                    source_item[
                        field
                    ]
                )


        # YouTubes Most-Replayed Daten
        # bekommen einen zusätzlichen Bonus.
        if source == "youtube":

            try:

                heat = max(
                    0.0,
                    min(
                        1.0,
                        float(
                            source_item.get(
                                "heat_value"
                            )
                            or 0.0
                        ),
                    ),
                )

            except (
                TypeError,
                ValueError,
            ):

                heat = 0.0


            heat_bonus = (
                heat
                * 18.0
            )


            candidate[
                "metadata_score"
            ] = round(
                float(
                    candidate.get(
                        "metadata_score"
                    )
                    or 0.0
                )
                + heat_bonus,
                3,
            )


            breakdown = (
                candidate.get(
                    "metadata_score_breakdown"
                )
            )


            if isinstance(
                breakdown,
                dict,
            ):

                breakdown[
                    "youtube_heatmap"
                ] = round(
                    heat_bonus,
                    3,
                )


            candidate[
                "selected_by"
            ] = (
                "youtube_most_replayed"
            )


        elif source == "kick":

            candidate[
                "selected_by"
            ] = (
                "kick_recent"
            )


        else:

            candidate[
                "selected_by"
            ] = (
                "twitch_recent"
            )


    return candidates


# ============================================================
# GEMISCHTER POOL
# ============================================================

def diverse_pool(
    candidates: list[
        dict[str, Any]
    ],
    limit: int,
) -> list[
    dict[str, Any]
]:

    """
    Jeder verfügbare Streamer bekommt
    Kandidaten in die genaue Analyse.

    Das erzwingt NICHT 2/2/1 bei den
    finalen fünf Videos.

    Die finalen fünf werden weiterhin
    nach Qualität ausgewählt.
    """

    ranked = sorted(
        candidates,
        key=lambda item: float(
            item.get(
                "metadata_score"
            )
            or 0.0
        ),
        reverse=True,
    )


    groups: dict[
        str,
        list[
            dict[str, Any]
        ],
    ] = {}


    for item in ranked:

        streamer = str(
            item.get(
                "broadcaster_name"
            )
            or "Unknown"
        )

        groups.setdefault(
            streamer,
            [],
        ).append(
            item
        )


    selected: list[
        dict[str, Any]
    ] = []


    selected_ids: set[
        str
    ] = set()


    # Erst sicherstellen, dass die besten
    # Kandidaten jedes Streamers überhaupt
    # ins Quality Gate gelangen.
    for streamer in (

        "Kai Cenat",

        "IShowSpeed",

        "N3on",

    ):

        for item in (
            groups.get(
                streamer,
                [],
            )[
                :MIN_PER_STREAMER_IN_POOL
            ]
        ):

            clip_id = str(
                item.get(
                    "id"
                )
                or ""
            )


            if (
                not clip_id
                or clip_id in selected_ids
            ):

                continue


            selected.append(
                item
            )

            selected_ids.add(
                clip_id
            )


    # Rest komplett nach Stärke.
    for item in ranked:

        if len(
            selected
        ) >= limit:

            break


        clip_id = str(
            item.get(
                "id"
            )
            or ""
        )


        if (
            not clip_id
            or clip_id in selected_ids
        ):

            continue


        selected.append(
            item
        )

        selected_ids.add(
            clip_id
        )


    selected.sort(
        key=lambda item: float(
            item.get(
                "metadata_score"
            )
            or 0.0
        ),
        reverse=True,
    )


    return selected[
        :limit
    ]


# ============================================================
# MAIN
# ============================================================

def main() -> None:

    US_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )


    core = load_core()


    # ========================================================
    # US CONFIG
    # ========================================================

    core.LOOKBACK_DAYS = 30

    core.WINDOW_DAYS = 7

    core.MAX_PAGES_PER_WINDOW = 2

    core.MAX_CANDIDATES_PER_VOD = 4

    core.MIN_DURATION_SECONDS = 8.0


    core.REACTION_TERMS = {

        "crashout": 4.0,

        "crash out": 4.0,

        "rage": 3.5,

        "scream": 3.0,

        "screaming": 3.0,

        "wtf": 3.0,

        "oh my god": 3.0,

        "omg": 2.5,

        "no way": 3.0,

        "crazy": 2.0,

        "insane": 2.5,

        "funny": 2.0,

        "fail": 2.5,

        "roast": 2.5,

        "caught": 2.0,

        "exposed": 2.0,

        "troll": 2.0,

        "reaction": 1.5,
    }


    core.GENERIC_TITLES = {

        "clip",

        "clips",

        "lol",

        "lmao",

        "w",

        "l",
    }


    # ========================================================
    # QUELLEN EINZELN SAMMELN
    # ========================================================

    kai_raw: list[
        dict[str, Any]
    ] = []


    speed_raw: list[
        dict[str, Any]
    ] = []


    n3on_raw: list[
        dict[str, Any]
    ] = []


    # --------------------------------------------------------
    # SPEED YOUTUBE ZUERST
    # --------------------------------------------------------

    try:

        speed_raw.extend(
            speed_youtube_segments()
        )

    except Exception as error:

        print(
            "Speed/YouTube WARNUNG:",
            error,
        )


    # --------------------------------------------------------
    # N3ON KICK
    # --------------------------------------------------------

    try:

        n3on_raw.extend(
            n3on_kick_clips()
        )

    except Exception as error:

        print(
            "N3on/Kick WARNUNG:",
            error,
        )


    # --------------------------------------------------------
    # TWITCH
    # --------------------------------------------------------

    twitch_session = (
        core.build_session()
    )


    try:

        token = (
            core.get_token(
                twitch_session
            )
        )


        # Kai immer über Twitch.
        try:

            kai_raw.extend(
                twitch_clips(
                    core,
                    twitch_session,
                    token,
                    KAI_TWITCH_LOGIN,
                    "Kai Cenat",
                )
            )

        except Exception as error:

            print(
                "Kai/Twitch WARNUNG:",
                error,
            )


        # Speed Twitch nur als Fallback.
        if len(
            speed_raw
        ) < 5:

            try:

                speed_raw.extend(
                    twitch_clips(
                        core,
                        twitch_session,
                        token,
                        SPEED_TWITCH_LOGIN,
                        "IShowSpeed",
                    )
                )

                print(
                    "Speed: "
                    "Twitch-Fallback aktiv."
                )

            except Exception as error:

                print(
                    "Speed/Twitch-Fallback "
                    "WARNUNG:",
                    error,
                )


    finally:

        twitch_session.close()


    # ========================================================
    # HISTORY
    # ========================================================

    used_raw = load_json(
        USED_FILE,
        [],
    )


    used_ids = (

        {
            str(
                value
            )
            for value in used_raw
        }

        if isinstance(
            used_raw,
            list,
        )

        else set()
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


    # ========================================================
    # JEDEN STREAMER SEPARAT RANKEN
    #
    # Dadurch kann Kai mit riesigen Twitch-
    # Zahlen nicht bereits vor dem Quality
    # Gate alle N3on Kandidaten verdrängen.
    # ========================================================

    candidates: list[
        dict[str, Any]
    ] = []


    candidates.extend(
        rank_streamer_group(
            core,
            kai_raw,
            used_ids,
            history,
        )
    )


    candidates.extend(
        rank_streamer_group(
            core,
            speed_raw,
            used_ids,
            history,
        )
    )


    candidates.extend(
        rank_streamer_group(
            core,
            n3on_raw,
            used_ids,
            history,
        )
    )


    # ========================================================
    # GEMISCHTER FINALER KANDIDATENPOOL
    # ========================================================

    candidates = diverse_pool(
        candidates,
        FINAL_CANDIDATE_POOL,
    )


    save_json(
        OUTPUT_FILE,
        candidates,
    )


    # ========================================================
    # LOG
    # ========================================================

    print(
        ""
    )

    print(
        "=" * 72
    )

    print(
        "CLIPCRIP3 US | "
        "GEMISCHTER POOL"
    )

    print(
        "=" * 72
    )


    counts: dict[
        str,
        int,
    ] = {}


    for item in candidates:

        label = str(
            item.get(
                "broadcaster_name"
            )
            or "Unknown"
        )

        counts[
            label
        ] = (
            counts.get(
                label,
                0,
            )
            + 1
        )


    print(
        "Pool-Verteilung:",
        counts,
    )


    for (
        number,
        item,
    ) in enumerate(
        candidates,
        start=1,
    ):

        print(
            f"{number:02d}. "
            f"{float(item.get('metadata_score', 0.0)):6.1f} | "
            f"{str(item.get('broadcaster_name', '')):12} | "
            f"{str(item.get('source', '')):8} | "
            f"{int(item.get('view_count', 0) or 0):8} Views | "
            f"{str(item.get('title', ''))[:90]}"
        )


    if len(
        candidates
    ) < 5:

        raise RuntimeError(
            f"Nur {len(candidates)} "
            "frische US-Kandidaten verfügbar. "
            "Mindestens 5 benötigt."
        )


if __name__ == "__main__":

    main()
