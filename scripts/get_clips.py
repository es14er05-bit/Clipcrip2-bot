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
    r = requests.post(
        "https://id.twitch.tv/oauth2/token",
        data={
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "grant_type": "client_credentials"
        }
    )
    r.raise_for_status()
    return r.json()["access_token"]


def get_broadcaster_id(token):
    h = {
        "Client-Id": CLIENT_ID,
        "Authorization": f"Bearer {token}"
    }

    r = requests.get(
        "https://api.twitch.tv/helix/users",
        params={"login": BROADCASTER_LOGIN},
        headers=h
    )

    r.raise_for_status()

    data = r.json()["data"]

    if not data:
        raise RuntimeError(
            f"Twitch-User '{BROADCASTER_LOGIN}' nicht gefunden!"
        )

    return data[0]["id"]


def get_top_clips(token, bid):
    h = {
        "Client-Id": CLIENT_ID,
        "Authorization": f"Bearer {token}"
    }

    since = (
        datetime.datetime.utcnow()
        - datetime.timedelta(hours=24)
    ).isoformat("T") + "Z"

    r = requests.get(
        "https://api.twitch.tv/helix/clips",
        headers=h,
        params={
            "broadcaster_id": bid,
            "started_at": since,
            "first": 30
        }
    )

    r.raise_for_status()

    return r.json()["data"]


def load_used():
    if os.path.exists(USED_FILE):
        try:
            with open(
                USED_FILE,
                "r",
                encoding="utf-8"
            ) as f:
                return set(json.load(f))
        except Exception:
            return set()

    return set()


def main():
    token = get_token()

    bid = get_broadcaster_id(token)

    clips = get_top_clips(
        token,
        bid
    )

    print(
        f"Twitch hat {len(clips)} Clips gefunden."
    )

    used = load_used()

    auswahl = []

    for c in clips:

        if c["id"] in used:
            continue

        if c["duration"] < 5:
            continue

        thumbnail = c.get(
            "thumbnail_url",
            ""
        )

        download_url = (
            thumbnail.split(
                "-preview-"
            )[0] + ".mp4"
        )

        auswahl.append({
            "id": c["id"],
            "title": c["title"],
            "url": c["url"],
            "view_count": c["view_count"],
            "duration": c["duration"],
            "download_url": download_url
        })

        if len(auswahl) >= ANZAHL_CLIPS:
            break

    with open(
        "clips_today.json",
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            auswahl,
            f,
            indent=2,
            ensure_ascii=False
        )

    print(
        f"{len(auswahl)} neue Clips ausgewählt."
    )


if __name__ == "__main__":
    main()
