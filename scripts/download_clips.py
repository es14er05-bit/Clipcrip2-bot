import json
import os
import shutil
import subprocess
import sys

INPUT_FILE = "clips_today.json"
OUTPUT_DIR = "downloaded_clips"


def clean_directory(directory):
    os.makedirs(
        directory,
        exist_ok=True
    )

    for filename in os.listdir(directory):

        path = os.path.join(
            directory,
            filename
        )

        if os.path.isfile(path):
            os.remove(path)

        elif os.path.isdir(path):
            shutil.rmtree(path)


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


def find_downloaded_file(base_name):

    extensions = (
        ".mp4",
        ".webm",
        ".mkv",
        ".mov"
    )

    for extension in extensions:

        path = os.path.join(
            OUTPUT_DIR,
            base_name + extension
        )

        if os.path.exists(path):
            return path

    return None


def main():

    print("================================")
    print("ClipCrip2 – Downloads")
    print("================================")

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

    # Ganz wichtig:
    # Alte Videos aus dem vorherigen Workflow löschen.
    clean_directory(
        OUTPUT_DIR
    )

    print(
        f"{len(clips)} Kandidaten werden heruntergeladen."
    )

    successful = 0

    for number, clip in enumerate(
        clips,
        start=1
    ):

        url = clip.get("url")

        if not url:
            print(
                f"Clip {number}: keine URL – übersprungen."
            )
            continue

        output = os.path.join(
            OUTPUT_DIR,
            f"clip_{number}.%(ext)s"
        )

        print("")
        print(
            f"CLIP {number}/{len(clips)}"
        )
        print(
            clip.get(
                "title",
                ""
            )
        )

        try:

            download_clip(
                url,
                output
            )

            downloaded = find_downloaded_file(
                f"clip_{number}"
            )

            if downloaded:

                successful += 1

                print(
                    f"Download OK: {downloaded}"
                )

            else:

                print(
                    "Download scheinbar erfolgreich, "
                    "aber Datei wurde nicht gefunden."
                )

        except Exception as error:

            print(
                f"Download fehlgeschlagen: {error}"
            )

    print("")
    print("================================")
    print(
        f"Erfolgreiche Downloads: {successful}"
    )
    print("================================")

    if successful == 0:

        raise RuntimeError(
            "Kein Clip konnte heruntergeladen werden."
        )


if __name__ == "__main__":
    main()
