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
        now - datetime.timedelta(days=SUCHZEITRAUM_TAGE)
    ).isoformat().replace("+00:00", "Z")

    ended_at = now.isoformat().replace("+00:00", "Z")

    clips = []
    cursor = None

    for _ in range(10):

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

        clips.extend(result.get("data", []))

        cursor = result.get("pagination", {}).get("cursor")

        if not cursor:
            break

    return clips


def load_used():
    if not os.path.exists(USED_FILE):
        return set()

    try:
        with open(USED_FILE, "r", encoding="utf-8") as file:
            return set(json.load(file))
    except Exception:
        return set()


def save_used(used):
    with open(USED_FILE, "w", encoding="utf-8") as file:
        json.dump(
            sorted(used),
            file,
            indent=2,
            ensure_ascii=False,
        )


def score_clip(clip):
    views = int(clip.get("view_count", 0))
    duration = float(clip.get("duration", 0))

    score = 0

    # Popularität
    score += min(views, 100000) * 1.0

    # Gute TikTok-Länge bevorzugen
    if 12 <= duration <= 45:
        score += 3000

    elif 8 <= duration < 12:
        score += 500

    elif 45 < duration <= 60:
        score += 1000

    elif duration > 60:
        score -= 5000

    # Extrem kurze Clips vermeiden
    if duration < 8:
        score -= 10000

    return score


def main():

    print("================================")
    print("ClipCrip2 – intelligente Auswahl")
    print("================================")

    token = get_token()

    broadcaster_id = get_broadcaster_id(token)

    print(f"Streamer: {BROADCASTER_LOGIN}")
    print(f"Zeitraum: letzte {SUCHZEITRAUM_TAGE} Tage")

    clips = get_all_clips(
        token,
        broadcaster_id,
    )

    print(f"Gefundene Clips: {len(clips)}")

    used = load_used()

    candidates = []

    for clip in clips:

        clip_id = clip["id"]

        if clip_id in used:
            continue

        duration = float(
            clip.get("duration", 0)
        )

        views = int(
            clip.get("view_count", 0)
        )

        # Mindestqualität
        if duration < 8:
            continue

        if views < 2:
            continue

        score = score_clip(clip)

        candidates.append({
            "id": clip_id,
            "title": clip.get("title", ""),
            "url": clip.get("url", ""),
            "view_count": views,
            "duration": duration,
            "creator_name": clip.get(
                "creator_name",
                "",
            ),
            "created_at": clip.get(
                "created_at",
                "",
            ),
            "thumbnail_url": clip.get(
                "thumbnail_url",
                "",
            ),
            "score": score,
        })

    candidates.sort(
        key=lambda x: x["score"],
        reverse=True,
    )

    auswahl = candidates[:ANZAHL_CLIPS]

    # Nur tatsächlich ausgewählte Clips als benutzt markieren
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
    print("TOP AUSWAHL:")

    for i, clip in enumerate(
        auswahl,
        start=1,
    ):
        print(
            f"{i}. "
            f"{clip['title']} | "
            f"{clip['view_count']} Views | "
            f"{clip['duration']:.1f}s"
        )

    print("")
    print(
        f"{len(auswahl)} neue Clips ausgewählt."
    )

    if len(auswahl) < ANZAHL_CLIPS:
        print(
            "WARNUNG: Es wurden nicht genügend "
            "neue geeignete Clips gefunden."
        )

    print("================================")


if __name__ == "__main__":
    main()
