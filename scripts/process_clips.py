from __future__ import annotations

import json
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent

INPUT_DIR = REPO_ROOT / "selected_clips"
OUTPUT_DIR = REPO_ROOT / "tiktok_ready"
METADATA_FILE = REPO_ROOT / "clips_today.json"
SELECTION_REPORT_FILE = REPO_ROOT / "selection_report.json"

MIN_VIDEOS = 3
MAX_VIDEOS = 5

OUTPUT_PREFIX = "jussef_tiktok"
WATERMARK = "@clipcrip2"

STREAMER_NAME = "Jussef"

TARGET_WIDTH = 1080
TARGET_HEIGHT = 1920


def run(command: list[Any]) -> None:
    command = [
        str(item)
        for item in command
    ]

    print(
        "RUN:",
        " ".join(command),
    )

    result = subprocess.run(
        command,
        check=False,
    )

    if result.returncode != 0:
        raise RuntimeError(
            "Befehl fehlgeschlagen: "
            + " ".join(command)
        )


def load_json(
    path: str | Path,
    default: Any,
) -> Any:

    path = Path(path)

    if not path.exists():
        return default

    try:
        with path.open(
            "r",
            encoding="utf-8",
        ) as handle:
            return json.load(
                handle
            )
    except Exception:
        return default


def save_json(
    path: str | Path,
    data: Any,
) -> None:

    path = Path(path)

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with path.open(
        "w",
        encoding="utf-8",
    ) as handle:
        json.dump(
            data,
            handle,
            indent=2,
            ensure_ascii=False,
        )


def clean_output() -> Path:
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    for item in (
        OUTPUT_DIR.iterdir()
    ):
        if (
            item.is_file()
            or item.is_symlink()
        ):
            item.unlink()

        elif item.is_dir():
            shutil.rmtree(
                item
            )

    temp_dir = (
        OUTPUT_DIR
        / "_temp"
    )

    temp_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    return temp_dir


def video_number(
    path: Path,
) -> int:

    match = re.search(
        r"clip_(\d+)",
        path.stem,
        re.IGNORECASE,
    )

    if match:
        return int(
            match.group(1)
        )

    return 999999


def find_videos() -> list[Path]:
    extensions = {
        ".mp4",
        ".webm",
        ".mkv",
        ".mov",
        ".m4v",
    }

    if not INPUT_DIR.exists():
        return []

    videos = [
        path
        for path in INPUT_DIR.iterdir()
        if (
            path.is_file()
            and path.suffix.lower()
            in extensions
        )
    ]

    return sorted(
        videos,
        key=lambda path: (
            video_number(path),
            path.name.lower(),
        ),
    )


def clean_text(
    value: Any,
) -> str:

    text = re.sub(
        r"\s+",
        " ",
        str(
            value
            or ""
        ),
    ).strip()

    return (
        text.replace(
            "{",
            "(",
        )
        .replace(
            "}",
            ")",
        )
        .replace(
            "\\",
            "",
        )
    )


def escape_ass_text(
    value: Any,
) -> str:

    return clean_text(
        value
    ).replace(
        "\n",
        " ",
    )


def safe_float(
    value: Any,
    default: float = 0.0,
) -> float:

    try:
        return float(
            value
        )
    except Exception:
        return default


def ass_time(
    seconds: float,
) -> str:

    value = max(
        0.0,
        float(
            seconds
        ),
    )

    hours = int(
        value
        // 3600
    )

    minutes = int(
        (
            value
            % 3600
        )
        // 60
    )

    secs = int(
        value
        % 60
    )

    centiseconds = max(
        0,
        min(
            99,
            int(
                (
                    value
                    - int(value)
                )
                * 100
            ),
        ),
    )

    return (
        f"{hours}:"
        f"{minutes:02d}:"
        f"{secs:02d}."
        f"{centiseconds:02d}"
    )


