import os
import json
import datetime
import requests

CLIENT_ID = os.environ["TWITCH_CLIENT_ID"]
CLIENT_SECRET = os.environ["TWITCH_CLIENT_SECRET"]

BROADCASTER_LOGIN = "jussef"

ANZAHL_CLIPS = 5
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
        params={"login": BROADCASTER_LOGIN},
        headers=headers,
    )

    response.raise_for_status()

    data = response.json()["data"]

    if not data:
        raise SystemExit(
            f"Twitch-User '{BROADCASTER_LOGIN}' wurde nicht gefunden."
        )

    return data[0]["id"]


def get_clips(token, broadcaster_id):
    headers = {
        "Client-Id": CLIENT_ID,
        "Authorization": f"Bearer {token}",
    }

    since = (
        datetime.datetime.now(datetime.timezone.utc)
        - datetime.timedelta(days=SUCHZEITRAUM_TAGE)
    ).isoformat().replace("+00:00", "Z")

    response = requests.get(
        "https://api.twitch.tv/helix/clips",
        params={
            "broadcaster_id": broadcaster_id,
            "started_at": since,
            "first": 100,
        },
        headers=headers,
    )

    response.raise_for_status()

    return response.json()["data"]


def load_used():
    if not os.path.exists(USED_FILE):
        return set()

    try:
        with open(USED_FILE, "r", encoding="utf-8") as file:
            return set(json.load(file))
    except (json.JSONDecodeError, OSError):
        return set()


def save_used(used):
    with open(USED_FILE, "w", encoding="utf-8") as file:
        json.dump(
            sorted(list(used)),
            file,
            indent=2,
            ensure_ascii=False,
        )


def main():
    print("Starte ClipCrip2...")

    token = get_token()

    print(f"Suche Twitch-Kanal: {BROADCASTER_LOGIN}")

    broadcaster_id = get_broadcaster_id(token)

    print(
        f"Suche Clips der letzten "
        f"{SUCHZEITRAUM_TAGE} Tage..."
    )

    clips = get_clips(token, broadcaster_id)

    print(f"{len(clips)} Clips insgesamt gefunden.")

    # Nach Aufrufen sortieren: beliebteste zuerst
    clips.sort(
        key=lambda clip: clip.get("view_count", 0),
        reverse=True,
    )

    used = load_used()

    auswahl = []

    for clip in clips:
        clip_id = clip["id"]

        # Bereits verwendete Clips überspringen
        if clip_id in used:
            continue

        # Extrem kurze Clips überspringen
        if clip.get("duration", 0) < 5:
            continue

        auswahl.append(
            {
                "id": clip_id,
                "title": clip.get("title", ""),
                "url": clip["url"],
                "view_count": clip.get("view_count", 0),
                "creator_name": clip.get("creator_name", ""),
                "created_at": clip.get("created_at", ""),
            }
        )

        if len(auswahl) >= ANZAHL_CLIPS:
            break

    # IDs der ausgewählten Clips als benutzt markieren
    for clip in auswahl:
        used.add(clip["id"])

    save_used(used)

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

    print("")
    print("==============================")
    print(f"{len(auswahl)} Clips ausgewählt.")
    print("==============================")

    for number, clip in enumerate(auswahl, start=1):
        print(
            f"{number}. "
            f"{clip['title']} | "
            f"{clip['view_count']} Views"
        )


if __name__ == "__main__":
    main()
