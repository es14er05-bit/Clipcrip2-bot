import os
import json
import datetime
import requests
import hashlib

CLIENT_ID = os.environ["TWITCH_CLIENT_ID"]
CLIENT_SECRET = os.environ["TWITCH_CLIENT_SECRET"]

BROADCASTER_LOGIN = "jussef"

ANZAHL_CLIPS = 5
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
        params={"login": BROADCASTER_LOGIN},
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

    # Mehrere Seiten abrufen.
    # Dadurch sind wir nicht auf die ersten 100 Clips beschränkt.
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

        clips.extend(result.get("data", []))

        cursor = result.get("pagination", {}).get("cursor")

        if not cursor:
            break

    return clips


def load_json(filename, default):
    if not os.path.exists(filename):
        return default

    try:
        with open(filename, "r", encoding="utf-8") as file:
            data = json.load(file)

        return data

    except (json.JSONDecodeError, OSError):
        return default


def save_json(filename, data):
    with open(filename, "w", encoding="utf-8") as file:
        json.dump(
            data,
            file,
            indent=2,
            ensure_ascii=False,
        )


def make_content_key(clip):
    """
    Erstellt einen zusätzlichen Schlüssel aus dem
    eigentlichen Clip-Inhalt/Metadaten.

    Die Twitch-ID bleibt der wichtigste Schutz gegen
    exakte Wiederholungen.
    """

    title = str(
        clip.get("title", "")
    ).strip().lower()

    creator = str(
        clip.get("creator_name", "")
    ).strip().lower()

    created = str(
        clip.get("created_at", "")
    )

    duration = round(
        float(
            clip.get("duration", 0)
        ),
        1,
    )

    raw = (
        f"{title}|"
        f"{creator}|"
        f"{created}|"
        f"{duration}"
    )

    return hashlib.sha1(
        raw.encode("utf-8")
    ).hexdigest()


def clip_score(clip):
    views = int(
        clip.get("view_count", 0)
    )

    duration = float(
        clip.get("duration", 0)
    )

    score = 0.0

    # Views sind ein gutes Signal,
    # aber nicht das einzige.
    score += min(views, 100000) * 1.0

    # Zu kurze Clips sind meistens schlechter.
    if duration < 8:
        score -= 50000

    # Gute TikTok-Länge bevorzugen.
    if 12 <= duration <= 45:
        score += 25000

    # Sehr lange Clips leicht abwerten.
    if duration > 60:
        score -= 15000

    # Titel berücksichtigen.
    title = str(
        clip.get("title", "")
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
        "was",
        "warum",
        "chat",
    ]

    for word in interesting_words:
        if word in title:
            score += 5000

    return score


def main():
    print("================================")
    print("ClipCrip2 – intelligente Auswahl")
    print("================================")

    token = get_token()

    broadcaster_id = get_broadcaster_id(
        token
    )

    print(
        f"Suche Clips von "
        f"{BROADCASTER_LOGIN}..."
    )

    clips = get_clips(
        token,
        broadcaster_id
    )

    print(
        f"{len(clips)} Clips gefunden."
    )

    used_ids = set(
        load_json(
            USED_FILE,
            []
        )
    )

    history = load_json(
        HISTORY_FILE,
        {}
    )

    candidates = []

    for clip in clips:

        clip_id = clip["id"]

        duration = float(
            clip.get("duration", 0)
        )

        views = int(
            clip.get("view_count", 0)
        )

        # Exakt verwendete Twitch-Clips niemals wieder nehmen.
        if clip_id in used_ids:
            continue

        # Zu kurze Clips ignorieren.
        if duration < 8:
            continue

        # Clips ohne Aufrufe ignorieren.
        if views <= 0:
            continue

        content_key = make_content_key(
            clip
        )

        # Bereits in unserer Historie vorhanden.
        if content_key in history:
            continue

        score = clip_score(
            clip
        )

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
            "content_key": content_key,
            "score": score,
        })

    candidates.sort(
        key=lambda clip: clip["score"],
        reverse=True
    )

    auswahl = candidates[
        :ANZAHL_CLIPS
    ]

    if len(auswahl) < ANZAHL_CLIPS:
        raise RuntimeError(
            f"Nur {len(auswahl)} wirklich neue "
            f"Clips gefunden. Benötigt werden "
            f"{ANZAHL_CLIPS}."
        )

    print("")
    print("AUSGEWÄHLTE CLIPS:")

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

    # Für Download-Script.
    with open(
        "clips_today.json",
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            auswahl,
            file,
            indent=2,
            ensure_ascii=False,
        )

    # Twitch IDs dauerhaft markieren.
    for clip in auswahl:
        used_ids.add(
            clip["id"]
        )

        history[
            clip["content_key"]
        ] = {
            "clip_id": clip["id"],
            "title": clip["title"],
            "created_at": clip["created_at"],
        }

    save_json(
        USED_FILE,
        sorted(list(used_ids))
    )

    save_json(
        HISTORY_FILE,
        history
    )

    print("")
    print(
        f"{len(auswahl)} neue Clips ausgewählt."
    )
    print(
        "IDs und Historie gespeichert."
    )


if __name__ == "__main__":
    main()