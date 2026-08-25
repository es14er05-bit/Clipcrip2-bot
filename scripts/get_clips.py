import os
import json
import datetime
import requests

CLIENT_ID = os.environ["TWITCH_CLIENT_ID"]
CLIENT_SECRET = os.environ["TWITCH_CLIENT_SECRET"]

BROADCASTER_LOGIN = "jussef"

# Wir holen bewusst mehr Kandidaten,
# damit die Bearbeitung später die besten auswählen kann.
KANDIDATEN = 20

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


def get_all_clips(token, broadcaster_id):
    headers = {
        "Client-Id": CLIENT_ID,
        "Authorization": f"Bearer {token}",
    }

    now = datetime.datetime.now(datetime.timezone.utc)

    started_at = (
        now - datetime.timedelta(days=SUCHZEITRAUM_TAGE)
    ).isoformat().replace("+00:00", "Z")

    ended_at = now.isoformat().replace("+00:00", "Z")

    clips = []
    cursor = None

    # Mehrere Seiten durchsuchen.
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
            timeout=30,
        )

        response.raise_for_status()

        result = response.json()

        page_clips = result.get("data", [])

        clips.extend(page_clips)

        print(
            f"Twitch-Seite {page + 1}: "
            f"{len(page_clips)} Clips"
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
            data = json.load(file)

        if not isinstance(data, list):
            return set()

        return set(data)

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
            indent=2,
            ensure_ascii=False,
        )


def score_clip(clip):
    """
    Bewertet einen Clip nach objektiven Signalen.

    Views = wichtigstes Signal
    Dauer = kurze, aber nicht extrem kurze Clips bevorzugen
    """

    views = int(
        clip.get("view_count", 0)
    )

    duration = float(
        clip.get("duration", 0)
    )

    score = 0.0

    # Views logarithmisch bewerten,
    # damit ein Clip mit extrem vielen Views
    # nicht alles andere komplett verdrängt.
    if views > 0:
        score += min(100, views ** 0.5) * 10

    # Sehr kurze Clips sind meistens ungeeignet.
    if duration < 8:
        score -= 1000

    elif duration < 12:
        score += 5

    elif duration <= 45:
        score += 30

    elif duration <= 60:
        score += 15

    else:
        score -= 10

    return score


def main():

    print("================================")
    print("ClipCrip2 – neue Clip-Auswahl")
    print("================================")

    token = get_token()

    broadcaster_id = get_broadcaster_id(
        token
    )

    print(
        f"Kanal: {BROADCASTER_LOGIN}"
    )

    print(
        f"Suche Clips der letzten "
        f"{SUCHZEITRAUM_TAGE} Tage..."
    )

    clips = get_all_clips(
        token,
        broadcaster_id
    )

    print(
        f"Insgesamt gefunden: {len(clips)}"
    )

    used = load_used()

    candidates = []

    for clip in clips:

        clip_id = clip.get("id")

        if not clip_id:
            continue

        # NIEMALS denselben Clip nochmal verwenden.
        if clip_id in used:
            continue

        duration = float(
            clip.get("duration", 0)
        )

        views = int(
            clip.get("view_count", 0)
        )

        # Unbrauchbare Clips direkt aussortieren.
        if duration < 8:
            continue

        if views <= 0:
            continue

        score = score_clip(clip)

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

    candidates.sort(
        key=lambda x: (
            x["score"],
            x["view_count"]
        ),
        reverse=True,
    )

    auswahl = candidates[:KANDIDATEN]

    if not auswahl:
        raise RuntimeError(
            "Keine neuen geeigneten Clips gefunden. "
            "Der Bot hat keine bereits verwendeten Clips "
            "erneut ausgewählt."
        )

    print("")
    print("KANDIDATEN:")
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

    # WICHTIG:
    # Die Clips werden erst hier als benutzt markiert,
    # damit bei einem Download-Problem keine Clips
    # unnötig verloren gehen.
    #
    # Die IDs bleiben trotzdem für zukünftige Runs gespeichert.
    for clip in auswahl:
        used.add(clip["id"])

    save_used(used)

    with open(
        "clips_today.json",
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            auswahl,
            file,
            indent=2,
            ensure_ascii=False,
        )

    print("")
    print(
        f"{len(auswahl)} neue Kandidaten gespeichert."
    )

    print("================================")


if __name__ == "__main__":
    main()
