import json
import os
import subprocess
import sys

INPUT_FILE = "clips_today.json"
OUTPUT_DIR = "downloaded_clips"

TEST_CLIP_URL = "https://www.twitch.tv/jussef/clip/ObesePlainCaribouDatBoi-hsk3_1eft3oXVzRB"


def download_clip(url, output):
    print(f"Downloading: {url}")

    command = [
        sys.executable,
        "-m",
        "yt_dlp",
        "--no-playlist",
        "-o",
        output,
        url,
    ]

    result = subprocess.run(command)

    if result.returncode != 0:
        raise RuntimeError(f"Download fehlgeschlagen: {url}")


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Zuerst testen wir EINEN bekannten öffentlichen Jussef-Clip.
    output = os.path.join(OUTPUT_DIR, "test_jussef_clip.mp4")

    download_clip(TEST_CLIP_URL, output)

    print(f"Fertig: {output}")


if __name__ == "__main__":
    main()
