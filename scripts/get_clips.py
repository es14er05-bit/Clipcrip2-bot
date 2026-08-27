"""Discover recent Twitch clips for the shared ClipCrip engine.

The old collector supplied only ``started_at``. Twitch then implicitly used a
one-week window beginning 365 days ago, so Jussef repeatedly received old
clips. This collector explicitly walks recent seven-day windows, de-duplicates
the results and builds a diverse candidate pool instead of blindly taking the
oldest all-time view leaders.

Streamer wrappers may override the module-level configuration before calling
``main()``. That keeps one implementation for Jussef, Rohat and Giggand.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import os
import re
import time
from pathlib import Path
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


BROADCASTER_LOGIN = "jussef"

LOOKBACK_DAYS = 90
WINDOW_DAYS = 7
MAX_PAGES_PER_WINDOW = 3

CANDIDATE_COUNT = 24
MAX_CANDIDATES_PER_VOD = 3
MIN_DURATION_SECONDS = 8.0
VOD_DUPLICATE_WINDOW_SECONDS = 75

USED_FILE = "used_clips.json"
HISTORY_FILE = "clip_history.json"
OUTPUT_FILE = "clips_today.json"


REACTION_TERMS: dict[str, float] = {
    "ausrast": 4.0,
    "crashout": 4.0,
    "rage": 3.5,
    "schrei": 3.0,
    "jumpscare": 3.5,
    "erschreck": 3.0,
    "wtf": 3.0,
    "oh mein gott": 3.0,
    "lach": 2.5,
    "haha": 2.5,
    "lustig": 2.0,
    "fail": 2.5,
    "verkackt": 3.0,
    "roast": 2.5,
    "hops": 2.5,
    "troll": 2.0,
    "chat": 1.0,
    "reaction": 1.5,
    "reaktion": 1.5,
    "sprachlos": 2.5,
    "eskal": 3.0,
}

GENERIC_TITLES = {
    "clip",
    "clips",
    "twitch clip",
    "lol",
    "haha",
    "hahaha",
    "w",
    "l",
}


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def iso_z(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def parse_datetime(value: Any) -> dt.datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return dt.datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(
            dt.timezone.utc
        )
    except (TypeError, ValueError):
        return None


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


def build_session() -> requests.Session:
    retry = Retry(
        total=5,
        connect=5,
        read=5,
        status=5,
        backoff_factor=1.2,
        status_forcelist=(408, 429, 500, 502, 503, 504),
        allowed_methods=("GET", "POST"),
        raise_on_status=False,
    )
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.headers.update({"User-Agent": "ClipCrip-Shared-Engine/1.0"})
    return session


def get_token(session: requests.Session) -> str:
    client_id = os.environ.get("TWITCH_CLIENT_ID", "").strip()
    client_secret = os.environ.get("TWITCH_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        raise RuntimeError("TWITCH_CLIENT_ID oder TWITCH_CLIENT_SECRET fehlt.")

    response = session.post(
        "https://id.twitch.tv/oauth2/token",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "client_credentials",
        },
        timeout=30,
    )
    response.raise_for_status()
    token = str(response.json().get("access_token", "")).strip()
    if not token:
        raise RuntimeError("Twitch lieferte keinen Access Token.")
    return token


def twitch_headers(token: str) -> dict[str, str]:
    return {
        "Client-Id": os.environ["TWITCH_CLIENT_ID"],
        "Authorization": f"Bearer {token}",
    }


def get_broadcaster_id(session: requests.Session, token: str) -> str:
    response = session.get(
        "https://api.twitch.tv/helix/users",
        params={"login": BROADCASTER_LOGIN},
        headers=twitch_headers(token),
        timeout=30,
    )
    response.raise_for_status()
    users = response.json().get("data", [])
    if not users:
        raise RuntimeError(f"Twitch-User '{BROADCASTER_LOGIN}' wurde nicht gefunden.")
    return str(users[0]["id"])


def get_window_clips(
    session: requests.Session,
    token: str,
    broadcaster_id: str,
    started_at: dt.datetime,
    ended_at: dt.datetime,
) -> list[dict[str, Any]]:
    clips: list[dict[str, Any]] = []
    cursor: str | None = None

    for page in range(1, MAX_PAGES_PER_WINDOW + 1):
        params: dict[str, Any] = {
            "broadcaster_id": broadcaster_id,
            "started_at": iso_z(started_at),
            "ended_at": iso_z(ended_at),
            "first": 100,
        }
        if cursor:
            params["after"] = cursor

        response = session.get(
            "https://api.twitch.tv/helix/clips",
            params=params,
            headers=twitch_headers(token),
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        page_clips = payload.get("data", [])
        clips.extend(item for item in page_clips if isinstance(item, dict))

        print(
            f"  {started_at.date()} bis {ended_at.date()} | "
            f"Seite {page}: {len(page_clips)} Clips"
        )

        cursor = payload.get("pagination", {}).get("cursor")
        if not cursor or not page_clips:
            break
        time.sleep(0.08)

    return clips


def get_all_clips(
    token: str,
    broadcaster_id: str,
    session: requests.Session | None = None,
) -> list[dict[str, Any]]:
    """Walk explicit recent windows and return unique Twitch clips."""

    own_session = session is None
    session = session or build_session()
    now = utc_now()
    oldest = now - dt.timedelta(days=LOOKBACK_DAYS)
    window_end = now
    collected: dict[str, dict[str, Any]] = {}

    print(
        f"Twitch-Suche: letzte {LOOKBACK_DAYS} Tage in "
        f"{WINDOW_DAYS}-Tage-Fenstern."
    )

    while window_end > oldest:
        window_start = max(oldest, window_end - dt.timedelta(days=WINDOW_DAYS))
        for clip in get_window_clips(
            session,
            token,
            broadcaster_id,
            window_start,
            window_end,
        ):
            clip_id = str(clip.get("id", "")).strip()
            if clip_id:
                collected[clip_id] = clip
        window_end = window_start

    if own_session:
        session.close()

    print(f"{len(collected)} eindeutige Twitch-Clips gefunden.")
    return list(collected.values())


def get_vod_position(clip: dict[str, Any]) -> tuple[str, int] | None:
    video_id = str(clip.get("video_id", "")).strip()
    raw_offset = clip.get("vod_offset")
    if not video_id or raw_offset is None:
        return None
    try:
        offset = int(raw_offset)
    except (TypeError, ValueError):
        return None
    if offset < 0:
        return None
    return video_id, offset


def build_used_vod_positions(
    all_clips: list[dict[str, Any]],
    used_ids: set[str],
    history: dict[str, Any],
) -> dict[str, list[int]]:
    positions: dict[str, set[int]] = {}

    for entry in history.values():
        if not isinstance(entry, dict):
            continue
        position = get_vod_position(entry)
        if position:
            video_id, offset = position
            positions.setdefault(video_id, set()).add(offset)

    for clip in all_clips:
        clip_id = str(clip.get("id", "")).strip()
        if clip_id not in used_ids:
            continue
        position = get_vod_position(clip)
        if position:
            video_id, offset = position
            positions.setdefault(video_id, set()).add(offset)

    result = {video_id: sorted(values) for video_id, values in positions.items()}
    print(
        f"{sum(len(values) for values in result.values())} bekannte "
        "VOD-Positionen für die Duplikatsperre."
    )
    return result


def is_used_vod_position(
    clip: dict[str, Any], positions: dict[str, list[int]]
) -> bool:
    position = get_vod_position(clip)
    if not position:
        return False
    video_id, offset = position
    return any(
        abs(offset - previous) <= VOD_DUPLICATE_WINDOW_SECONDS
        for previous in positions.get(video_id, [])
    )


def normalize_title(value: Any) -> str:
    title = re.sub(r"[^a-z0-9äöüß]+", " ", str(value or "").lower())
    return re.sub(r"\s+", " ", title).strip()


def title_signal(title: str) -> float:
    normalized = normalize_title(title)
    if not normalized or normalized in GENERIC_TITLES:
        return 0.0
    score = sum(weight for term, weight in REACTION_TERMS.items() if term in normalized)
    if 3 <= len(normalized.split()) <= 9:
        score += 1.5
    return min(12.0, score)


def metadata_score(
    clip: dict[str, Any], now: dt.datetime
) -> tuple[float, dict[str, float]]:
    try:
        views = max(0, int(clip.get("view_count", 0)))
    except (TypeError, ValueError):
        views = 0

    created = parse_datetime(clip.get("created_at")) or now - dt.timedelta(
        days=LOOKBACK_DAYS
    )
    age_days = max(0.25, (now - created).total_seconds() / 86400.0)
    recency = max(0.0, 22.0 * (1.0 - age_days / max(LOOKBACK_DAYS, 1)))
    view_strength = min(24.0, math.log10(views + 1.0) * 6.0)
    velocity = min(18.0, math.log10((views / age_days) + 1.0) * 6.0)

    try:
        duration = float(clip.get("duration", 0.0))
    except (TypeError, ValueError):
        duration = 0.0

    if 12.0 <= duration <= 45.0:
        duration_score = 9.0
    elif 8.0 <= duration <= 60.5:
        duration_score = 4.0
    else:
        duration_score = 0.0

    title = title_signal(str(clip.get("title", "")))
    featured = 2.0 if clip.get("is_featured") else 0.0
    breakdown = {
        "recency": round(recency, 3),
        "views": round(view_strength, 3),
        "view_velocity": round(velocity, 3),
        "duration": round(duration_score, 3),
        "title": round(title, 3),
        "featured": featured,
    }
    return round(sum(breakdown.values()), 3), breakdown


def build_candidates(
    clips: list[dict[str, Any]],
    used_ids: set[str],
    history: dict[str, Any],
) -> list[dict[str, Any]]:
    now = utc_now()
    used_positions = build_used_vod_positions(clips, used_ids, history)
    eligible: list[dict[str, Any]] = []

    counters = {"used_id": 0, "used_vod": 0, "short": 0, "invalid": 0}

    for clip in clips:
        clip_id = str(clip.get("id", "")).strip()
        url = str(clip.get("url", "")).strip()
        try:
            duration = float(clip.get("duration", 0.0))
        except (TypeError, ValueError):
            duration = 0.0

        if not clip_id or not url:
            counters["invalid"] += 1
            continue
        if clip_id in used_ids:
            counters["used_id"] += 1
            continue
        if is_used_vod_position(clip, used_positions):
            counters["used_vod"] += 1
            continue
        if duration < MIN_DURATION_SECONDS:
            counters["short"] += 1
            continue

        score, breakdown = metadata_score(clip, now)
        position = get_vod_position(clip)
        video_id, vod_offset = position if position else ("", None)
        eligible.append(
            {
                "id": clip_id,
                "title": str(clip.get("title", "")).strip(),
                "url": url,
                "view_count": int(clip.get("view_count", 0) or 0),
                "creator_name": str(clip.get("creator_name", "")),
                "created_at": str(clip.get("created_at", "")),
                "duration": duration,
                "broadcaster_name": str(
                    clip.get("broadcaster_name", BROADCASTER_LOGIN)
                ),
                "video_id": video_id,
                "vod_offset": vod_offset,
                "metadata_score": score,
                "metadata_score_breakdown": breakdown,
                "source": "twitch",
                "selected_by": "recent_diverse_candidate_pool",
            }
        )

    eligible.sort(key=lambda item: item["metadata_score"], reverse=True)

    selected: list[dict[str, Any]] = []
    per_vod: dict[str, int] = {}
    title_counts: dict[str, int] = {}

    for clip in eligible:
        video_id = clip.get("video_id") or f"no-vod:{clip['id']}"
        if per_vod.get(video_id, 0) >= MAX_CANDIDATES_PER_VOD:
            continue

        normalized_title = normalize_title(clip.get("title"))
        meaningful_title = (
            len(normalized_title) >= 6 and normalized_title not in GENERIC_TITLES
        )
        if meaningful_title and title_counts.get(normalized_title, 0) >= 2:
            continue

        selected.append(clip)
        per_vod[video_id] = per_vod.get(video_id, 0) + 1
        if meaningful_title:
            title_counts[normalized_title] = title_counts.get(normalized_title, 0) + 1
        if len(selected) >= CANDIDATE_COUNT:
            break

    print("Filter-Statistik:", counters)
    return selected


def main() -> None:
    print("=" * 56)
    print(f"CLIPCRIP SHARED DISCOVERY | {BROADCASTER_LOGIN}")
    print("=" * 56)

    session = build_session()
    try:
        token = get_token(session)
        broadcaster_id = get_broadcaster_id(session, token)
        clips = get_all_clips(token, broadcaster_id, session=session)
    finally:
        session.close()

    raw_used = load_json(USED_FILE, [])
    used_ids = {str(value) for value in raw_used} if isinstance(raw_used, list) else set()
    raw_history = load_json(HISTORY_FILE, {})
    history = raw_history if isinstance(raw_history, dict) else {}

    candidates = build_candidates(clips, used_ids, history)
    save_json(OUTPUT_FILE, candidates)

    print(f"{len(candidates)} frische, diverse Kandidaten gespeichert: {OUTPUT_FILE}")
    for index, candidate in enumerate(candidates, start=1):
        print(
            f"{index:02d}. {candidate['metadata_score']:5.1f} | "
            f"{candidate['duration']:4.1f}s | {candidate['view_count']:7d} Views | "
            f"{candidate['created_at'][:10]} | {candidate['title']}"
        )

    if not candidates:
        print("Kein frischer Kandidat verfügbar. Das ist ein gültiges Ergebnis.")


if __name__ == "__main__":
    main()