def load_transcript(
    source: Path,
) -> dict[str, Any] | None:

    transcript_path = (
        source.with_suffix(
            ".transcript.json"
        )
    )

    transcript = load_json(
        transcript_path,
        None,
    )

    if isinstance(
        transcript,
        dict,
    ):
        return transcript

    return None


def extract_words(
    transcript: dict[str, Any],
    trim_start: float,
    trim_end: float,
) -> list[dict[str, Any]]:

    words: list[
        dict[str, Any]
    ] = []

    for segment in transcript.get(
        "segments",
        [],
    ):
        if not isinstance(
            segment,
            dict,
        ):
            continue

        for word in (
            segment.get(
                "words",
                [],
            )
            or []
        ):
            if not isinstance(
                word,
                dict,
            ):
                continue

            text = clean_text(
                word.get(
                    "word",
                    "",
                )
            )

            start = safe_float(
                word.get(
                    "start"
                ),
                0.0,
            )

            end = safe_float(
                word.get(
                    "end"
                ),
                start + 0.2,
            )

            if (
                not text
                or end <= trim_start
                or start >= trim_end
            ):
                continue

            local_start = max(
                0.0,
                start
                - trim_start,
            )

            local_end = (
                min(
                    trim_end,
                    end,
                )
                - trim_start
            )

            words.append(
                {
                    "text": text,
                    "start": local_start,
                    "end": max(
                        local_start
                        + 0.08,
                        local_end,
                    ),
                }
            )

    return words


def words_to_chunks(
    words: list[dict[str, Any]],
) -> list[
    list[dict[str, Any]]
]:

    chunks: list[
        list[dict[str, Any]]
    ] = []

    current: list[
        dict[str, Any]
    ] = []

    for word in words:
        current.append(
            word
        )

        text = " ".join(
            item["text"]
            for item in current
        )

        duration = (
            current[-1]["end"]
            - current[0]["start"]
        )

        finish = (
            len(current) >= 4
            or (
                len(current) >= 3
                and duration >= 1.2
            )
            or len(text) >= 28
            or (
                len(current) >= 2
                and current[-1][
                    "text"
                ].endswith(
                    (
                        ".",
                        "!",
                        "?",
                        ",",
                        ":",
                        ";",
                    )
                )
            )
        )

        if finish:
            chunks.append(
                current
            )

            current = []

    if current:
        chunks.append(
            current
        )

    return chunks


def create_karaoke_text(
    words: list[dict[str, Any]],
) -> str:

    parts: list[str] = []

    for word in words:
        duration = max(
            0.08,
            word["end"]
            - word["start"],
        )

        parts.append(
            "{\\kf"
            + str(
                max(
                    8,
                    int(
                        duration
                        * 100
                    ),
                )
            )
            + "}"
            + escape_ass_text(
                word["text"]
            )
        )

    return " ".join(
        parts
    )


def create_ass(
    transcript: dict[str, Any],
    ass_file: Path,
    trim_start: float,
    trim_end: float,
) -> int:

    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        "PlayResX: 1080",
        "PlayResY: 1920",
        "ScaledBorderAndShadow: yes",
        "WrapStyle: 2",
        "",
        "[V4+ Styles]",
        (
            "Format: Name, Fontname, Fontsize, PrimaryColour, "
            "SecondaryColour, OutlineColour, BackColour, Bold, "
            "Italic, Underline, StrikeOut, ScaleX, ScaleY, "
            "Spacing, Angle, BorderStyle, Outline, Shadow, "
            "Alignment, MarginL, MarginR, MarginV, Encoding"
        ),
        (
            "Style: TikTok,DejaVu Sans,70,"
            "&H00FFFFFF,&H0000FFFF,&H00000000,&H70000000,"
            "-1,0,0,0,100,100,1,0,1,5,1,2,70,70,390,1"
        ),
        "",
        "[Events]",
        (
            "Format: Layer, Start, End, Style, Name, "
            "MarginL, MarginR, MarginV, Effect, Text"
        ),
    ]

    words = extract_words(
        transcript,
        trim_start,
        trim_end,
    )

    chunks = words_to_chunks(
        words
    )

    for chunk in chunks:
        start = chunk[0][
            "start"
        ]

        end = max(
            start + 0.35,
            chunk[-1][
                "end"
            ],
        )

        lines.append(
            f"Dialogue: 0,"
            f"{ass_time(start)},"
            f"{ass_time(end)},"
            "TikTok,,0,0,0,,"
            f"{create_karaoke_text(chunk)}"
        )

    with ass_file.open(
        "w",
        encoding="utf-8",
    ) as handle:
        handle.write(
            "\n".join(
                lines
            )
        )

    return len(
        chunks
    )


