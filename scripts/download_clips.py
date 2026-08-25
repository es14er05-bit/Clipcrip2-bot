import json
import os
import glob
import subprocess
import sys

INPUT_FILE = "clips_today.json"
OUTPUT_DIR = "downloaded_clips"


def clean_output_folder():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    for file in glob.glob(
        os.path.join(OUTPUT_DIR, "*")
    ):
        try:
            os.remove(file)
        except Exception:
            pass


def download_clip(url, output):
    print(f"Downloading: {url}")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "yt_dlp",
            "--no-playlist",
            "--merge-output-format",
            "mp4",
            "-o",
            output,
            url,
        ],
        capture_output=False,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Download fehlgeschlagen: {url}"
        )


def main():

    print("================================")
    print("ClipCrip2 – Downloads")
    print("================================")

    clean_output_folder()

    if not os.path.exists(INPUT_FILE):
        raise FileNotFoundError(
            f"{INPUT_FILE} wurde nicht gefunden."
        )

    with open(
        INPUT_FILE,
        "r",
        encoding="utf-8",
    ) as file:
        clips = json.load(file)

    if not clips:
        raise RuntimeError(
            "clips_today.json ist leer. "
            "Keine Clips ausgewählt."
        )

    print(
        f"{len(clips)} Clips werden heruntergeladen."
    )

    for number, clip in enumerate(
        clips,
        start=1,
    ):

        url = clip.get("url")

        if not url:
            print(
                f"Clip {number} hat keine URL – übersprungen."
            )
            continue

        output = os.path.join(
            OUTPUT_DIR,
            f"clip_{number}.%(ext)s",
        )

        print(
            f"\nClip {number}/{len(clips)}"
        )

        download_clip(
            url,
            output,
        )

    downloaded = []

    for extension in (
        "mp4",
        "webm",
        "mkv",
        "mov",
    ):
        downloaded.extend(
            glob.glob(
                os.path.join(
                    OUTPUT_DIR,
                    f"*.{extension}",
                )
            )
        )

    if not downloaded:
        raise RuntimeError(
            "Es wurde kein Video heruntergeladen."
        )

    print("")
    print(
        f"{len(downloaded)} Videos erfolgreich heruntergeladen."
    )


if __name__ == "__main__":
    main()
