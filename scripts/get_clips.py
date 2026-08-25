import os
import json
import datetime
import requests

CLIENT_ID = os.environ["TWITCH_CLIENT_ID"]
CLIENT_SECRET = os.environ["TWITCH_CLIENT_SECRET"]

BROADCASTER_LOGIN = "jussef"

ANZAHL_FINAL = 5
ANZAHL_KANDIDATEN = 20
SUCHZEITRAUM_TAGE = 30

USED_FILE = "used_clips.json"
HISTORY_FILE = "clip_history.json"


def get_token():
    response = requests.post(
        "https://id.twitch.tv/oauth2/token",
        data={
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "grant_type": "client_credentials",
        },
        timeout=30,
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
        timeout=30,
    )

    response.raise_for_status()

    data = response.json().get("data", [])

    if not data:
        raise RuntimeError(
            f"Twitch-User '{BROADCASTER_LOGIN}' wurde nicht gefunden."
        )

    return data[0]["id"]


def get_clips(token, broadcaster_id):
    headers = {
        "Client-Id": CLIENT_ID,
        "Authorization": f"Bearer {token}",
    }

    now = datetime.datetime.now(datetime.timezone.utc)

    since = (
        now - datetime.timedelta(days=SUCHZEITRAUM_TAGE)
    ).isoformat().replace("+00:00", "Z")

    clips = []
    cursor = None

    for _ in range(10):

        params = {
            "broadcaster_id": broadcaster_id,
            "started_at": since,
            "ended_at": now.isoformat().replace("+00:00", "Z"),
            "first": 100,
        }

        if cursor:
            params["after"] = cursor

        response = requests.get(
            "https://api.twitch.tv/helix/clips",
            params=params,
            headers=headers,
            timeout=30,
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
            return set(json.load(file))

    except Exception:
        return set()


def load_history():
    if not os.path.exists(HISTORY_FILE):
        return {}

    try:
        with open(
            HISTORY_FILE,
            "r",
            encoding="utf-8"
        ) as file:
            return json.load(file)

    except Exception:
        return {}


def score_clip(clip):

    views = int(
        clip.get(
            "view_count",
            0
        )
    )

    duration = float(
        clip.get(
            "duration",
            0
        )
    )

    score = 0

    # Views
    score += min(
        views,
        100000
    )

    # Gute TikTok-Länge
    if 12 <= duration <= 45:
        score += 30000

    elif 8 <= duration < 12:
        score += 5000

    elif 45 < duration <= 60:
        score += 10000

    elif duration > 60:
        score -= 15000

    title = str(
        clip.get(
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
        "reagiert",
        "rage",
        "fail",
        "geil",
        "bruder",
        "chat",
        "was",
        "warum",
    ]

    for word in interesting_words:
        if word in title:
            score += 5000

    return score


def main():

    print("================================")
    print("ClipCrip2 – 20 Kandidaten")
    print("================================")

    token = get_token()

    broadcaster_id = get_broadcaster_id(
        token
    )

    print(
        f"Suche Clips der letzten "
        f"{SUCHZEITRAUM_TAGE} Tage..."
    )

    clips = get_clips(
        token,
        broadcaster_id
    )

    print(
        f"{len(clips)} Clips gefunden."
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

        views = int(
            clip.get(
                "view_count",
                0
            )
        )

        # Exakt bereits verwendete Clips niemals erneut.
        if clip_id in used:
            continue

        # Zu kurze Clips raus.
        if duration < 8:
            continue

        # Clips ohne Views raus.
        if views <= 0:
            continue

        candidates.append({
            "id": clip_id,
            "title": clip.get(
                "title",
                ""
            ),
            "url": clip["url"],
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
            "score": score_clip(
                clip
            ),
        })

    candidates.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    candidates = candidates[
        :ANZAHL_KANDIDATEN
    ]

    if len(candidates) < ANZAHL_KANDIDATEN:
        raise RuntimeError(
            f"Nur {len(candidates)} neue "
            f"Kandidaten gefunden. "
            f"Benötigt werden {ANZAHL_KANDIDATEN}."
        )

    with open(
        "clips_today.json",
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            candidates,
            file,
            indent=2,
            ensure_ascii=False
        )

    print("")
    print(
        f"{len(candidates)} Kandidaten ausgewählt."
    )

    for i, clip in enumerate(
        candidates,
        start=1
    ):

        print(
            f"{i:02d}. "
            f"{clip['title']} | "
            f"{clip['view_count']} Views | "
            f"{clip['duration']:.1f}s"
        )

    print("")
    print(
        "WICHTIG: Kandidaten werden "
        "noch NICHT als benutzt markiert."
    )


if __name__ == "__main__":
    main()