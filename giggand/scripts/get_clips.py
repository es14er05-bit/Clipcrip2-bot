from pathlib import Path
import datetime
import importlib.util

import requests


REPO_ROOT = Path(__file__).resolve().parents[2]
GIGGAND_ROOT = REPO_ROOT / "giggand"
CORE_FILE = REPO_ROOT / "scripts" / "get_clips.py"


GIGGAND_LOGIN = "giggand"
GIGGAND_SEARCH_DAYS = 365
MAX_PAGES = 10


def load_core():
    spec = importlib.util.spec_from_file_location(
        "clipcrip2_core_get_clips",
        CORE_FILE,
    )

    if spec is None or spec.loader is None:
        raise RuntimeError(
            f"Konnte Core-Datei nicht laden: {CORE_FILE}"
        )

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    return module


def get_giggand_clips(
    core,
    token,
    broadcaster_id,
):
    headers = {
        "Client-Id": core.CLIENT_ID,
        "Authorization": f"Bearer {token}",
    }

    now = datetime.datetime.now(
        datetime.timezone.utc
    )

    since = (
        now
        - datetime.timedelta(
            days=GIGGAND_SEARCH_DAYS
        )
    )

    started_at = (
        since
        .isoformat()
        .replace("+00:00", "Z")
    )

    ended_at = (
        now
        .isoformat()
        .replace("+00:00", "Z")
    )

    clips = []
    cursor = None
    page = 1

    print("")
    print("Giggand Twitch-Abfrage:")
    print(
        f"Zeitraum: letzte "
        f"{GIGGAND_SEARCH_DAYS} Tage"
    )
    print(f"started_at: {started_at}")
    print(f"ended_at:   {ended_at}")
    print("")

    while True:
        params = {
            "broadcaster_id": broadcaster_id,
            "started_at": started_at,
            "ended_at": ended_at,
            "first": 100,
        }

        if cursor:
            params["after"] = cursor

        print(
            f"Giggand Twitch-Seite "
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

        clips.extend(page_clips)

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

        if page >= MAX_PAGES:
            print(
                "Maximale Anzahl von "
                f"{MAX_PAGES} Seiten erreicht."
            )
            break

        page += 1

    print("")
    print(
        f"{len(clips)} Giggand-Clips "
        "im 365-Tage-Zeitraum gefunden."
    )

    if clips:
        return clips

    print("")
    print(
        "WARNUNG: Zeitfilter lieferte "
        "0 Clips."
    )
    print(
        "Starte Twitch-Fallback ohne "
        "Datumsfilter..."
    )

    clips = []
    cursor = None
    page = 1

    while True:
        params = {
            "broadcaster_id": broadcaster_id,
            "first": 100,
        }

        if cursor:
            params["after"] = cursor

        print(
            f"Fallback Twitch-Seite "
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

        clips.extend(page_clips)

        print(
            f"{len(page_clips)} Clips "
            f"auf Fallback-Seite {page}."
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

        if page >= MAX_PAGES:
            print(
                "Fallback-Limit von "
                f"{MAX_PAGES} Seiten erreicht."
            )
            break

        page += 1

    print("")
    print(
        f"{len(clips)} Giggand-Clips "
        "über Fallback gefunden."
    )

    return clips


def main():
    GIGGAND_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    core = load_core()

    core.BROADCASTER_LOGIN = (
        GIGGAND_LOGIN
    )

    core.USED_FILE = str(
        GIGGAND_ROOT
        / "used_clips.json"
    )

    core.OUTPUT_FILE = str(
        GIGGAND_ROOT
        / "clips_today.json"
    )

    core.SUCHZEITRAUM_TAGE = (
        GIGGAND_SEARCH_DAYS
    )

    original_get_all_clips = (
        core.get_all_clips
    )

    def giggand_get_all_clips(
        token,
        broadcaster_id,
    ):
        return get_giggand_clips(
            core,
            token,
            broadcaster_id,
        )

    core.get_all_clips = (
        giggand_get_all_clips
    )

    print("")
    print(
        "================================"
    )
    print(
        "CLIPCRIP5 – GIGGAND"
    )
    print(
        "================================"
    )
    print("Twitch: giggand")
    print("TikTok: @clipcrip5")
    print(
        "Suchzeitraum: "
        f"{GIGGAND_SEARCH_DAYS} Tage"
    )
    print(
        "Eigene Used-History: "
        + core.USED_FILE
    )
    print(
        "Eigene Kandidaten-Datei: "
        + core.OUTPUT_FILE
    )
    print(
        "Twitch-Fix: started_at "
        "+ ended_at aktiviert"
    )
    print(
        "Fallback ohne Datumsfilter: "
        "aktiviert"
    )
    print("")

    try:
        core.main()

    finally:
        core.get_all_clips = (
            original_get_all_clips
        )


if __name__ == "__main__":
    main()