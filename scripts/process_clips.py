"""Render the variable output of the shared ClipCrip quality gate.

Hooks are evidence-based and optional. They stay visible for the first 3.6
seconds only, contain no emoji glyphs, and never fall back to generic clickbait.
Whisper transcripts produced during selection are reused, long clips are cut to
the selected event window, audio is normalized, and every output is validated.
"""

from __future__ import annotations

import hashlib
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

MAX_VIDEOS = 3
WHISPER_MODEL = "turbo"
OUTPUT_PREFIX = "jussef_tiktok"
WATERMARK = "@clipcrip2"
STREAMER_NAME = "Jussef"

TARGET_WIDTH = 1080
TARGET_HEIGHT = 1920
HOOK_DURATION = 3.6
HOOK_MIN_CONFIDENCE = 0.55

BASE_PROMPT = (
    "Deutscher Twitch-Stream von Jussef. Die Sprecher reden schnell, locker "
    "und umgangssprachlich. Namen und Wörter: Jussef, Yussef, Yavuz, Chat, "
    "Bro, Bruder, Digga, Wallah, crashout. Transkribiere wortgetreu und "
    "behalte Jugendsprache bei."
)


HOOK_TEMPLATES: dict[str, list[str]] = {
    "laugh": [
        "{name} kann nicht mehr",
        "{name} bricht komplett weg",
        "Bro kann nicht mehr",
    ],
    "rage": [
        "{name} geht crashout",
        "{name} reicht's komplett",
        "Bro hat komplett genug",
    ],
    "surprise": [
        "{name} checkt gar nichts",
        "{name} ist sprachlos",
        "Bro glaubt es nicht",
    ],
    "fail": [
        "{name} ist cooked",
        "{name} verkackt komplett",
        "Bro hats verkackt",
    ],
    "chat": [
        "Chat macht {name} fertig",
        "Chat trollt {name}",
        "{name} gegen den Chat",
    ],
    "roast": [
        "{name} wird hops genommen",
        "{name} wurde erwischt",
        "Bro wurde zerlegt",
    ],
}


def run(command: list[Any]) -> None:
    normalized = [str(item) for item in command]
    print("RUN:", " ".join(normalized))
    result = subprocess.run(normalized, check=False)
    if result.returncode != 0:
        raise RuntimeError("Befehl fehlgeschlagen: " + " ".join(normalized))


def load_json(path: str | Path, default: Any) -> Any:
    file_path = Path(path)
    if not file_path.exists():
        return default
    try:
        with file_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError, TypeError):
        return default


def save_json(path: str | Path, data: Any) -> None:
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with file_path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)


def clean_output() -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for item in OUTPUT_DIR.iterdir():
        if item.is_file() or item.is_symlink():
            item.unlink()
        elif item.is_dir():
            shutil.rmtree(item)
    temp_dir = OUTPUT_DIR / "_temp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    return temp_dir


def video_number(path: Path) -> int:
    match = re.search(r"clip_(\d+)", path.stem, re.IGNORECASE)
    if match:
        return int(match.group(1))
    match = re.search(r"(\d+)", path.stem)
    return int(match.group(1)) if match else 999999


def find_videos() -> list[Path]:
    extensions = {".mp4", ".webm", ".mkv", ".mov", ".m4v"}
    if not INPUT_DIR.exists():
        return []
    videos = [
        path
        for path in INPUT_DIR.iterdir()
        if path.is_file() and path.suffix.lower() in extensions
    ]
    return sorted(videos, key=lambda path: (video_number(path), path.name.lower()))


