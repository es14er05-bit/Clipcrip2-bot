import json
import os
import subprocess
import sys
import glob

INPUT_FILE = "clips_today.json"
OUTPUT_DIR = "downloaded_clips"


def download_clip(url, output_template):
    print(f"Downloading: {url}")

    result = subprocess.run([
        sys.executable,
        "-m",
        "yt_dlp",
        "--no-playlist",
        "--force-overwrites",
        "--merge-output-format",
        "mp4",
        "-o",
        output_template,
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

    # Alte Dateien entfernen
    for file in glob.glob(
        os.path.join(OUTPUT_DIR, "*")
    ):
        try:
            os.remove(file)
        except Exception:
            pass

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
            "clips_today.json ist leer. "
            "Es wurden keine Clips ausgewählt."
        )

    print(
        f"{len(clips)} Clips zum "
        f"Herunterladen gefunden."
    )

    successful = 0

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
            f"\n================================"
        )
        print(
            f"Clip {number}/{len(clips)}"
        )
        print(
            f"Titel: {clip.get('title', '')}"
        )
        print(
            f"URL: {clip_url}"
        )
        print(
            "================================"
        )

        download_clip(
            clip_url,
            output
        )

        # Prüfen, ob tatsächlich eine Datei entstanden ist
        possible_files = glob.glob(
            os.path.join(
                OUTPUT_DIR,
                f"clip_{number}.*"
            )
        )

        video_files = [
            f for f in possible_files
            if not f.endswith(".part")
            and not f.endswith(".ytdl")
        ]

        if not video_files:
            raise RuntimeError(
                f"yt-dlp meldet keinen Fehler, "
                f"aber Clip {number} wurde nicht "
                f"in {OUTPUT_DIR} gespeichert."
            )

        actual_file = video_files[0]

        size = os.path.getsize(
            actual_file
        )

        if size < 10000:
            raise RuntimeError(
                f"Clip {number} ist nur "
                f"{size} Bytes groß."
            )

        # Falls yt-dlp eine andere Endung erzeugt hat,
        # auf .mp4 umbenennen.
        final_file = os.path.join(
            OUTPUT_DIR,
            f"clip_{number}.mp4"
        )

        if actual_file != final_file:
            os.replace(
                actual_file,
                final_file
            )

        successful += 1

        print(
            f"ERFOLG: {final_file} "
            f"({size / 1024 / 1024:.2f} MB)"
        )

    print(
        f"\n{successful}/{len(clips)} "
        "Clips erfolgreich heruntergeladen."
    )

    # Letzte Sicherheitsprüfung
    downloaded = glob.glob(
        os.path.join(
            OUTPUT_DIR,
            "*.mp4"
        )
    )

    if len(downloaded) == 0:
        raise RuntimeError(
            "downloaded_clips enthält keine MP4-Dateien."
        )

    print(
        "\nDateien in downloaded_clips:"
    )

    for file in downloaded:
        print(
            f" - {file}"
        )


if __name__ == "__main__":
    main()
