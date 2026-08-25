import os
import json
import datetime
import requests

CLIENT_ID = os.environ["TWITCH_CLIENT_ID"]
CLIENT_SECRET = os.environ["TWITCH_CLIENT_SECRET"]

BROADCASTER_LOGIN = "jussef"

# Wir holen deutlich mehr Kandidaten.
KANDIDATEN_ANZAHL = 40

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


def get_clips(token, broadcaster_id):
    headers = {
        "Client-Id": CLIENT_ID,
        "Authorization": f"Bearer {token}",
    }

    now = datetime.datetime.now(datetime.timezone.utc)

    since = (
        now - datetime.timedelta(days=SUCHZEITRAUM_TAGE)
    ).isoformat().replace("+00:00", "Z")

    until = now.isoformat().replace("+00:00", "Z")

    all_clips = []
    cursor = None

    # Mehrere Seiten abrufen.
    for page in range(10):

        params = {
            "broadcaster_id": broadcaster_id,
            "started_at": since,
            "ended_at": until,
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

        clips = result.get("data", [])

        all_clips.extend(clips)

        print(
            f"Twitch-Seite {page + 1}: "
            f"{len(clips)} Clips"
        )

        cursor = (
            result
            .get("pagination", {})
            .get("cursor")
        )

        if not cursor:
            break

    return all_clips


def load_used():
    if not os.path.exists(USED_FILE):
        return set()

    try:
        with open(
            USED_FILE,
            "r",
            encoding="utf-8",
        ) as file:
            data = json.load(file)

        if not isinstance(data, list):
            return set()

        return set(data)

    except Exception:
        return set()


def calculate_candidate_score(clip):
    """
    Nur eine VORauswahl.
    Die eigentliche Qualitätskontrolle passiert später.
    """

    score = 0.0

    views = int(
        clip.get(
            "view_count",
            0,
        )
    )

    duration = float(
        clip.get(
            "duration",
            0,
        )
    )

    # Views sind nur ein Signal.
    score += min(views / 500.0, 30.0)

    # Sinnvolle Clip-Längen bevorzugen.
    if 10 <= duration <= 45:
        score += 15

    elif 8 <= duration < 10:
        score += 3

    elif 45 < duration <= 60:
        score += 8

    elif duration > 90:
        score -= 10

    # Titel nur als sehr kleines Signal.
    title = str(
        clip.get(
            "title",
            "",
        )
    ).lower()

    keywords = [
        "lol",
        "haha",
        "wtf",
        "crazy",
        "rage",
        "fail",
        "eskaliert",
        "lustig",
        "lachen",
        "bruder",
        "reaktion",
        "chat",
    ]

    for keyword in keywords:
        if keyword in title:
            score += 2

    return score


def main():
    print("================================")
    print("CLIPCRIP2 – KANDIDATENSUCHE")
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
        broadcaster_id,
    )

    print(
        f"Insgesamt gefunden: "
        f"{len(clips)}"
    )

    used = load_used()

    candidates = []

    for clip in clips:

        clip_id = clip.get("id")

        if not clip_id:
            continue

        # Bereits endgültig verwendete Clips NICHT wieder nehmen.
        if clip_id in used:
            continue

        duration = float(
            clip.get(
                "duration",
                0,
            )
        )

        # Extrem kurze Clips raus.
        if duration < 8:
            continue

        # Sehr lange Clips nicht komplett ausschließen,
        # aber deutlich nach hinten sortieren.
        score = calculate_candidate_score(
            clip
        )

        candidates.append(
            {
                "id": clip_id,
                "title": clip.get(
                    "title",
                    "",
                ),
                "url": clip.get(
                    "url",
                    "",
                ),
                "view_count": int(
                    clip.get(
                        "view_count",
                        0,
                    )
                ),
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
                "candidate_score": score,
            }
        )

    candidates.sort(
        key=lambda x: x["candidate_score"],
        reverse=True,
    )

    # 40 Kandidaten an Download/QC weitergeben.
    selected_candidates = candidates[
        :KANDIDATEN_ANZAHL
    ]

    with open(
        "clips_today.json",
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            selected_candidates,
            file,
            indent=2,
            ensure_ascii=False,
        )

    print("")
    print("================================")
    print(
        f"{len(selected_candidates)} "
        "KANDIDATEN AUSGEWÄHLT"
    )
    print("================================")

    for number, clip in enumerate(
        selected_candidates,
        start=1,
    ):
        print(
            f"{number:02d}. "
            f"{clip['title']} | "
            f"{clip['view_count']} Views | "
            f"{clip['duration']:.1f}s"
        )

    print("")
    print(
        "WICHTIG: Kandidaten werden "
        "NOCH NICHT als benutzt markiert."
    )
    print(
        "Das passiert erst nach erfolgreicher "
        "Qualitätskontrolle."
    )


if __name__ == "__main__":
    main()