def clean_text(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text.replace("{", "(").replace("}", ")").replace("\\", "")


def safe_hook_text(value: Any) -> str:
    text = clean_text(value)
    text = re.sub(r"[^A-Za-z0-9ÄÖÜäöüß?!.,'’\- ]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def escape_ass_text(value: Any) -> str:
    return clean_text(value).replace("\n", " ")


def stable_choice(values: list[str], seed: str) -> str:
    if not values:
        return ""
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    return values[int.from_bytes(digest[:4], "big") % len(values)]


def create_hook(metadata: dict[str, Any]) -> str:
    category = str(metadata.get("hook_category", "")).strip().lower()
    try:
        confidence = float(metadata.get("hook_confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    if category not in HOOK_TEMPLATES or confidence < HOOK_MIN_CONFIDENCE:
        return ""

    template = stable_choice(
        HOOK_TEMPLATES[category],
        f"{metadata.get('id', '')}|{metadata.get('title', '')}|{category}",
    )
    hook = safe_hook_text(template.format(name=STREAMER_NAME))
    words = hook.split()
    if not hook or len(words) < 2 or len(words) > 6:
        return ""
    return hook


def hook_to_ass(value: str) -> str:
    words = escape_ass_text(value).split()
    if len(words) <= 4:
        return " ".join(words)
    split_at = (len(words) + 1) // 2
    return " ".join(words[:split_at]) + "\\N" + " ".join(words[split_at:])


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def compact_transcript(raw: dict[str, Any]) -> dict[str, Any]:
    segments: list[dict[str, Any]] = []
    for segment in raw.get("segments", []):
        if not isinstance(segment, dict):
            continue
        words: list[dict[str, Any]] = []
        for word in segment.get("words", []) or []:
            if not isinstance(word, dict):
                continue
            start = safe_float(word.get("start"), 0.0)
            end = safe_float(word.get("end"), start + 0.2)
            words.append(
                {
                    "word": str(word.get("word", "")),
                    "start": round(start, 3),
                    "end": round(max(start + 0.05, end), 3),
                }
            )
        start = safe_float(segment.get("start"), 0.0)
        end = safe_float(segment.get("end"), start + 0.5)
        segments.append(
            {
                "start": round(start, 3),
                "end": round(max(start + 0.05, end), 3),
                "text": str(segment.get("text", "")).strip(),
                "words": words,
            }
        )
    return {"text": str(raw.get("text", "")).strip(), "segments": segments}


_WHISPER_MODEL_INSTANCE: Any = None


def transcribe_fallback(video: Path, clip_title: str) -> dict[str, Any] | None:
    global _WHISPER_MODEL_INSTANCE
    try:
        if _WHISPER_MODEL_INSTANCE is None:
            import whisper

            print(f"Fallback-Whisper wird einmal geladen: {WHISPER_MODEL}")
            _WHISPER_MODEL_INSTANCE = whisper.load_model(WHISPER_MODEL)
        prompt = BASE_PROMPT
        if clip_title:
            prompt += " Twitch-Clip-Titel: " + clean_text(clip_title) + "."
        raw = _WHISPER_MODEL_INSTANCE.transcribe(
            str(video),
            language="de",
            task="transcribe",
            word_timestamps=True,
            initial_prompt=prompt,
            temperature=0.0,
            condition_on_previous_text=False,
            fp16=False,
            verbose=False,
        )
        return compact_transcript(raw)
    except Exception as error:
        print(f"WARNUNG: Fallback-Whisper fehlgeschlagen: {error}")
        return None


def load_transcript(source: Path, metadata: dict[str, Any]) -> dict[str, Any] | None:
    transcript_path = source.with_suffix(".transcript.json")
    transcript = load_json(transcript_path, None)
    if isinstance(transcript, dict):
        print(f"QC-Transkript wird wiederverwendet: {transcript_path.name}")
        return transcript
    return transcribe_fallback(source, str(metadata.get("title", "")))


def ass_time(seconds: float) -> str:
    value = max(0.0, float(seconds))
    hours = int(value // 3600)
    minutes = int((value % 3600) // 60)
    secs = int(value % 60)
    centiseconds = max(0, min(99, int((value - int(value)) * 100)))
    return f"{hours}:{minutes:02d}:{secs:02d}.{centiseconds:02d}"


def extract_words(
    transcript: dict[str, Any], trim_start: float, trim_end: float
) -> list[dict[str, Any]]:
    words: list[dict[str, Any]] = []
    for segment in transcript.get("segments", []):
        if not isinstance(segment, dict):
            continue
        for word in segment.get("words", []) or []:
            if not isinstance(word, dict):
                continue
            text = clean_text(word.get("word", ""))
            start = safe_float(word.get("start"), 0.0)
            end = safe_float(word.get("end"), start + 0.2)
            if not text or end <= trim_start or start >= trim_end:
                continue
            local_start = max(0.0, start - trim_start)
            local_end = min(trim_end, end) - trim_start
            words.append(
                {
                    "text": text,
                    "start": local_start,
                    "end": max(local_start + 0.08, local_end),
                }
            )
    return words


def extract_segments(
    transcript: dict[str, Any], trim_start: float, trim_end: float
) -> list[dict[str, Any]]:
    segments: list[dict[str, Any]] = []
    for segment in transcript.get("segments", []):
        if not isinstance(segment, dict):
            continue
        text = clean_text(segment.get("text", ""))
        start = safe_float(segment.get("start"), 0.0)
        end = safe_float(segment.get("end"), start + 0.5)
        if not text or end <= trim_start or start >= trim_end:
            continue
        local_start = max(0.0, start - trim_start)
        local_end = min(trim_end, end) - trim_start
        segments.append(
            {
                "text": text,
                "start": local_start,
                "end": max(local_start + 0.35, local_end),
            }
        )
    return segments


def words_to_chunks(words: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    chunks: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for word in words:
        current.append(word)
        text = " ".join(item["text"] for item in current)
        duration = current[-1]["end"] - current[0]["start"]
        finish = (
            len(current) >= 4
            or (len(current) >= 3 and duration >= 1.2)
            or (
                len(current) >= 2
                and current[-1]["text"].endswith((".", "!", "?", ",", ":", ";"))
            )
            or len(text) >= 28
        )
        if finish:
            chunks.append(current)
            current = []
    if current:
        chunks.append(current)
    return chunks


def create_karaoke_text(words: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for word in words:
        duration = max(0.08, word["end"] - word["start"])
        parts.append(
            "{\\kf" + str(max(8, int(duration * 100))) + "}" + escape_ass_text(word["text"])
        )
    return " ".join(parts)


def split_segment(segment: dict[str, Any]) -> list[dict[str, Any]]:
    words = segment["text"].split()
    if not words:
        return []
    pieces = [words[index : index + 4] for index in range(0, len(words), 4)]
    duration = max(0.5, segment["end"] - segment["start"])
    return [
        {
            "text": " ".join(piece),
            "start": segment["start"] + duration * index / len(pieces),
            "end": segment["start"] + duration * (index + 1) / len(pieces),
        }
        for index, piece in enumerate(pieces)
    ]


def create_ass(
    transcript: dict[str, Any] | None,
    ass_file: Path,
    metadata: dict[str, Any],
    trim_start: float,
    trim_end: float,
) -> dict[str, Any]:
    header = [
        "[Script Info]",
        "ScriptType: v4.00+",
        "PlayResX: 1080",
        "PlayResY: 1920",
        "ScaledBorderAndShadow: yes",
        "WrapStyle: 2",
        "",
        "[V4+ Styles]",
        (
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
            "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
            "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
            "Alignment, MarginL, MarginR, MarginV, Encoding"
        ),
        (
            "Style: TikTok,DejaVu Sans,70,&H00FFFFFF,&H0000FFFF,&H00000000,"
            "&H70000000,-1,0,0,0,100,100,1,0,1,5,1,2,70,70,390,1"
        ),
        (
            "Style: Hook,DejaVu Sans,76,&H00FFFFFF,&H00FFFFFF,&H00000000,"
            "&H70000000,-1,0,0,0,100,100,0,0,3,6,0,8,80,80,175,1"
        ),
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    lines = list(header)
    hook = create_hook(metadata)
    if hook:
        lines.append(
            "Dialogue: 1,0:00:00.00,"
            + ass_time(min(HOOK_DURATION, max(0.5, trim_end - trim_start)))
            + ",Hook,,0,0,0,,"
            + hook_to_ass(hook)
        )

    caption_count = 0
    if transcript:
        words = extract_words(transcript, trim_start, trim_end)
        if words:
            for chunk in words_to_chunks(words):
                start = chunk[0]["start"]
                end = max(start + 0.35, chunk[-1]["end"])
                lines.append(
                    f"Dialogue: 0,{ass_time(start)},{ass_time(end)},"
                    f"TikTok,,0,0,0,,{create_karaoke_text(chunk)}"
                )
                caption_count += 1
        else:
            for segment in extract_segments(transcript, trim_start, trim_end):
                for group in split_segment(segment):
                    lines.append(
                        f"Dialogue: 0,{ass_time(group['start'])},{ass_time(group['end'])},"
                        f"TikTok,,0,0,0,,{escape_ass_text(group['text'])}"
                    )
                    caption_count += 1

    with ass_file.open("w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))
    return {
        "hook": hook,
        "has_subtitles": caption_count > 0,
        "has_ass_content": bool(hook or caption_count),
        "caption_count": caption_count,
    }


def escape_filter_path(path: Path) -> str:
    return (
        str(path.resolve())
        .replace("\\", "/")
        .replace(":", "\\:")
        .replace("'", "\\'")
    )


def escape_drawtext(value: str) -> str:
    return value.replace("\\", "").replace("'", "\\'").replace(":", "\\:")


def create_filter(ass_file: Path, has_ass_content: bool) -> tuple[str, str]:
    filter_parts = [
        "[0:v]fps=30,split=2[bgsrc][fgsrc]",
        (
            "[bgsrc]scale=1080:1920:force_original_aspect_ratio=increase,"
            "crop=1080:1920,boxblur=28:12,eq=brightness=-0.15:saturation=0.90,"
            "setsar=1[bg]"
        ),
        (
            "[fgsrc]scale=1080:1920:force_original_aspect_ratio=decrease,"
            "eq=contrast=1.025:saturation=1.04,setsar=1[fg]"
        ),
        "[bg][fg]overlay=(W-w)/2:(H-h)/2-35[combined]",
        (
            "[combined]drawtext="
            f"text='{escape_drawtext(WATERMARK)}':"
            "font='DejaVu Sans':fontsize=34:fontcolor=white@0.34:"
            "borderw=2:bordercolor=black@0.30:"
            "x=w-text_w-42:y=300[watermarked]"
        ),
    ]
    current = "[watermarked]"
    if has_ass_content:
        filter_parts.append(
            current
            + "subtitles='"
            + escape_filter_path(ass_file)
            + "':fontsdir=/usr/share/fonts/truetype[final]"
        )
        current = "[final]"
    return ";".join(filter_parts), current


def probe_output(path: Path) -> dict[str, Any]:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration,size:stream=codec_type,codec_name,width,height,pix_fmt",
        "-of",
        "json",
        str(path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe fehlgeschlagen: {result.stderr[-1000:]}")
    return json.loads(result.stdout)


def validate_output(path: Path, expected_duration: float) -> dict[str, Any]:
    if not path.exists() or path.stat().st_size < 100_000:
        raise RuntimeError(f"Output fehlt oder ist zu klein: {path}")
    probe = probe_output(path)
    streams = probe.get("streams", [])
    video_stream = next(
        (stream for stream in streams if stream.get("codec_type") == "video"), None
    )
    audio_stream = next(
        (stream for stream in streams if stream.get("codec_type") == "audio"), None
    )
    if not video_stream or not audio_stream:
        raise RuntimeError(f"Video- oder Audiostream fehlt: {path}")
    if (
        int(video_stream.get("width", 0)) != TARGET_WIDTH
        or int(video_stream.get("height", 0)) != TARGET_HEIGHT
    ):
        raise RuntimeError(f"Falsche Auflösung: {path}")
    duration = safe_float(probe.get("format", {}).get("duration"), 0.0)
    if duration <= 0 or abs(duration - expected_duration) > 1.25:
        raise RuntimeError(
            f"Unerwartete Dauer {duration:.2f}s statt {expected_duration:.2f}s: {path}"
        )
    return {
        "duration": round(duration, 3),
        "size_bytes": path.stat().st_size,
        "video_codec": video_stream.get("codec_name", ""),
        "audio_codec": audio_stream.get("codec_name", ""),
    }


def process_video(
    source: Path,
    output: Path,
    metadata: dict[str, Any],
    temp_dir: Path,
) -> dict[str, Any]:
    trim_start = max(0.0, safe_float(metadata.get("trim_start"), 0.0))
    trim_end = safe_float(metadata.get("trim_end"), 0.0)
    if trim_end <= trim_start:
        trim_end = trim_start + max(10.0, safe_float(metadata.get("duration"), 30.0))
    output_duration = trim_end - trim_start

    transcript = load_transcript(source, metadata)
    ass_file = temp_dir / f"caption_{video_number(source)}.ass"
    ass_result = create_ass(transcript, ass_file, metadata, trim_start, trim_end)
    filter_complex, final_stream = create_filter(
        ass_file, bool(ass_result["has_ass_content"])
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
    run(command)
    technical = validate_output(output, output_duration)
    return {
        "file": output.name,
        "clip_id": metadata.get("id", ""),
        "title": metadata.get("title", ""),
        "viral_score": metadata.get("viral_score", 0.0),
        "hook": ass_result["hook"],
        "hook_category": metadata.get("hook_category", ""),
        "hook_confidence": metadata.get("hook_confidence", 0.0),
        "subtitles": ass_result["has_subtitles"],
        "caption_blocks": ass_result["caption_count"],
        "trim_start": trim_start,
        "trim_end": trim_end,
        **technical,
    }


def copy_selection_report() -> None:
    if Path(SELECTION_REPORT_FILE).exists():
        shutil.copy2(SELECTION_REPORT_FILE, OUTPUT_DIR / "selection_report.json")


def main() -> None:
    print("=" * 64)
    print(f"CLIPCRIP RETENTION RENDERER V6 | {STREAMER_NAME}")
    print("Hooks: nur belegt, ohne Emoji, maximal 3.6 Sekunden")
    print("=" * 64)
    temp_dir = clean_output()
    videos = find_videos()[:MAX_VIDEOS]
    metadata_list = load_json(METADATA_FILE, [])
    if not isinstance(metadata_list, list):
        metadata_list = []

    if not videos:
        manifest = {
            "streamer": STREAMER_NAME,
            "status": "no_strong_clips",
            "output_count": 0,
            "videos": [],
        }
        save_json(OUTPUT_DIR / "publish_manifest.json", manifest)
        shutil.rmtree(temp_dir, ignore_errors=True)
        copy_selection_report()
        print("Kein starker Clip ausgewählt. Erfolgreicher Run ohne Füllmaterial.")
        return

    if len(videos) != len(metadata_list):
        raise RuntimeError(
            f"Selected-Clips ({len(videos)}) und Metadaten ({len(metadata_list)}) "
            "passen nicht zusammen."
        )

    outputs: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    run_stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    for index, source in enumerate(videos, start=1):
        metadata = metadata_list[index - 1]
        if not isinstance(metadata, dict):
            failures.append({"video": source.name, "error": "Metadaten ungültig"})
            continue
        clip_id = re.sub(r"[^A-Za-z0-9]", "", str(metadata.get("id", "")))[:12]
        identity = clip_id or f"clip{index}"
        output = OUTPUT_DIR / (
            f"{run_stamp}_{index:02d}_{OUTPUT_PREFIX}_{identity}.mp4"
        )
        try:
            result = process_video(source, output, metadata, temp_dir)
            outputs.append(result)
            print(
                f"FERTIG {index}/{len(videos)} | {result['duration']:.1f}s | "
                f"Hook: {result['hook'] or 'keine'}"
            )
        except Exception as error:
            failures.append({"video": source.name, "error": str(error)})
            print(f"RENDER-FEHLER {source.name}: {error}")

    shutil.rmtree(temp_dir, ignore_errors=True)
    if failures or len(outputs) != len(videos):
        save_json(
            OUTPUT_DIR / "publish_manifest.json",
            {
                "streamer": STREAMER_NAME,
                "status": "render_failed",
                "output_count": len(outputs),
                "videos": outputs,
                "failures": failures,
            },
        )
        raise RuntimeError(f"{len(failures)} ausgewählte Videos konnten nicht rendern.")

    manifest = {
        "streamer": STREAMER_NAME,
        "status": "ready",
        "output_count": len(outputs),
        "videos": outputs,
    }
    save_json(OUTPUT_DIR / "publish_manifest.json", manifest)
    copy_selection_report()

    print("=" * 64)
    print(f"RENDERER FERTIG | {len(outputs)} statt erzwungener 5 Clips")
    print("=" * 64)


if __name__ == "__main__":
    main()
