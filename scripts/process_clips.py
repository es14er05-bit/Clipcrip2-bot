import os
import glob
import subprocess
import sys

INPUT_DIR = "downloaded_clips"
OUTPUT_DIR = "tiktok_ready"

WIDTH = 1080
HEIGHT = 1920


def run(command):
    print("RUN:", " ".join(command))
    result = subprocess.run(command)

    if result.returncode != 0:
        raise RuntimeError(
            f"Befehl fehlgeschlagen: {' '.join(command)}"
        )


def find_video():
    videos = []

    for extension in ("mp4", "webm", "mkv", "mov"):
        videos.extend(
            glob.glob(
                os.path.join(INPUT_DIR, f"*.{extension}")
            )
        )

    if not videos:
        raise FileNotFoundError(
            "Keine Videos im Ordner downloaded_clips gefunden."
        )

    return videos[0]


def create_subtitles(video, subtitle_file):
    print("Erstelle automatische Untertitel...")

    run([
        sys.executable,
        "-m",
        "whisper",
        video,
        "--model",
        "small",
        "--output_format",
        "srt",
        "--output_dir",
        os.path.dirname(subtitle_file),
    ])


def create_tiktok_video(video, subtitle_file, output):
    print("Erstelle 9:16 TikTok-Version...")

    filter_complex = (
        "[0:v]"
        "scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,"
        "setsar=1"
        "[v]"
    )

    run([
        "ffmpeg",
        "-y",
        "-i",
        video,
        "-vf",
        f"{filter_complex};subtitles={subtitle_file}:"
        "force_style='FontSize=18,"
        "Bold=1,"
        "Alignment=2,"
        "MarginV=180'",
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
        output,
    ])


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    video = find_video()

    base_name = os.path.splitext(
        os.path.basename(video)
    )[0]

    subtitle_file = os.path.join(
        OUTPUT_DIR,
        f"{base_name}.srt"
    )

    output = os.path.join(
        OUTPUT_DIR,
        f"{base_name}_tiktok.mp4"
    )

    print("================================")
    print("ClipCrip2 Video Processing")
    print("================================")
    print(f"Eingabe: {video}")
    print(f"Ausgabe: {output}")

    create_subtitles(video, subtitle_file)

    # Whisper erzeugt die SRT-Datei normalerweise
    # mit demselben Namen wie das Eingabevideo.
    generated_srt = os.path.join(
        OUTPUT_DIR,
        f"{base_name}.srt"
    )

    if not os.path.exists(generated_srt):
        raise FileNotFoundError(
            f"Untertitel wurden nicht gefunden: {generated_srt}"
        )

    create_tiktok_video(
        video,
        generated_srt,
        output
    )

    print("")
    print("================================")
    print("FERTIG!")
    print(f"TikTok-Video: {output}")
    print("================================")


if __name__ == "__main__":
    main()
