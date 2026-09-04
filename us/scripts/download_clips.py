"""
ClipCrip3 US Downloader

Twitch:
normaler Clip-Download

Kick:
normaler Clip-Download

Speed YouTube:
nur die ausgewählte Most-Replayed
Stelle aus dem langen Stream herunterladen
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = (
    Path(__file__)
    .resolve()
    .parents[2]
)

US_ROOT = (
    REPO_ROOT
    / "us"
)

INPUT_FILE = (
    US_ROOT
    / "clips_today.json"
)

OUTPUT_DIR = (
    US_ROOT
    / "downloaded_clips"
)

MIN_SUCCESSFUL_DOWNLOADS = 5


def load_candidates() -> list[
    dict[str, Any]
]:

    if not INPUT_FILE.exists():

        raise FileNotFoundError(
            f"{INPUT_FILE} "
            "wurde nicht gefunden."
        )


    data = json.loads(
        INPUT_FILE.read_text(
            encoding="utf-8"
        )
    )


    if not isinstance(
        data,
        list,
    ):

        raise RuntimeError(
            f"{INPUT_FILE} "
            "ist keine JSON-Liste."
        )


    return [
        item
        for item in data
        if isinstance(
            item,
            dict,
        )
    ]


def clean_output() -> None:

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )


    for item in (
        OUTPUT_DIR.iterdir()
    ):

        if (
            item.is_file()
            or item.is_symlink()
        ):

            item.unlink()


        elif item.is_dir():

            shutil.rmtree(
                item
            )


def download_candidate(
    candidate: dict[str, Any],
    number: int,
) -> bool:

    url = str(
        candidate.get(
            "url"
        )
        or ""
    ).strip()


    if not url:

        print(
            f"Clip {number}: "
            "keine URL."
        )

        return False


    output_template = str(
        OUTPUT_DIR
        / (
            f"clip_{number}."
            "%(ext)s"
        )
    )


    command = [

        sys.executable,

        "-m",

        "yt_dlp",

        "--no-playlist",

        "--retries",
        "3",

        "--fragment-retries",
        "3",

        "--concurrent-fragments",
        "4",

        "-f",
        (
            "bestvideo[height<=1080]"
            "+bestaudio/"
            "best[height<=1080]/"
            "best"
        ),

        "--merge-output-format",
        "mp4",

        "-o",
        output_template,
    ]


    # ========================================================
    # SPEED YOUTUBE SECTION
    # ========================================================

    section_start = (
        candidate.get(
            "section_start"
        )
    )


    section_end = (
        candidate.get(
            "section_end"
        )
    )


    if (
        candidate.get(
            "source"
        )
        == "youtube"
        and section_start
        is not None
        and section_end
        is not None
    ):

        try:

            start = float(
                section_start
            )

            end = float(
                section_end
            )

        except (
            TypeError,
            ValueError,
        ):

            print(
                f"Clip {number}: "
                "ungültige YouTube Section."
            )

            return False


        command += [

            "--download-sections",

            (
                "*"
                + f"{start:.3f}"
                + "-"
                + f"{end:.3f}"
            ),

            "--force-keyframes-at-cuts",
        ]


        print(
            "YOUTUBE SECTION | "
            f"{start:.1f}s "
            "-> "
            f"{end:.1f}s"
        )


    command.append(
        url
    )


    print(
        ""
    )

    print(
        "=" * 64
    )


    print(
        f"DOWNLOAD {number} | "
        f"{candidate.get('broadcaster_name', '')} | "
        f"{candidate.get('source', '')}"
    )


    print(
        candidate.get(
            "title",
            "",
        )
    )


    print(
        "=" * 64
    )


    result = subprocess.run(
        command,
        check=False,
    )


    if result.returncode != 0:

        print(
            f"DOWNLOAD FEHLER: "
            f"Kandidat {number}"
        )

        return False


    matches = list(
        OUTPUT_DIR.glob(
            f"clip_{number}.*"
        )
    )


    if not matches:

        print(
            "DOWNLOAD FEHLER: "
            f"keine Datei für "
            f"Kandidat {number}."
        )

        return False


    print(
        "DOWNLOAD OK:",
        matches[0].name,
    )


    return True


def main() -> None:

    clean_output()


    candidates = (
        load_candidates()
    )


    if len(
        candidates
    ) < MIN_SUCCESSFUL_DOWNLOADS:

        raise RuntimeError(
            f"Nur {len(candidates)} "
            "Kandidaten vorhanden."
        )


    successful = 0


    for (
        number,
        candidate,
    ) in enumerate(
        candidates,
        start=1,
    ):


        try:

            if download_candidate(
                candidate,
                number,
            ):

                successful += 1


        except Exception as error:

            print(
                "DOWNLOAD AUSNAHME "
                f"{number}: "
                f"{error}"
            )


    print(
        ""
    )


    print(
        f"{successful} von "
        f"{len(candidates)} "
        "US-Kandidaten erfolgreich "
        "heruntergeladen."
    )


    if (
        successful
        < MIN_SUCCESSFUL_DOWNLOADS
    ):

        raise RuntimeError(
            f"Nur {successful} "
            "Kandidaten konnten "
            "geladen werden. "
            f"Mindestens "
            f"{MIN_SUCCESSFUL_DOWNLOADS} "
            "benötigt."
        )


if __name__ == "__main__":

    main()
