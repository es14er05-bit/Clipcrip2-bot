import json
import os
import subprocess
import sys

INPUT_FILE = "clips_today.json"
OUTPUT_DIR = "downloaded_clips"


def download_clip(url, output):

    print(
        f"Downloading: {url}"
    )

    result = subprocess.run([
        sys.executable,
        "-m",
        "yt_dlp",
        "--no-playlist",
        "--merge-output-format",
        "mp4",
        "-o",
        output,
        url
    ])

    if result.returncode != 0:

        raise RuntimeError(
            f"Download fehlgeschlagen: {url}"
        )


def main():

    os.makedirs(
        OUTPUT_DIR,
        exist_ok=True
    )

    if not os.path.exists(
        INPUT_FILE
    ):

        raise FileNotFoundError(
            f"{INPUT_FILE} wurde nicht gefunden."
        )

    with open(
        INPUT_FILE,
        "r",
        encoding="utf-8"
    ) as file:

        clips = json.load(file)

    if not clips:

        raise RuntimeError(
            "clips_today.json ist leer."
        )

    print(
        f"{len(clips)} Kandidaten zum "
        "Herunterladen gefunden."
    )

    # Alte Dateien entfernen
    for filename in os.listdir(
        OUTPUT_DIR
    ):

        path = os.path.join(
            OUTPUT_DIR,
            filename
        )

        if os.path.isfile(path):
            os.remove(path)

    for number, clip in enumerate(
        clips,
        start=1
    ):

        clip_url = clip["url"]

        output = os.path.join(
            OUTPUT_DIR,
            f"candidate_{number:02d}.%(ext)s"
        )

        print("")
        print(
            f"Kandidat "
            f"{number}/{len(clips)}"
        )

        print(
            clip.get(
                "title",
                ""
            )
        )

        download_clip(
            clip_url,
            output
        )

    print("")
    print(
        "================================"
    )
    print(
        "ALLE KANDIDATEN HERUNTERGELADEN"
    )
    print(
        "================================"
    )


if __name__ == "__main__":
    main()