def escape_filter_path(
    path: Path,
) -> str:

    return (
        str(
            path.resolve()
        )
        .replace(
            "\\",
            "/",
        )
        .replace(
            ":",
            "\\:",
        )
        .replace(
            "'",
            "\\'",
        )
    )


def escape_drawtext(
    value: str,
) -> str:

    return (
        value.replace(
            "\\",
            "",
        )
        .replace(
            "'",
            "\\'",
        )
        .replace(
            ":",
            "\\:",
        )
    )


def create_filter(
    ass_file: Path,
) -> tuple[str, str]:

    filter_parts = [
        "[0:v]fps=30,split=2[bgsrc][fgsrc]",
        (
            "[bgsrc]"
            "scale=1080:1920:"
            "force_original_aspect_ratio=increase,"
            "crop=1080:1920,"
            "boxblur=28:12,"
            "eq=brightness=-0.15:saturation=0.90,"
            "setsar=1[bg]"
        ),
        (
            "[fgsrc]"
            "scale=1080:1920:"
            "force_original_aspect_ratio=decrease,"
            "eq=contrast=1.025:saturation=1.04,"
            "setsar=1[fg]"
        ),
        (
            "[bg][fg]"
            "overlay=(W-w)/2:(H-h)/2-35"
            "[combined]"
        ),
        (
            "[combined]"
            "drawtext="
            f"text='{escape_drawtext(WATERMARK)}':"
            "font='DejaVu Sans':"
            "fontsize=34:"
            "fontcolor=white@0.34:"
            "borderw=2:"
            "bordercolor=black@0.30:"
            "x=w-text_w-42:"
            "y=300"
            "[watermarked]"
        ),
        (
            "[watermarked]"
            "subtitles='"
            + escape_filter_path(
                ass_file
            )
            + "':fontsdir="
            "/usr/share/fonts/truetype"
            "[final]"
        ),
    ]

    return (
        ";".join(
            filter_parts
        ),
        "[final]",
    )


def probe_output(
    path: Path,
) -> dict[str, Any]:

    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        (
            "format=duration,size:"
            "stream=codec_type,"
            "codec_name,width,height"
        ),
        "-of",
        "json",
        str(path),
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        raise RuntimeError(
            "ffprobe fehlgeschlagen."
        )

    return json.loads(
        result.stdout
    )


