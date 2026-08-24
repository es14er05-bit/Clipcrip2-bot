import os
import json
import datetime
import requests

CLIENT_ID = os.environ["TWITCH_CLIENT_ID"]
CLIENT_SECRET = os.environ["TWITCH_CLIENT_SECRET"]

BROADCASTER_LOGIN = "jussef"

ANZAHL_CLIPS = 5

USED_FILE = "used_clips.json"


def get_token():

    response = requests.post(
        "https://id.twitch.tv/oauth2/token",
        data={
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "grant_type": "client_credentials",
        },
    )

    response.raise_for_status()

    return response.json()["access_token"]


def get_broadcaster_id(token):

    headers = {
        "Client-Id": CLIENT_ID,
        "Authorization": f"Bearer {token}",
    }

    response = requests.get(
        "https://api.twitch.tv/helix/users",
        params={
            "login": BROADCASTER_LOGIN
        },
        headers=headers,
    )

    response.raise_for_status()

    data = response.json()["data"]

    if not data:
        raise RuntimeError(
            f"Twitch-User '{BROADCASTER_LOGIN}' nicht gefunden."
        )

    return data[0]["id"]


def get_all_clips(token, broadcaster_id):

    headers = {
        "Client-Id": CLIENT_ID,
        "Authorization": f"Bearer {token}",
    }

    now = datetime.datetime.now(
        datetime.timezone.utc
    )

    started_at = (
        now - datetime.timedelta(hours=24)
    ).isoformat()

    ended_at = now.isoformat()

    clips = []

    cursor = None

    # Mehrere Seiten abrufen
    for _ in range(5):

        params = {
            "broadcaster_id": broadcaster_id,
            "started_at": started_at,
            "ended_at": ended_at,
            "first": 100,
        }

        if cursor:
            params["after"] = cursor

        response = requests.get(
            "https://api.twitch.tv/helix/clips",
            params=params,
            headers=headers,
        )

        response.raise_for_status()

        result = response.json()

        clips.extend(
            result.get("data", [])
        )

        cursor = (
            result
            .get("pagination", {})
            .get("cursor")
        )

        if not cursor:
            break

    return clips


def load_used():

    if not os.path.exists(USED_FILE):
        return set()

    try:

        with open(
            USED_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            return set(
                json.load(file)
            )

    except Exception:

        return set()


def save_used(used):

    with open(
        USED_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            sorted(list(used)),
            file,
            indent=2
        )


def calculate_score(clip):

    views = clip.get(
        "view_count",
        0
    )

    duration = float(
        clip.get(
            "duration",
            0
        )
    )

    score = 0

    # Views sind das wichtigste Signal
    score += views * 1.0

    # Sehr kurze Clips vermeiden
    if duration < 8:
        score *= 0.5

    # Sweet Spot für kurze TikTok-Clips
    if 12 <= duration <= 45:
        score *= 1.15

    # Extrem lange Clips etwas abwerten
    if duration > 60:
        score *= 0.85

    return score


def main():

    print(
        "================================"
    )

    print(
        "ClipCrip2 – Twitch Clip Auswahl"
    )

    print(
        "================================"
    )

    token = get_token()

    broadcaster_id = get_broadcaster_id(
        token
    )

    print(
        f"Streamer: {BROADCASTER_LOGIN}"
    )

    clips = get_all_clips(
        token,
        broadcaster_id
    )

    print(
        f"Gefundene Clips: {len(clips)}"
    )

    used = load_used()

    candidates = []

    for clip in clips:

        clip_id = clip["id"]

        duration = float(
            clip.get(
                "duration",
                0
            )
        )

        views = clip.get(
            "view_count",
            0
        )

        # Bereits verwendete Clips überspringen
        if clip_id in used:
            continue

        # Zu kurze Clips überspringen
        if duration < 8:
            continue

        # Keine Views = wahrscheinlich ungeeignet
        if views <= 0:
            continue

        score = calculate_score(
            clip
        )

        candidates.append({
            "id": clip_id,
            "title": clip.get(
                "title",
                ""
            ),
            "url": clip.get(
                "url",
                ""
            ),
            "view_count": views,
            "duration": duration,
            "creator_name": clip.get(
                "creator_name",
                ""
            ),
            "created_at": clip.get(
                "created_at",
                ""
            ),
            "thumbnail_url": clip.get(
                "thumbnail_url",
                ""
            ),
            "score": score,
        })

    # Höchsten Score zuerst
    candidates.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    auswahl = candidates[
        :ANZAHL_CLIPS
    ]

    print("")
    print(
        "TOP CLIPS:"
    )

    for index, clip in enumerate(
        auswahl,
        start=1
    ):

        print(
            f"{index}. "
            f"{clip['title']} | "
            f"{clip['view_count']} Views | "
            f"{clip['duration']:.1f}s"
        )

    # Für Download-Script speichern
    with open(
        "clips_today.json",
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            auswahl,
            file,
            indent=2,
            ensure_ascii=False
        )

    # Ausgewählte Clips als verwendet markieren
    for clip in auswahl:

        used.add(
            clip["id"]
        )

    save_used(
        used
    )

    print("")
    print(
        f"{len(auswahl)} neue Clips ausgewählt."
    )

    print(
        "================================"
    )


if __name__ == "__main__":
    main()
