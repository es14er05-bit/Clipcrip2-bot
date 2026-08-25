import os
import json
import datetime
import requests


CLIENT_ID = os.environ["TWITCH_CLIENT_ID"]
CLIENT_SECRET = os.environ["TWITCH_CLIENT_SECRET"]

BROADCASTER_LOGIN = "jussef"

# Wie viele Kandidaten die Quality-Control bekommen soll.
KANDIDATEN_ANZAHL = 40

# Großer Pool, damit auch nach vielen Tagen noch genug
# unbenutzte Kandidaten vorhanden sind.
SUCHZEITRAUM_TAGE = 365

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

    data = response.json().get(
        "data",
        []
    )

    if not data:

        raise RuntimeError(
            f"Twitch-User "
            f"'{BROADCASTER_LOGIN}' "
            f"wurde nicht gefunden."
        )

    return data[0]["id"]


def get_all_clips(
    token,
    broadcaster_id
):

    headers = {
        "Client-Id": CLIENT_ID,
        "Authorization": f"Bearer {token}",
    }

    since = (
        datetime.datetime.now(
            datetime.timezone.utc
        )
        - datetime.timedelta(
            days=SUCHZEITRAUM_TAGE
        )
    ).isoformat().replace(
        "+00:00",
        "Z"
    )

    clips = []

    cursor = None

    page = 1

    while True:

        params = {
            "broadcaster_id":
                broadcaster_id,

            "started_at":
                since,

            "first":
                100,
        }

        if cursor:

            params["after"] = cursor

        print(
            f"Twitch-Seite "
            f"{page} wird geladen..."
        )

        response = requests.get(
            "https://api.twitch.tv/helix/clips",
            params=params,
            headers=headers,
            timeout=30,
        )

        response.raise_for_status()

        result = response.json()

        page_clips = result.get(
            "data",
            []
        )

        clips.extend(
            page_clips
        )

        print(
            f"{len(page_clips)} Clips "
            f"auf Seite {page}."
        )

        pagination = result.get(
            "pagination",
            {}
        )

        cursor = pagination.get(
            "cursor"
        )

        if not cursor:
            break

        if not page_clips:
            break

        page += 1

        # Sicherheitslimit.
        # 20 Seiten = maximal 2000 Clips.
        if page > 20:

            print(
                "Sicherheitslimit von "
                "2000 Twitch-Clips erreicht."
            )

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

            data = json.load(
                file
            )

        if not isinstance(
            data,
            list
        ):
            return set()

        return set(
            data
        )

    except (
        json.JSONDecodeError,
        OSError,
        TypeError,
    ):

        return set()


def save_candidates(
    candidates
):

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

    print(
        "================================"
    )

    print(
        "CLIPCRIP2 – CANDIDATEN SAMMLER"
    )

    print(
        "================================"
    )

    token = get_token()

    print(
        f"Twitch-Kanal: "
        f"{BROADCASTER_LOGIN}"
    )

    broadcaster_id = (
        get_broadcaster_id(
            token
        )
    )

    print(
        f"Suche Clips der letzten "
        f"{SUCHZEITRAUM_TAGE} Tage..."
    )

    clips = get_all_clips(
        token,
        broadcaster_id
    )

    print("")

    print(
        f"{len(clips)} Twitch-Clips "
        f"insgesamt gefunden."
    )

    used = load_used()

    print(
        f"{len(used)} Clips befinden "
        f"sich bereits in der "
        f"Used-History."
    )

    # --------------------------------
    # DUPLIKATE AUS API ENTFERNEN
    # --------------------------------

    unique_clips = {}

    for clip in clips:

        clip_id = clip.get(
            "id"
        )

        if not clip_id:
            continue

        unique_clips[
            clip_id
        ] = clip

    clips = list(
        unique_clips.values()
    )

    print(
        f"{len(clips)} eindeutige "
        f"Twitch-Clips."
    )

    # --------------------------------
    # NACH VIEWS SORTIEREN
    # --------------------------------

    clips.sort(
        key=lambda clip: int(
            clip.get(
                "view_count",
                0
            )
        ),
        reverse=True,
    )

    candidates = []

    skipped_used = 0
    skipped_short = 0
    skipped_invalid = 0

    # --------------------------------
    # KANDIDATEN AUFBAUEN
    # --------------------------------

    for clip in clips:

        clip_id = clip.get(
            "id"
        )

        if not clip_id:

            skipped_invalid += 1

            continue

        # Bereits final verwendete
        # Clips niemals wieder nehmen.
        if clip_id in used:

            skipped_used += 1

            continue

        try:

            duration = float(
                clip.get(
                    "duration",
                    0
                )
            )

        except (
            TypeError,
            ValueError,
        ):

            skipped_invalid += 1

            continue

        # Zu kurze Clips bringen für
        # TikTok meistens nichts.
        if duration < 8:

            skipped_short += 1

            continue

        url = clip.get(
            "url"
        )

        if not url:

            skipped_invalid += 1

            continue

        title = str(
            clip.get(
                "title",
                ""
            )
        ).strip()

        candidate = {

            "id":
                clip_id,

            "title":
                title,

            "url":
                url,

            "view_count":
                int(
                    clip.get(
                        "view_count",
                        0
                    )
                ),

            "creator_name":
                clip.get(
                    "creator_name",
                    ""
                ),

            "created_at":
                clip.get(
                    "created_at",
                    ""
                ),

            "duration":
                duration,

            "broadcaster_name":
                clip.get(
                    "broadcaster_name",
                    BROADCASTER_LOGIN
                ),

            "source":
                "twitch",

            "selected_by":
                "candidate_pool",
        }

        candidates.append(
            candidate
        )

        if (
            len(candidates)
            >= KANDIDATEN_ANZAHL
        ):

            break

    # --------------------------------
    # SPEICHERN
    # --------------------------------

    save_candidates(
        candidates
    )

    print("")

    print(
        "================================"
    )

    print(
        "KANDIDATEN-STATISTIK"
    )

    print(
        "================================"
    )

    print(
        f"Bereits benutzt: "
        f"{skipped_used}"
    )

    print(
        f"Zu kurz: "
        f"{skipped_short}"
    )

    print(
        f"Ungültig: "
        f"{skipped_invalid}"
    )

    print(
        f"Frische Kandidaten: "
        f"{len(candidates)}"
    )

    print("")

    if not candidates:

        raise RuntimeError(
            "Keine neuen Twitch-Clips "
            "verfügbar."
        )

    print(
        "================================"
    )

    print(
        f"{len(candidates)} KANDIDATEN "
        f"FÜR QUALITY CONTROL"
    )

    print(
        "================================"
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

    if len(candidates) < 20:

        print(
            "WARNUNG: Der Pool enthält "
            "weniger als 20 frische Clips."
        )

    if len(candidates) < 5:

        print(
            "WARNUNG: Es stehen weniger "
            "als 5 frische Clips zur "
            "Verfügung."
        )

    print("")

    print(
        "Kandidaten wurden gespeichert."
    )

    print(
        "Die Quality-Control entscheidet "
        "jetzt über die finalen 5."
    )

    print(
        "Noch kein Kandidat wurde als "
        "benutzt markiert."
    )


if __name__ == "__main__":
    main()