def validate_output(
    path: Path,
    expected_duration: float,
) -> dict[str, Any]:

    if (
        not path.exists()
        or path.stat().st_size
        < 100_000
    ):
        raise RuntimeError(
            f"Output fehlt/zu klein: {path}"
        )

    probe = probe_output(
        path
    )

    streams = probe.get(
        "streams",
        [],
    )

    video_stream = next(
        (
            stream
            for stream in streams
            if stream.get(
                "codec_type"
            )
            == "video"
        ),
        None,
    )

    audio_stream = next(
        (
            stream
            for stream in streams
            if stream.get(
                "codec_type"
            )
            == "audio"
        ),
        None,
    )

    if (
        not video_stream
        or not audio_stream
    ):
        raise RuntimeError(
            "Video- oder Audiostream fehlt."
        )

    if (
        int(
            video_stream.get(
                "width",
                0,
            )
        )
        != TARGET_WIDTH
        or int(
            video_stream.get(
                "height",
                0,
            )
        )
        != TARGET_HEIGHT
    ):
        raise RuntimeError(
            "Falsche AuflÃ¶sung."
        )

    duration = safe_float(
        probe.get(
            "format",
            {},
        ).get(
            "duration"
        ),
        0.0,
    )

    if (
        duration <= 0
        or abs(
            duration
            - expected_duration
        )
        > 1.25
    ):
        raise RuntimeError(
            f"Falsche Dauer: "
            f"{duration:.2f}s"
        )

    return {
        "duration": round(
            duration,
            3,
        ),
        "size_bytes": path.stat().st_size,
        "video_codec": video_stream.get(
            "codec_name",
            "",
        ),
        "audio_codec": audio_stream.get(
            "codec_name",
            "",
        ),
    }


def process_video(
    source: Path,
    output: Path,
    metadata: dict[str, Any],
    temp_dir: Path,
) -> dict[str, Any]:

    trim_start = max(
        0.0,
        safe_float(
            metadata.get(
                "trim_start"
            ),
            0.0,
        ),
    )

    trim_end = safe_float(
        metadata.get(
            "trim_end"
        ),
        0.0,
    )

    if trim_end <= trim_start:
        trim_end = (
            trim_start
            + max(
                10.0,
                safe_float(
                    metadata.get(
                        "duration"
                    ),
                    30.0,
                ),
            )
        )

    output_duration = (
        trim_end
        - trim_start
    )

    transcript = load_transcript(
        source
    )

    if not transcript:
        raise RuntimeError(
            f"Transkript fehlt fÃ¼r {source.name}"
        )

    ass_file = (
        temp_dir
        / f"caption_{video_number(source)}.ass"
    )

    caption_count = create_ass(
        transcript,
        ass_file,
        trim_start,
        trim_end,
    )

    if caption_count <= 0:
        raise RuntimeError(
            f"Keine Untertitel fÃ¼r {source.name}"
        )

    (
        filter_complex,
        final_stream,
    ) = create_filter(
        ass_file
    )

    command: list[Any] = [
        "ffmpeg",
        "-y",
        "-ss",
        f"{trim_start:.3f}",
        "-i",
        source,
        "-t",
        f"{output_duration:.3f}",
        "-filter_complex",
        filter_complex,
        "-map",
        final_stream,
        "-map",
        "0:a:0",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "19",
        "-pix_fmt",
        "yuv420p",
        "-profile:v",
        "high",
        "-level",
        "4.1",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-ar",
        "48000",
        "-af",
        "loudnorm=I=-16:TP=-1.5:LRA=9",
        "-movflags",
        "+faststart",
        "-shortest",
        output,
    ]

    run(
        command
    )

    technical = validate_output(
        output,
        output_duration,
    )

    return {
        "file": output.name,
        "clip_id": metadata.get(
            "id",
            "",
        ),
        "title": metadata.get(
            "title",
            "",
        ),
        "viral_score": metadata.get(
            "viral_score",
            0.0,
        ),
        "selection_tier": metadata.get(
            "selection_tier",
            "",
        ),
        "subtitles": True,
        "hook": "",
        "hook_duration_seconds": 0.0,
        "caption_blocks": caption_count,
        "trim_start": trim_start,
        "trim_end": trim_end,
        **technical,
    }


def copy_selection_report() -> None:
    if (
        Path(
            SELECTION_REPORT_FILE
        ).exists()
    ):
        shutil.copy2(
            SELECTION_REPORT_FILE,
            OUTPUT_DIR
            / "selection_report.json",
        )


