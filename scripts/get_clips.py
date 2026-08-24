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
        params={"login": BROADCASTER_LOGIN},
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

    now = datetime.datetime.now(datetime.timezone.utc)

    started_at = (
        now - datetime.timedelta(hours=24)
    ).isoformat()

    ended_at = now.isoformat()

    clips = []
    cursor = None

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

        clips.extend(result.get("data", []))

        cursor = result.get(
            "pagination", {}
        ).get("cursor")

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
            return set(json.load(file))
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
    views = clip.get("view_count", 0)
    duration = float(
        clip.get("duration", 0)
    )

    score = views

    if duration < 8:
        score *= 0.5

    if 12 <= duration <= 45:
        score *= 1.15

    if duration > 60:
        score *= 0.85

    return score


def make_download_url(thumbnail_url):
    """
    Twitch stellt die Clip-Videodatei über die
    bekannte Twitch-Clip-Downloadstruktur bereit.
    """

    if not thumbnail_url:
        return None

    base = thumbnail_url.split("-preview-")[0]

    return base + ".mp4"


def main():
    print("================================")
    print("ClipCrip2 – Twitch Clip Auswahl")
    print("================================")

    token = get_token()

    broadcaster_id = get_broadcaster_id(
        token
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
            clip.get("duration", 0)
        )

        views = clip.get(
            "view_count", 0
        )

        if clip_id in used:
            continue

        if duration < 8:
            continue

        if views <= 0:
            continue

        thumbnail = clip.get(
            "thumbnail_url", ""
        )

        download_url = make_download_url(
            thumbnail
        )

        if not download_url:
            continue

        score = calculate_score(
            clip
        )

        candidates.append({
            "id": clip_id,
            "title": clip.get(
                "title", ""
            ),
            "url": clip.get(
                "url", ""
            ),
            "download_url": download_url,
            "view_count": views,
            "duration": duration,
            "creator_name": clip.get(
                "creator_name", ""
            ),
            "created_at": clip.get(
                "created_at", ""
            ),
            "thumbnail_url": thumbnail,
            "score": score
        })

    candidates.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    auswahl = candidates[:ANZAHL_CLIPS]

    print("")
    print("TOP CLIPS:")

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

    for clip in auswahl:
        used.add(clip["id"])

    save_used(used)

    print("")
    print(
        f"{len(auswahl)} neue Clips ausgewählt."
    )


if __name__ == "__main__":
    main()
