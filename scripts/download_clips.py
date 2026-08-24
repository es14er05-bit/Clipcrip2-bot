import json
import os
import subprocess
import sys

INPUT_FILE = "clips_today.json"
OUTPUT_DIR = "downloaded_clips"


def download_clip(url, output):
    print(f"Downloading: {url}")

    result = subprocess.run([
        sys.executable,
        "-m",
        "yt_dlp",
        "--no-playlist",
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
        print(
            "Keine Clips zum Herunterladen gefunden."
        )
        return

    print(
        f"{len(clips)} Clips zum "
        f"Herunterladen gefunden."
    )

    for number, clip in enumerate(
        clips,
        start=1
    ):

        clip_url = clip["url"]

        output = os.path.join(
            OUTPUT_DIR,
            f"clip_{number}.%(ext)s"
        )

        print(
            f"\nClip {number}/{len(clips)}: "
            f"{clip.get('title', '')}"
        )

        download_clip(
            clip_url,
            output
        )

    print(
        "\nAlle Clips wurden heruntergeladen."
    )


if __name__ == "__main__":
    main()
