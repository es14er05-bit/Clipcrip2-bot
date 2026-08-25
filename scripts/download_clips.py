import json
import os
import subprocess
import sys
import glob

INPUT_FILE = "clips_today.json"
OUTPUT_DIR = "downloaded_clips"


def download_clip(url, output):
    print(f"Downloading: {url}")

    result = subprocess.run([
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
        "bestvideo+bestaudio/best",
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

    # Alte Downloads löschen
    for file in glob.glob(
        os.path.join(OUTPUT_DIR, "*")
    ):
        if os.path.isfile(file):
            os.remove(file)

    if not os.path.exists(INPUT_FILE):
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
        f"{len(clips)} Kandidaten werden "
        "heruntergeladen."
    )

    successful = 0

    for number, clip in enumerate(
        clips,
        start=1
    ):

        clip_url = clip.get("url")

        if not clip_url:
            print(
                f"Clip {number} hat keine URL."
            )
            continue

        output = os.path.join(
            OUTPUT_DIR,
            f"clip_{number}.%(ext)s"
        )

        print("")
        print(
            f"===== DOWNLOAD {number}/"
            f"{len(clips)} ====="
        )

        try:

            download_clip(
                clip_url,
                output
            )

            successful += 1

        except Exception as error:

            print(
                f"DOWNLOAD FEHLER: {error}"
            )

    if successful == 0:

        raise RuntimeError(
            "Keiner der Clips konnte "
            "heruntergeladen werden."
        )

    print("")
    print(
        f"{successful} von "
        f"{len(clips)} Clips erfolgreich "
        "heruntergeladen."
    )


if __name__ == "__main__":
    main()