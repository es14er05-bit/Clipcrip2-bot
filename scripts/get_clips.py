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

# Wenn aus demselben VOD bereits eine Stelle benutzt wurde,
# wird dieser Bereich davor und danach ebenfalls gesperrt.
#
# Beispiel:
# alter Clip bei Sekunde 5000
# -> neue Clips zwischen 4940 und 5060 werden blockiert.
VOD_DUPLICATE_WINDOW_SECONDS = 60

USED_FILE = "used_clips.json"
OUTPUT_FILE = "clips_today.json"


# =========================================================
# TWITCH TOKEN
# =========================================================

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

    return response.json()[
        "access_token"
    ]


# =========================================================
# BROADCASTER
# =========================================================

def get_broadcaster_id(token):

    headers = {
        "Client-Id": CLIENT_ID,
        "Authorization":
            f"Bearer {token}",
    }

    response = requests.get(
        "https://api.twitch.tv/helix/users",
        params={
            "login":
                BROADCASTER_LOGIN
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


# =========================================================
# ALLE TWITCH CLIPS
# =========================================================

def get_all_clips(
    token,
    broadcaster_id
):

    headers = {
        "Client-Id": CLIENT_ID,
        "Authorization":
            f"Bearer {token}",
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

        # Sicherheitslimit:
        # maximal 2000 Twitch-Clips.
        if page > 20:

            print(
                "Sicherheitslimit von "
                "2000 Twitch-Clips erreicht."
            )

            break

    return clips


# =========================================================
# USED HISTORY
# =========================================================

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
            str(item)
            for item in data
        )

    except (
        json.JSONDecodeError,
        OSError,
        TypeError,
    ):

        return set()


# =========================================================
# VOD POSITION
# =========================================================

def get_vod_position(clip):

    """
    Liefert:
    (video_id, vod_offset)

    video_id:
        Twitch VOD / Stream-ID.

    vod_offset:
        Position des Clips innerhalb des VODs
        in Sekunden.

    Falls Twitch keine brauchbaren Daten liefert,
    wird None zurückgegeben.
    """

    video_id = str(
        clip.get(
            "video_id",
            ""
        )
    ).strip()

    raw_offset = clip.get(
        "vod_offset"
    )

    if not video_id:
        return None

    if raw_offset is None:
        return None

    try:

        vod_offset = int(
            raw_offset
        )

    except (
        TypeError,
        ValueError,
    ):
        return None

    if vod_offset < 0:
        return None

    return (
        video_id,
        vod_offset
    )


# =========================================================
# BEREITS BENUTZTE VOD-STELLEN AUFBAUEN
# =========================================================

def build_used_vod_positions(
    all_clips,
    used_ids
):

    """
    Sehr wichtig:

    used_clips.json enthält alte Twitch-Clip-IDs.

    Da die aktuelle Twitch-Abfrage auch alte Clips liefert,
    können wir anhand dieser alten IDs herausfinden,
    aus welchem VOD und von welcher Stelle sie kamen.

    Dadurch können wir auch alte Wiederholungen blockieren,
    obwohl clip_history.json damals noch keine
    video_id/vod_offset-Daten gespeichert hat.
    """

    positions = {}

    matched_used_ids = 0

    for clip in all_clips:

        clip_id = str(
            clip.get(
                "id",
                ""
            )
        )

        if (
            not clip_id
            or clip_id not in used_ids
        ):
            continue

        position = get_vod_position(
            clip
        )

        if position is None:
            continue

        video_id, vod_offset = position

        positions.setdefault(
            video_id,
            []
        ).append(
            vod_offset
        )

        matched_used_ids += 1

    # Doppelte Offsets entfernen.
    for video_id in positions:

        positions[
            video_id
        ] = sorted(
            set(
                positions[
                    video_id
                ]
            )
        )

    total_positions = sum(
        len(values)
        for values in positions.values()
    )

    print("")
    print(
        "================================"
    )

    print(
        "VOD-DUPLIKAT-HISTORY"
    )

    print(
        "================================"
    )

    print(
        f"{matched_used_ids} alte Used-IDs "
        "konnten einem Twitch-VOD "
        "zugeordnet werden."
    )

    print(
        f"{total_positions} bereits "
        "verwendete VOD-Stellen bekannt."
    )

    print(
        f"Sperrbereich: +/- "
        f"{VOD_DUPLICATE_WINDOW_SECONDS} Sekunden."
    )

    return positions


# =========================================================
# VOD DUPLICATE CHECK
# =========================================================

def is_used_vod_position(
    clip,
    used_vod_positions
):

    position = get_vod_position(
        clip
    )

    if position is None:

        # Wenn Twitch keine VOD-Daten liefert,
        # greifen weiterhin Clip-ID und später
        # visuelle Quality-Control.
        return False

    video_id, vod_offset = position

    old_offsets = (
        used_vod_positions.get(
            video_id,
            []
        )
    )

    for old_offset in old_offsets:

        difference = abs(
            vod_offset
            - old_offset
        )

        if (
            difference
            <= VOD_DUPLICATE_WINDOW_SECONDS
        ):

            print(
                "VOD-DUPLIKAT BLOCKIERT | "
                f"VOD {video_id} | "
                f"neu {vod_offset}s | "
                f"alt {old_offset}s | "
                f"Abstand {difference}s"
            )

            return True

    return False


# =========================================================
# OUTPUT
# =========================================================

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


# =========================================================
# MAIN
# =========================================================

def main():

    print(
        "================================"
    )

    print(
        "CLIPCRIP2 – CANDIDATEN SAMMLER V2"
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

    # =====================================================
    # DUPLIKATE AUS API ENTFERNEN
    # =====================================================

    unique_clips = {}

    for clip in clips:

        clip_id = clip.get(
            "id"
        )

        if not clip_id:
            continue

        unique_clips[
            str(clip_id)
        ] = clip

    clips = list(
        unique_clips.values()
    )

    print(
        f"{len(clips)} eindeutige "
        f"Twitch-Clips."
    )

    # =====================================================
    # ALTE VOD-STELLEN REKONSTRUIEREN
    # =====================================================

    used_vod_positions = (
        build_used_vod_positions(
            clips,
            used
        )
    )

    # =====================================================
    # NACH VIEWS SORTIEREN
    # =====================================================

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
    skipped_vod_duplicate = 0
    skipped_short = 0
    skipped_invalid = 0

    # =====================================================
    # KANDIDATEN AUFBAUEN
    # =====================================================

    for clip in clips:

        clip_id = str(
            clip.get(
                "id",
                ""
            )
        )

        if not clip_id:

            skipped_invalid += 1
            continue

        # -------------------------------------------------
        # EXAKTE TWITCH CLIP-ID BEREITS BENUTZT
        # -------------------------------------------------

        if clip_id in used:

            skipped_used += 1
            continue

        # -------------------------------------------------
        # GLEICHE STELLE AUS DEMSELBEN VOD
        # -------------------------------------------------

        if is_used_vod_position(
            clip,
            used_vod_positions
        ):

            skipped_vod_duplicate += 1
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

        position = get_vod_position(
            clip
        )

        video_id = ""
        vod_offset = None

        if position is not None:

            video_id, vod_offset = (
                position
            )

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

            # ---------------------------------------------
            # NEU:
            # Stream/VOD + Position für permanente
            # Wiederholungssperre.
            # ---------------------------------------------

            "video_id":
                video_id,

            "vod_offset":
                vod_offset,

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

    # =====================================================
    # SPEICHERN
    # =====================================================

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
        f"Exakte Clip-ID benutzt: "
        f"{skipped_used}"
    )

    print(
        f"Gleiche VOD-Stelle blockiert: "
        f"{skipped_vod_duplicate}"
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

        vod_text = ""

        if (
            clip.get("video_id")
            and clip.get("vod_offset")
            is not None
        ):

            vod_text = (
                f" | VOD "
                f"{clip['video_id']} "
                f"@ {clip['vod_offset']}s"
            )

        print(
            f"{number:02d}. "
            f"{clip['title']} | "
            f"{clip['duration']:.1f}s | "
            f"{clip['view_count']} Views"
            f"{vod_text}"
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
        "Gleicher Stream bleibt erlaubt."
    )

    print(
        "Bereits verwendete Stellen "
        "desselben Streams sind gesperrt."
    )

    print(
        "Die Quality-Control entscheidet "
        "jetzt über die finalen 5."
    )


if __name__ == "__main__":
    main()