import os
import json
import datetime
import requests

CLIENT_ID = os.environ["TWITCH_CLIENT_ID"]
CLIENT_SECRET = os.environ["TWITCH_CLIENT_SECRET"]

BROADCASTER_LOGIN = "jussef"

ANZAHL_CLIPS = 5

# Wir suchen bis zu 30 Tage zurück.
SUCHZEITRAUM_TAGE = 30

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
            f"Twitch-User '{BROADCASTER_LOGIN}' wurde nicht gefunden."
        )

    return data[0]["id"]


def get_clips(token, broadcaster_id):
    headers = {
        "Client-Id": CLIENT_ID,
        "Authorization": f"Bearer {token}",
    }

    now = datetime.datetime.now(
        datetime.timezone.utc
    )

    started_at = (
        now - datetime.timedelta(
            days=SUCHZEITRAUM_TAGE
        )
    ).isoformat().replace(
        "+00:00",
        "Z"
    )

    ended_at = now.isoformat().replace(
        "+00:00",
        "Z"
    )

    clips = []
    cursor = None

    # Mehrere Seiten abrufen.
    # Dadurch können wir deutlich mehr als
    # nur die ersten 100 Clips durchsuchen.
    for page in range(10):

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
    if not os.path.exists(
        USED_FILE
    ):
        return set()

    try:

        with open(
            USED_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            data = json.load(file)

            if isinstance(data, list):
                return set(data)

            return set()

    except (
        json.JSONDecodeError,
        OSError,
        TypeError
    ):
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
            indent=2,
            ensure_ascii=False
        )


def calculate_score(clip):

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

    score = float(views)

    # Zu kurze Clips abwerten
    if duration < 8:
        score *= 0.25

    # Gute TikTok-Länge bevorzugen
    elif 12 <= duration <= 45:
        score *= 1.15

    # Sehr lange Clips leicht abwerten
    elif duration > 60:
        score *= 0.85

    return score


def main():

    print("================================")
    print("ClipCrip2 – Clip-Auswahl")
    print("================================")

    token = get_token()

    print(
        f"Streamer: {BROADCASTER_LOGIN}"
    )

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
        f"{len(clips)} Clips insgesamt gefunden."
    )

    used = load_used()

    print(
        f"{len(used)} Clips bereits verwendet."
    )

    candidates = []

    for clip in clips:

        clip_id = clip["id"]

        # Bereits verwendete Clips niemals erneut nehmen.
        if clip_id in used:
            continue

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

        # Sehr kurze Clips raus.
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

            "score": calculate_score(
                clip
            ),
        })

    # Beste Kandidaten zuerst.
    candidates.sort(
        key=lambda clip: clip["score"],
        reverse=True
    )

    auswahl = candidates[
        :ANZAHL_CLIPS
    ]

    # WICHTIG:
    # Wir markieren die Clips NICHT mehr hier als benutzt.
    #
    # Erst wenn der komplette Workflow erfolgreich
    # durchgelaufen ist, sollte ein Clip als verwendet
    # gelten.
    #
    # Für deinen jetzigen Workflow behalten wir
    # die Auswahldatei deshalb getrennt.

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

    print("")
    print("================================")
    print(
        f"{len(auswahl)} neue Clips ausgewählt."
    )
    print("================================")

    for number, clip in enumerate(
        auswahl,
        start=1
    ):

        print(
            f"{number}. "
            f"{clip['title']} | "
            f"{clip['view_count']} Views | "
            f"{clip['duration']:.1f}s"
        )

    if len(auswahl) < ANZAHL_CLIPS:

        print("")
        print(
            "WARNUNG:"
        )

        print(
            f"Es wurden nur {len(auswahl)} "
            f"statt {ANZAHL_CLIPS} neue Clips gefunden."
        )

        print(
            "Es werden keine alten Clips "
            "doppelt verwendet."
        )


if __name__ == "__main__":
    main()
