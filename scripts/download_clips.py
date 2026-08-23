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
        raise RuntimeError(f"Download fehlgeschlagen: {url}")

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        clips = json.load(f)

    if not clips:
        print("Keine neuen Clips gefunden.")
        return

    clips = clips[:5]

    for i, clip in enumerate(clips, start=1):
        output = os.path.join(
            OUTPUT_DIR,
            f"clip_{i}.%(ext)s"
        )

        download_clip(clip["url"], output)

    print(f"{len(clips)} Clips heruntergeladen.")

if __name__ == "__main__":
    main()
