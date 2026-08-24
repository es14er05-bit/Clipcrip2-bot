import json
import os
import requests

INPUT_FILE = "clips_today.json"
OUTPUT_DIR = "downloaded_clips"


def download_clip(url, output):
    print(f"Downloading: {url}")

    response = requests.get(
        url,
        stream=True,
        timeout=120
    )

    response.raise_for_status()

    with open(output, "wb") as file:
        for chunk in response.iter_content(
            chunk_size=1024 * 1024
        ):
            if chunk:
                file.write(chunk)


def main():
    os.makedirs(
        OUTPUT_DIR,
        exist_ok=True
    )

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
            "Keine Clips zum Herunterladen gefunden."
        )

    print(
        f"{len(clips)} Clips zum "
        f"Herunterladen gefunden."
    )

    downloaded = 0

    for number, clip in enumerate(
        clips,
        start=1
    ):
        download_url = clip.get(
            "download_url"
        )

        if not download_url:
            print(
                f"Clip {number}: "
                "Keine Download-URL vorhanden."
            )
            continue

        output = os.path.join(
            OUTPUT_DIR,
            f"clip_{number}.mp4"
        )

        print(
            f"\nClip {number}/{len(clips)}"
        )

        print(
            f"Titel: "
            f"{clip.get('title', '')}"
        )

        download_clip(
            download_url,
            output
        )

        if os.path.exists(output):
            size = os.path.getsize(
                output
            )

            if size > 10000:
                downloaded += 1

                print(
                    f"OK: {output} "
                    f"({size / 1024 / 1024:.1f} MB)"
                )
            else:
                os.remove(output)

                print(
                    "Download war zu klein "
                    "und wurde verworfen."
                )

    print("")
    print(
        f"{downloaded}/{len(clips)} "
        "Clips erfolgreich heruntergeladen."
    )

    if downloaded == 0:
        raise RuntimeError(
            "Kein einziger Clip konnte "
            "heruntergeladen werden."
        )


if __name__ == "__main__":
    main()
