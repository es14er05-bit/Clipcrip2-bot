import os
import glob
import subprocess
import sys

INPUT_DIR = "downloaded_clips"
OUTPUT_DIR = "tiktok_ready"


def run(command):
    print("RUN:", " ".join(command))

    result = subprocess.run(command)

    if result.returncode != 0:
        raise RuntimeError(
            "Befehl fehlgeschlagen: "
            + " ".join(command)
        )


def find_videos():
    videos = []

    for extension in ("mp4", "webm", "mkv", "mov"):
        videos.extend(
            glob.glob(
                os.path.join(
                    INPUT_DIR,
                    f"*.{extension}"
                )
            )
        )

    return sorted(videos)


def create_subtitles(video):
    print(f"Erstelle Untertitel für: {video}")

    run([
        sys.executable,
        "-m",
        "whisper",
        video,
        "--model",
        "small",
        "--language",
        "German",
        "--output_format",
        "srt",
        "--output_dir",
        OUTPUT_DIR,
    ])


def process_video(video, number):
    filename = os.path.splitext(
        os.path.basename(video)
    )[0]

    subtitle_file = os.path.join(
        OUTPUT_DIR,
        f"{filename}.srt"
    )

    output_file = os.path.join(
        OUTPUT_DIR,
        f"{number:02d}_jussef_tiktok.mp4"
    )

    # Untertitel erstellen
    create_subtitles(video)

    if not os.path.exists(subtitle_file):
        raise FileNotFoundError(
            f"SRT-Datei nicht gefunden: {subtitle_file}"
        )

    print(f"Bearbeite Video: {video}")

    # 16:9 -> 9:16
    # Das Bild wird mittig gecroppt.
    video_filter = (
        "scale=1080:1920:"
        "force_original_aspect_ratio=increase,"
        "crop=1080:1920,"
        "setsar=1,"
        "subtitles="
        + subtitle_file
        + ":force_style='"
        "FontSize=18,"
        "Bold=1,"
        "PrimaryColour=&HFFFFFF,"
        "OutlineColour=&H000000,"
        "Outline=3,"
        "Alignment=2,"
        "MarginV=180"
        "'"
    )

    run([
        "ffmpeg",
        "-y",
        "-i",
        video,
        "-vf",
        video_filter,
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "20",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-movflags",
        "+faststart",
        output_file,
    ])

    print(f"FERTIG: {output_file}")


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    videos = find_videos()

    if not videos:
        raise FileNotFoundError(
            "Keine Videos in downloaded_clips gefunden."
        )

    print("================================")
    print("ClipCrip2 Video Processing")
    print("================================")
    print(f"{len(videos)} Videos gefunden.")

    for number, video in enumerate(videos, start=1):
        process_video(video, number)

    print("")
    print("================================")
    print("ALLE VIDEOS FERTIG!")
    print("================================")


if __name__ == "__main__":
    main()