def main() -> None:
    print(
        "=" * 64
    )
    print(
        f"CLIPCRIP CLEAN RENDERER | {STREAMER_NAME}"
    )
    print(
        "V2: Clip + dynamische Untertitel + kurze Hook."
    )
    print(
        "=" * 64
    )

    temp_dir = clean_output()

    videos = find_videos()[
        :MAX_VIDEOS
    ]

    metadata_list = load_json(
        METADATA_FILE,
        [],
    )

    if not isinstance(
        metadata_list,
        list,
    ):
        raise RuntimeError(
            "clips_today.json ungÃ¼ltig."
        )

    if len(videos) < MIN_VIDEOS:
        raise RuntimeError(
            f"Nur {len(videos)} ausgewÃ¤hlte Clips vorhanden. "
            f"Mindestziel sind {MIN_VIDEOS}."
        )

    if len(videos) != len(
        metadata_list
    ):
        raise RuntimeError(
            f"Videos ({len(videos)}) und Metadaten "
            f"({len(metadata_list)}) passen nicht zusammen."
        )

    outputs: list[
        dict[str, Any]
    ] = []

    failures: list[
        dict[str, str]
    ] = []

    run_stamp = datetime.now(
        timezone.utc
    ).strftime(
        "%Y%m%d"
    )

    for index, source in enumerate(
        videos,
        start=1,
    ):
        metadata = metadata_list[
            index - 1
        ]

        if not isinstance(
            metadata,
            dict,
        ):
            failures.append(
                {
                    "video": source.name,
                    "error": "Metadaten ungÃ¼ltig",
                }
            )
            continue

        clip_id = re.sub(
            r"[^A-Za-z0-9]",
            "",
            str(
                metadata.get(
                    "id",
                    "",
                )
            ),
        )[:12]

        identity = (
            clip_id
            or f"clip{index}"
        )

        output = (
            OUTPUT_DIR
            / (
                f"{run_stamp}_"
                f"{index:02d}_"
                f"{OUTPUT_PREFIX}_"
                f"{identity}.mp4"
            )
        )

        try:
            result = process_video(
                source,
                output,
                metadata,
                temp_dir,
            )

            outputs.append(
                result
            )

            print(
                f"FERTIG {index}/{len(videos)} | "
                f"{result['duration']:.1f}s | "
                f"Untertitel: JA | "
                f"Hook: {result.get('hook', '')}"
            )

        except Exception as error:
            failures.append(
                {
                    "video": source.name,
                    "error": str(error),
                }
            )

            print(
                f"RENDER-FEHLER "
                f"{source.name}: "
                f"{error}"
            )

    shutil.rmtree(
        temp_dir,
        ignore_errors=True,
    )

    if failures:
        save_json(
            OUTPUT_DIR
            / "publish_manifest.json",
            {
                "streamer": STREAMER_NAME,
                "status": "render_failed",
                "output_count": len(
                    outputs
                ),
                "videos": outputs,
                "failures": failures,
            },
        )

        raise RuntimeError(
            f"{len(failures)} Videos "
            "konnten nicht gerendert werden."
        )

    if len(
        outputs
    ) < MIN_VIDEOS:
        raise RuntimeError(
            f"Nur {len(outputs)} fertige Videos. "
            f"Mindestziel sind {MIN_VIDEOS}."
        )

    manifest = {
        "streamer": STREAMER_NAME,
        "status": "ready",
        "output_count": len(
            outputs
        ),
        "minimum_required": MIN_VIDEOS,
        "target": MAX_VIDEOS,
        "hooks": False,
        "hook_style": "disabled-manual-hooks",
        "subtitles": True,
        "videos": outputs,
    }

    save_json(
        OUTPUT_DIR
        / "publish_manifest.json",
        manifest,
    )

    copy_selection_report()

    print(
        "=" * 64
    )
    print(
        f"RENDERER FERTIG | "
        f"{len(outputs)} Videos | "
        "KEINE AUTO-HOOKS"
    )
    print(
        "=" * 64
    )


if __name__ == "__main__":
    main()