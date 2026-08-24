import os
import json
import datetime
import requests
import math

CLIENT_ID = os.environ["TWITCH_CLIENT_ID"]
CLIENT_SECRET = os.environ["TWITCH_CLIENT_SECRET"]

BROADCASTER_LOGIN = "jussef"

ANZAHL_CLIPS = 5

# So weit suchen wir zurück
SUCHZEITRAUM_TAGE = 30

# Datei mit bereits erfolgreich verwendeten Clips
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

    # Mehrere Seiten durchsuchen
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

            data = json.load(file)

            if isinstance(data, list):
                return set(data)

    except Exception:
        pass

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

    score = 0.0

    # ------------------------------------------------
    # 1. VIEWS
    # ------------------------------------------------

    # Logarithm verhindert, dass ein Clip mit extrem
    # vielen Views alles andere automatisch dominiert.

    if views > 0:
        score += math.log10(
            views + 1
        ) * 25


    # ------------------------------------------------
    # 2. IDEALE CLIP-LÄNGE
    # ------------------------------------------------

    if 12 <= duration <= 40:

        score += 35

    elif 10 <= duration < 12:

        score += 20

    elif 40 < duration <= 55:

        score += 15

    elif 8 <= duration < 10:

        score += 5

    elif duration > 60:

        score -= 20


    # ------------------------------------------------
    # 3. SEHR KURZE CLIPS STARK ABWERTEN
    # ------------------------------------------------

    if duration < 8:

        score -= 100


    # ------------------------------------------------
    # 4. SWEET SPOT
    # ------------------------------------------------

    # Clips zwischen ca. 18 und 35 Sekunden sind
    # häufig gut für kurze Social-Videos.

    if 18 <= duration <= 35:

        score += 15


    # ------------------------------------------------
    # 5. CLIP TITEL
    # ------------------------------------------------

    title = clip.get(
        "title",
        ""
    ).lower()

    # Titel mit typischen Reaktions-/Moment-Wörtern
    # bekommen einen kleinen Bonus.

    positive_words = [
        "lol",
        "haha",
        "hahaha",
        "wtf",
        "bro",
        "bruder",
        "digga",
        "krank",
        "wild",
        "geil",
        "lustig",
        "wieso",
        "warum",
        "was",
        "nein",
        "ne",
        "alter",
        "junge",
        "chat",
        "reaction",
        "reaktion",
        "rage",
        "ausraster",
        "wtf",
        "omg",
    ]

    for word in positive_words:

        if word in title:

            score += 8


    # ------------------------------------------------
    # 6. LEERE / SEHR UNAUFFÄLLIGE TITEL
    # ------------------------------------------------

    if len(title.strip()) < 4:

        score -= 5


    return score


def main():

    print("")
    print("========================================")
    print("ClipCrip2 – intelligente Clip-Auswahl")
    print("========================================")

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
        f"Insgesamt gefunden: {len(clips)}"
    )

    used = load_used()

    print(
        f"Bereits verwendet: {len(used)}"
    )


    # ================================================
    # KANDIDATEN FILTERN
    # ================================================

    candidates = []

    for clip in clips:

        clip_id = clip.get(
            "id"
        )

        if not clip_id:
            continue


        # Bereits benutzt
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


        # --------------------------------------------
        # HARTE FILTER
        # --------------------------------------------

        # Unter 8 Sekunden wird komplett entfernt.
        if duration < 8:
            continue

        # Keine Views = sehr wahrscheinlich ungeeignet.
        if views <= 0:
            continue


        score = calculate_score(
            clip
        )


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


    print(
        f"Kandidaten nach Filter: "
        f"{len(candidates)}"
    )


    # ================================================
    # NACH SCORE SORTIEREN
    # ================================================

    candidates.sort(
        key=lambda clip: clip["score"],
        reverse=True
    )


    # ================================================
    # TOP 5
    # ================================================

    auswahl = candidates[
        :ANZAHL_CLIPS
    ]


    # ================================================
    # CLIPS FÜR HEUTIGEN RUN SPEICHERN
    # ================================================

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


    # ================================================
    # AUSGABE
    # ================================================

    print("")
    print("========================================")
    print(
        f"AUSGEWÄHLT: {len(auswahl)} / {ANZAHL_CLIPS}"
    )
    print("========================================")

    for number, clip in enumerate(
        auswahl,
        start=1
    ):

        print(
            f"{number}. "
            f"{clip['title']} | "
            f"{clip['view_count']} Views | "
            f"{clip['duration']:.1f}s | "
            f"Score {clip['score']:.1f}"
        )


    # ================================================
    # WARNUNG WENN ZU WENIG
    # ================================================

    if len(auswahl) < ANZAHL_CLIPS:

        print("")
        print("⚠️ WARNUNG")
        print(
            f"Nur {len(auswahl)} "
            f"brauchbare neue Clips gefunden."
        )

        print(
            "Es werden keine bereits verwendeten "
            "Clips wiederholt."
        )


    print("")
    print("Clip-Auswahl abgeschlossen.")
    print("========================================")


if __name__ == "__main__":
    main()
