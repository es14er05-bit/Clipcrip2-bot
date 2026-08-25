import os
import json
import datetime
import requests

CLIENT_ID = os.environ["TWITCH_CLIENT_ID"]
CLIENT_SECRET = os.environ["TWITCH_CLIENT_SECRET"]

BROADCASTER_LOGIN = "jussef"

# Wir sammeln viele Kandidaten.
# Die Quality-Control entscheidet später, welche 5 wirklich gut sind.
KANDIDATEN_ANZAHL = 40

SUCHZEITRAUM_TAGE = 30
USED_FILE = "used_clips.json"
OUTPUT_FILE = "clips_today.json"


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
        timeout=30,
    )

    response.raise_for_status()

    return response.json().get("data", [])


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

    except (
        json.JSONDecodeError,
        OSError,
        TypeError,
    ):
        return set()


def save_candidates(candidates):
    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            candidates,
            file,
            indent=2,
            ensure_ascii=False
        )


def main():

    print("================================")
    print("CLIPCRIP2 – CANDIDATEN SAMMLER")
    print("================================")

    token = get_token()

    print(
        f"Twitch-Kanal: {BROADCASTER_LOGIN}"
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
        f"{len(clips)} Twitch-Clips gefunden."
    )

    used = load_used()

    print(
        f"{len(used)} Clips befinden sich "
        "bereits in der Used-History."
    )

    # Zuerst nach Twitch-Views sortieren.
    # Das ist KEINE finale Qualitätsbewertung.
    # Es sorgt nur dafür, dass gute Kandidaten
    # weiter oben stehen.
    clips.sort(
        key=lambda clip: clip.get(
            "view_count",
            0
        ),
        reverse=True,
    )

    candidates = []

    seen_ids = set()

    for clip in clips:

        clip_id = clip.get("id")

        if not clip_id:
            continue

        # Doppelte IDs innerhalb desselben Laufs verhindern.
        if clip_id in seen_ids:
            continue

        seen_ids.add(clip_id)

        # Bereits final verwendete Clips niemals erneut auswählen.
        if clip_id in used:
            continue

        duration = float(
            clip.get(
                "duration",
                0
            )
        )

        # Extrem kurze Clips sind für unsere Verarbeitung
        # normalerweise nicht sinnvoll.
        if duration < 8:
            continue

        title = str(
            clip.get(
                "title",
                ""
            )
        ).strip()

        url = clip.get("url")

        if not url:
            continue

        candidate = {
            "id": clip_id,

            "title": title,

            "url": url,

            "view_count": int(
                clip.get(
                    "view_count",
                    0
                )
            ),

            "creator_name": clip.get(
                "creator_name",
                ""
            ),

            "created_at": clip.get(
                "created_at",
                ""
            ),

            "duration": duration,

            "broadcaster_name": clip.get(
                "broadcaster_name",
                BROADCASTER_LOGIN
            ),

            # Wichtig für spätere Qualitätskontrolle.
            "source": "twitch",

            "selected_by": "candidate_pool",
        }

        candidates.append(
            candidate
        )

        if len(candidates) >= KANDIDATEN_ANZAHL:
            break

    save_candidates(
        candidates
    )

    print("")
    print("================================")
    print(
        f"{len(candidates)} FRISCHE "
        "KANDIDATEN GESPEICHERT"
    )
    print("================================")

    if not candidates:

        print(
            "KEINE NEUEN KANDIDATEN GEFUNDEN."
        )

        print(
            "Die Quality-Control wird "
            "deshalb nicht gestartet werden "
            "können."
        )

        # Absichtlich KEINEN used-Eintrag verändern.
        # Wir wollen niemals einen Clip als benutzt
        # markieren, bevor er tatsächlich ausgewählt
        # und verarbeitet wurde.
        raise RuntimeError(
            "Keine neuen Twitch-Clips verfügbar."
        )

    for number, clip in enumerate(
        candidates,
        start=1
    ):

        print(
            f"{number:02d}. "
            f"{clip['title']} | "
            f"{clip['duration']:.1f}s | "
            f"{clip['view_count']} Views"
        )

    print("")
    print(
        "WICHTIG: Diese Clips wurden "
        "NOCH NICHT als benutzt markiert."
    )

    print(
        "Die endgültige Auswahl übernimmt "
        "die Quality-Control."
    )


if __name__ == "__main__":
    main()