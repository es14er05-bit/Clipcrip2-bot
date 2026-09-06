"""MW4: two review packages; never posts, submits, or claims earned money."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import textwrap
import zipfile
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

from subtitles import build_german_subtitles

ROOT = Path(__file__).resolve().parent
STATE = ROOT / "state/mw4.json"
CACHE = ROOT / "cache"
OUTPUT = ROOT / "output"

CAMPAIGN = "2432b187-415b-437c-9545-8cfa032a6155"
RULES = (
    "https://docs.google.com/document/d/"
    "1greWI_Iav9EvWzPMUUSczDBJsd_VgYOagYUmu6CjEow/edit"
)
DRIVE = "https://www.googleapis.com/drive/v3/files"


# ============================================================
# FREIGEGEBENE KAMPAGNEN-QUELLEN
# ============================================================

SOURCES = [
    (
        "1ikTpY_xctEHa9iSuFakTvTEVkIOAVfiv",
        "Pistole",
        "3 Gegner. Nur eine Pistole.",
    ),
    (
        "1Pbm7v5qE-SyDA5e9aeL7mH61ViW2JfAU",
        "Sniper",
        "3 Snipes. Direkt hintereinander.",
    ),
    (
        "1F9cCbVztPUP7sBiWVnpLescRPdyMqqTr",
        "Movement",
        "Dieses Movement macht den Unterschied.",
    ),
    (
        "1MQKZmzlRTz_Xoi5ZGHSfnQ54d9r0lvtB",
        "Spielzug",
        "Warte bis zum fünften Gegner.",
    ),
    (
        "11T2_z_-6l6CNJ83OFaEvO4HSU18OmIII",
        "Spielzug",
        "Wie lange hält er dieses 1v3?",
    ),
    (
        "1eRzChBSJSTH_uGhm9QpkOrQsaRRYo8Av",
        "Spielzug",
        "Pistole und Messer gegen vier Gegner.",
    ),
    (
        "1B8QHC8-DS25Z4Tj5U0LhlzSRmi1KQAou",
        "Spielzug",
        "Mit der PPSH gegen vier Gegner.",
    ),
    (
        "1_gpXpqmyqns5gGvSQ0rGP5Ip1dCxB7qP",
        "Movement",
        "Dieses Shotgun-Movement ist so clean.",
    ),
    (
        "19tId1rMDiR5zfWLWv1FpYmuC1CGw0xRV",
        "Spielzug",
        "Wie weit kommt er in diesem 1v4?",
    ),
    (
        "10lvHQPyLU9SVb3IepPWk1oVGRDfCiEc0",
        "Kulissen",
        "So sieht MW4 hinter den Kulissen aus.",
    ),
]


CATALOG = {
    sid: {
        "topic": topic,
        "hook": hook,
        "creator": "" if topic == "Kulissen" else "@averagejoewo",
    }
    for sid, topic, hook in SOURCES
}


# Weitere bereits im ursprünglichen Work-Bot freigegebene
# Kampagnenquellen.
EXTRA_SOURCES = [
    ("1BdQ0GaWyk_Y8acaCpSrnDpwtugST5S7z", "@tdawgsmitty"),
    ("1zQaSrEpjvCPYD-gfBE8aiRrIyFzAjqQq", "@tdawgsmitty"),
    ("1Rv_FxbZHzvyO5CsYj2YOOsROiyXGVPEx", "@tdawgsmitty"),

    ("11Ae6KGr3puVbhmdzj59mv56LCfCsgX8i", "@vauxie"),
    ("1OH3u2mfEx8Blb1bK1_tcjb6PCnI1mmkO", "@vauxie"),

    ("1P7-XPYGPPkCYWuNMVJgaYYeqolFF2eQ-", "@chrispreds"),
    ("1Y4PpuceBUF7liojOgrawZykAgpJJ71MG", "@chrispreds"),

    ("1LZOVMn4G7hDDWbXMXEIJkyvyvPiLocVK", "@thejaybroski"),
    ("1yhqkiKvnjVhQDvcsbNdMFhGM1nkcdSfv", "@thejaybroski"),
    ("1M6ebmW4AclwALXlfCa-sI4Iv6fOc8FHS", "@thejaybroski"),
    ("1A69nxT7xSHqeI-0xikm-c0UBttCwDpKs", "@thejaybroski"),
    ("1O-nhACUbo44_ZrwFFJsZgwSFXu2Sr0O5", "@thejaybroski"),

    ("1YtsSFDxIoZoulTntf_yjUicKIaZkLLmn", "@j9streams"),
    ("1R-pKNx2tSY0oLEn63LaR1stIRgngDZ3-", "@j9streams"),
    ("10KUVlh_RBCtziSTpO34Q5jF7qGVor7KX", "@j9streams"),
    ("16vCvB3B7AYLN1IA2T_DoB9H1HZCvk9nN", "@j9streams"),
    ("1vC1Zt-n8g4drs1dMQPuldN5sVHVL50zb", "@j9streams"),

    ("1sagZ2jQsdHatEjdWbcHTfDRc8xt0_YWp", "@swiftor"),
    ("1ADxvy9xJ-bib2SGCLUHlvbic3bBf-3c1", "@swiftor"),
    ("1Y689DQODD2I101iQYklSuKHKoPehrkT6", "@swiftor"),
    ("1cvXoaibzeVkPqaZrefSDicibW_BSIWCy", "@swiftor"),
]


for sid, creator in EXTRA_SOURCES:
    CATALOG[sid] = {
        "topic": "Spielzug",
        "hook": "Schau dir diesen MW4-Moment an.",
        "creator": creator,
    }


CHECKS = [
    (
        "Aktiver Kampagnenstatus, Restbudget und aktuelle "
        "Regeln selbst geprüft"
    ),
    (
        "Vollständiges Video angesehen: Aussage korrekt, "
        "positiv, keine Spielevergleiche"
    ),
    (
        "Alle sichtbaren Texte deutsch bzw. zulässige "
        "unveränderte Quelltexte geklärt"
    ),
    (
        "Keine fremden Logos, Musik, Beleidigungen oder "
        "problematischen Szenen"
    ),
    (
        "Creator-Gesicht und ursprüngliche "
        "Entwicklungs-/ALPHA-Hinweise sichtbar"
    ),
    (
        "Caption korrekt; @callofdutyde und gegebenenfalls "
        "Creator als echte Tags gewählt"
    ),
    (
        "Native TikTok-Werbekennzeichnung für eine andere "
        "Marke aktiviert"
    ),
    (
        "Öffentlich; Likes/Kommentare aktiviert und Zahlen sichtbar"
    ),
    (
        "Automatische deutsche Untertitel kurz auf Sinn, "
        "Schreibweise und Ton geprüft"
    ),
    (
        "Post noch nicht veröffentlicht oder eingereicht; "
        "keine externe Promotion"
    ),
    (
        "Nach Posting nach aktuell angezeigtem "
        "Kampagnenprozess einreichen"
    ),
    (
        "Später mindestens 2000 Views und "
        "DE+AT+CH+LU >= 30 Prozent nachweisen"
    ),
]


# ============================================================
# BASIS
# ============================================================

def read_json(path):
    return json.loads(
        Path(path).read_text(encoding="utf-8")
    )


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    temporary = path.with_suffix(
        path.suffix + ".tmp"
    )

    temporary.write_text(
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )

    temporary.replace(path)


def digest(path, algorithm="sha256"):
    h = hashlib.new(algorithm)

    with Path(path).open("rb") as stream:
        for block in iter(
            lambda: stream.read(1024 * 1024),
            b"",
        ):
            h.update(block)

    return h.hexdigest()


def command(args):
    return subprocess.run(
        [str(x) for x in args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout


def probe(path):
    data = json.loads(
        command(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_streams",
                "-show_format",
                "-of",
                "json",
                path,
            ]
        )
    )

    video = next(
        stream
        for stream in data["streams"]
        if stream["codec_type"] == "video"
    )

    if not any(
        stream["codec_type"] == "audio"
        for stream in data["streams"]
    ):
        raise ValueError(
            "Originalaudio fehlt"
        )

    duration = float(
        data["format"]["duration"]
    )

    if not 10 <= duration <= 45:
        raise ValueError(
            "Länge außerhalb 10-45 s; "
            "45 s ist unser Produktionslimit"
        )

    return (
        duration,
        int(video["width"]),
        int(video["height"]),
    )


# ============================================================
# GOOGLE
# ============================================================

def token():
    names = (
        "GOOGLE_CLIENT_ID",
        "GOOGLE_CLIENT_SECRET",
        "GOOGLE_REFRESH_TOKEN",
    )

    if not all(
        os.environ.get(name)
        for name in names
    ):
        raise ValueError(
            "Google-Secrets fehlen; alternativ "
            "Originaldateien unter "
            "mw4/cache/DATEI_ID.mp4 ablegen"
        )

    response = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": os.environ[
                "GOOGLE_CLIENT_ID"
            ],
            "client_secret": os.environ[
                "GOOGLE_CLIENT_SECRET"
            ],
            "refresh_token": os.environ[
                "GOOGLE_REFRESH_TOKEN"
            ],
            "grant_type": "refresh_token",
        },
        timeout=60,
    )

    if response.status_code != 200:
        raise ValueError(
            "Google OAuth fehlgeschlagen "
            f"(HTTP {response.status_code}); "
            "Secrets/Berechtigung prüfen"
        )

    return response.json()["access_token"]


def source_file(sid):
    if sid not in CATALOG:
        raise ValueError(
            "Nicht freigegebene Quellen-ID"
        )

    CACHE.mkdir(
        parents=True,
        exist_ok=True,
    )

    path = CACHE / f"{sid}.mp4"

    if path.exists():
        probe(path)
        return path

    headers = {
        "Authorization": "Bearer " + token()
    }

    meta = requests.get(
        f"{DRIVE}/{sid}",
        headers=headers,
        params={
            "fields": (
                "mimeType,"
                "md5Checksum,"
                "capabilities(canDownload)"
            )
        },
        timeout=60,
    )

    if meta.status_code != 200:
        raise ValueError(
            "Quellenzugriff "
            f"HTTP {meta.status_code}; "
            "Drive-Leseberechtigung erforderlich"
        )

    meta = meta.json()

    if (
        not meta.get(
            "capabilities",
            {},
        ).get("canDownload")
        or not meta.get(
            "mimeType",
            "",
        ).startswith("video/")
    ):
        raise ValueError(
            "Kein erlaubter Videodownload"
        )

    tmp = path.with_suffix(".part")

    with requests.get(
        f"{DRIVE}/{sid}",
        headers=headers,
        params={
            "alt": "media"
        },
        timeout=180,
        stream=True,
    ) as response:

        response.raise_for_status()

        with tmp.open("wb") as stream:
            for chunk in response.iter_content(
                1024 * 1024
            ):
                if chunk:
                    stream.write(chunk)

    expected_md5 = meta.get(
        "md5Checksum"
    )

    if expected_md5:
        actual_md5 = digest(
            tmp,
            "md5",
        )

        if expected_md5 != actual_md5:
            tmp.unlink(
                missing_ok=True
            )

            raise ValueError(
                "Download-Prüfsumme stimmt nicht"
            )

    probe(tmp)

    tmp.replace(path)

    return path


# ============================================================
# DUPLIKAT-ERKENNUNG
# ============================================================

def fingerprints(path):
    raw = command(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            path,
            "-vf",
            (
                "fps=1,"
                "scale=9:8,"
                "format=gray"
            ),
            "-f",
            "rawvideo",
            "-pix_fmt",
            "gray",
            "-",
        ]
    )

    hashes = []

    for offset in range(
        0,
        len(raw) - 71,
        72,
    ):
        frame = raw[
            offset:offset + 72
        ]

        bits = [
            frame[y * 9 + x]
            >
            frame[y * 9 + x + 1]
            for y in range(8)
            for x in range(8)
        ]

        value = sum(
            int(bit) << i
            for i, bit in enumerate(bits)
        )

        hashes.append(
            f"{value:016x}"
        )

    return hashes


def duplicate(item, previous):
    for old in previous:

        if (
            item["source_id"]
            == old["source_id"]
            or item["sha256"]
            == old["sha256"]
        ):
            return True

        a = item[
            "fingerprints"
        ]

        b = old[
            "fingerprints"
        ]

        if a and b:
            shorter, longer = sorted(
                (a, b),
                key=len,
            )

            matches = sum(
                any(
                    (
                        int(x, 16)
                        ^ int(y, 16)
                    ).bit_count()
                    <= 5
                    for y in longer
                )
                for x in shorter
            )

            if (
                matches
                / len(shorter)
                >= 0.85
            ):
                return True

    return False


# ============================================================
# STATE
# ============================================================

def load_state():
    data = read_json(
        STATE
    )

    if (
        data.get("schema") != 1
        or not isinstance(
            data.get("days"),
            dict,
        )
    ):
        raise ValueError(
            "Ungültige Historie; "
            "aus Git wiederherstellen"
        )

    for day, batch in data[
        "days"
    ].items():

        date.fromisoformat(day)

        if (
            not isinstance(
                batch,
                list,
            )
            or len(batch) != 2
        ):
            raise ValueError(
                "Unvollständige "
                "Tagesreservierung"
            )

        for item in batch:

            for key in (
                "source_id",
                "sha256",
                "fingerprints",
                "duration",
                "hook",
                "variant",
                "slot",
            ):
                if key not in item:
                    raise ValueError(
                        "Historieneintrag "
                        "beschädigt"
                    )

    return data


def prepare(day):
    state = load_state()

    if day in state["days"]:
        print(
            "Vorhandener Tagesplan "
            "bleibt unverändert:",
            day,
        )
        return

    previous = [
        item
        for batch
        in state["days"].values()
        for item in batch
    ]

    chosen = []
    errors = []

    for sid in CATALOG:

        if any(
            item["source_id"] == sid
            for item in previous
        ):
            continue

        try:
            path = source_file(
                sid
            )

            duration, _, _ = probe(
                path
            )

            item = {
                "source_id": sid,
                "sha256": digest(path),
                "duration": duration,
                "fingerprints": (
                    fingerprints(path)
                ),
                **CATALOG[sid],
            }

            if duplicate(
                item,
                previous + chosen,
            ):
                errors.append(
                    sid
                    + ": ähnliches Material "
                    "bereits reserviert"
                )

                continue

            variant = (
                "A",
                "B",
            )[
                (
                    len(state["days"])
                    + len(chosen)
                ) % 2
            ]

            item.update(
                variant=variant,
                slot=(
                    "17:30",
                    "20:30",
                )[len(chosen)],
            )

            chosen.append(
                item
            )

            if len(chosen) == 2:
                break

        except (
            ValueError,
            requests.RequestException,
            subprocess.CalledProcessError,
        ) as error:

            errors.append(
                sid
                + ": "
                + str(error)[:200]
            )

    if len(chosen) != 2:
        raise ValueError(
            "Keine zwei neuen geeigneten "
            "Quellen. Historie bleibt "
            "erhalten. "
            + " | ".join(errors)
        )

    state[
        "days"
    ][day] = chosen

    write_json(
        STATE,
        state,
    )

    print(
        "Zwei Quellen reserviert. "
        "Noch nicht veröffentlicht "
        "oder eingereicht."
    )


# ============================================================
# ASS / TEXT
# ============================================================

def escape_ass_text(text):
    text = re.sub(
        r"[{}\r\n]",
        " ",
        str(text),
    ).strip()

    text = text.replace(
        "\\",
        r"\\",
    )

    return text


def ass_time(seconds):
    seconds = max(
        0.0,
        float(seconds),
    )

    centiseconds = int(
        round(
            seconds * 100
        )
    )

    hours, remainder = divmod(
        centiseconds,
        360000,
    )

    minutes, remainder = divmod(
        remainder,
        6000,
    )

    secs, cs = divmod(
        remainder,
        100,
    )

    return (
        f"{hours}:"
        f"{minutes:02d}:"
        f"{secs:02d}."
        f"{cs:02d}"
    )


def ass_hook_text(text):
    text = escape_ass_text(
        text
    )

    lines = textwrap.wrap(
        text,
        width=24,
        break_long_words=False,
    )

    if len(lines) > 2:
        lines = textwrap.wrap(
            text,
            width=29,
            break_long_words=False,
        )

    if len(lines) > 2:
        raise ValueError(
            "Hook zu lang für "
            "zwei sichere TikTok-Zeilen"
        )

    longest = max(
        (
            len(line)
            for line in lines
        ),
        default=0,
    )

    if longest <= 20:
        size = 72

    elif longest <= 25:
        size = 66

    else:
        size = 60

    return (
        rf"{{\fs{size}}}"
        + r"\N".join(lines)
    )


def subtitle_dialogues(events):
    lines = []

    for event in events:

        text = escape_ass_text(
            event["text"]
        )

        if not text:
            continue

        lines.append(
            "Dialogue: 0,"
            + ass_time(
                event["start"]
            )
            + ","
            + ass_time(
                event["end"]
            )
            + ",Subtitle,,0,0,0,,"
            + text
        )

    return lines


# ============================================================
# VIDEO-RENDER
# ============================================================

def render_one(
    item,
    folder,
    index,
):
    # Wichtig:
    # Bereits gespeicherte State-Einträge können
    # alte Hook-Texte besitzen.
    #
    # Deshalb werden Hook/Creator/Topic immer aus
    # dem AKTUELLEN CATALOG übernommen.
    item = {
        **item,
        **CATALOG[
            item["source_id"]
        ],
    }

    path = source_file(
        item["source_id"]
    )

    if (
        digest(path)
        != item["sha256"]
    ):
        raise ValueError(
            "Quelle seit Reservierung "
            "verändert"
        )

    duration, width, height = probe(
        path
    )

    ass = (
        folder
        / "overlay.ass"
    )

    subtitle_events = (
        build_german_subtitles(
            path
        )
    )

    # --------------------------------------------------------
    # HOOK
    #
    # Weiß + fett auf rotem Hintergrund.
    # Max 2 Zeilen.
    #
    # SUBTITLES
    #
    # Weiß, fette TikTok-Schrift,
    # schwarze Outline,
    # bewusst nicht direkt am unteren Rand.
    # --------------------------------------------------------

    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Hook,DejaVu Sans,68,&H00FFFFFF,&H00FFFFFF,&H000000E8,&H000000E8,-1,0,0,0,100,100,0,0,3,12,0,8,120,120,145,1
Style: Subtitle,DejaVu Sans,54,&H00FFFFFF,&H00FFFFFF,&H00000000,&H70000000,-1,0,0,0,100,100,0,0,1,4,1,2,145,175,445,1
Style: Ad,DejaVu Sans,28,&H00FFFFFF,&H00FFFFFF,&H00181311,&H00181311,0,0,0,0,100,100,0,0,1,2,0,7,90,180,90,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    lines = [
        header.rstrip("\n"),
        (
            "Dialogue: 0,"
            "0:00:00.00,"
            f"{ass_time(duration)},"
            "Ad,,0,0,0,,Werbung"
        ),
        (
            "Dialogue: 1,"
            "0:00:00.00,"
            f"{ass_time(min(duration, 5.0))},"
            "Hook,,0,0,0,,"
            f"{ass_hook_text(item['hook'])}"
        ),
    ]

    lines.extend(
        subtitle_dialogues(
            subtitle_events
        )
    )

    ass.write_text(
        "\n".join(lines)
        + "\n",
        encoding="utf-8",
    )

    # --------------------------------------------------------
    # 9:16 LAYOUT
    # --------------------------------------------------------

    base = (
        "scale=1080:1120:"
        "force_original_aspect_ratio=decrease:"
        "force_divisible_by=2,"
        "setsar=1,"
        "pad=1080:1920:"
        "(ow-iw)/2:600:"
        "color=0x111318"
    )

    if (
        item["creator"]
        == "@averagejoewo"
        and width > height
    ):
        # JoeWo:
        # echtes Gameplay +
        # echte Facecam aus der Quelle.
        #
        # Nichts künstlich hinzugefügt.

        filters = (
            "[0:v]"
            "split=3"
            "[game][face][label];"

            "[game]"
            "crop="
            "trunc(ih*1080/1120/2)*2:"
            "ih:"
            "max(0\\,(iw-ow)/2-iw*0.05):"
            "0,"
            "scale=1080:1120,"
            "setsar=1,"
            "pad=1080:1920:"
            "0:600:"
            "color=0x111318"
            "[canvas];"

            "[face]"
            "crop="
            "trunc(iw*0.28/2)*2:"
            "trunc(ih*0.30/2)*2:"
            "trunc(iw*0.72/2)*2:"
            "0,"
            "scale=420:240:"
            "force_original_aspect_ratio="
            "decrease,"
            "pad=420:240:"
            "(ow-iw)/2:"
            "(oh-ih)/2:"
            "color=0x111318"
            "[cam];"

            "[label]"
            "crop="
            "trunc(iw*0.16/2)*2:"
            "trunc(ih*0.10/2)*2:"
            "0:0,"
            "scale=240:-2"
            "[tag];"

            "[canvas][cam]"
            "overlay="
            "300:350:"
            "shortest=1"
            "[withcam];"

            "[withcam][tag]"
            "overlay="
            "80:620:"
            "shortest=1,"
            "ass=overlay.ass"
            "[v]"
        )

    else:
        filters = (
            f"[0:v]{base},"
            "ass=overlay.ass"
            "[v]"
        )

    video = (
        folder
        / "video.mp4"
    )

    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",

            "-i",
            str(path),

            "-filter_complex",
            filters,

            "-map",
            "[v]",

            "-map",
            "0:a:0",

            "-c:v",
            "libx264",

            "-preset",
            "fast",

            "-crf",
            "20",

            "-pix_fmt",
            "yuv420p",

            "-threads",
            "2",

            "-filter_complex_threads",
            "1",

            "-c:a",
            "aac",

            "-b:a",
            "192k",

            "-movflags",
            "+faststart",

            str(video),
        ],
        cwd=folder,
        check=True,
    )

    (
        rendered_duration,
        rw,
        rh,
    ) = probe(video)

    if (
        (rw, rh)
        != (1080, 1920)
        or abs(
            rendered_duration
            - duration
        ) > 0.3
    ):
        raise ValueError(
            "Renderprüfung fehlgeschlagen"
        )

    command(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            video,
            "-f",
            "null",
            "-",
        ]
    )

    # ========================================================
    # CAPTION
    # ========================================================

    creator_part = (
        item["creator"]
        if item["creator"]
        else ""
    )

    caption = (
        "Werbung · "
        "#Ad "
        f"{item['hook']} "
        "@callofdutyde "
        f"{creator_part} "
        "#MW4 "
        "#CallOfDuty"
    )

    caption = " ".join(
        caption.split()
    )

    hashtags = re.findall(
        r"#\w+",
        caption,
    )

    if (
        not hashtags
        or hashtags[0]
        != "#Ad"
        or "@callofdutyde"
        not in caption
    ):
        raise ValueError(
            "Pflichtangaben fehlen"
        )

    if (
        item["creator"]
        and item["creator"]
        not in caption
    ):
        raise ValueError(
            "Creator-Tag fehlt"
        )

    (
        folder
        / "caption.txt"
    ).write_text(
        caption + "\n",
        encoding="utf-8",
    )

    # ========================================================
    # METADATA
    # ========================================================

    write_json(
        folder
        / "metadata.json",
        {
            "status": (
                "NEEDS_HUMAN_REVIEW"
            ),

            "automatic_publish": False,

            "campaign_id": CAMPAIGN,

            "rules_url": RULES,

            "rules_checked_on": (
                "2026-09-06"
            ),

            "source_url": (
                "https://drive.google.com/"
                "file/d/"
                f"{item['source_id']}/view"
            ),

            "source_sha256": (
                item["sha256"]
            ),

            "video_sha256": (
                digest(video)
            ),

            "variant": (
                item["variant"]
            ),

            "topic": (
                item["topic"]
            ),

            "hook": (
                item["hook"]
            ),

            "suggested_time": (
                item["slot"]
            ),

            "timezone": (
                "Europe/Berlin"
            ),

            "duration": (
                rendered_duration
            ),

            "source_audio_only": True,

            "speech_subtitles": (
                "german_auto_translated"
                if subtitle_events
                else "none_detected"
            ),

            "speech_subtitle_chunks": (
                len(
                    subtitle_events
                )
            ),

            "layout": (
                "joe_split_check_side_action"
                if (
                    item["creator"]
                    == "@averagejoewo"
                    and width > height
                )
                else "full_frame"
            ),

            "automatic_checks": [
                "source_allowlist",
                "source_hash",
                "duration",
                "1080x1920",
                "audio_present",
                "full_decode",
                "caption_tags",
                "subtitle_safe_zone",
                "hook_safe_zone",
                "duplicate_heuristic",
            ],

            "human_checks": CHECKS,

            "qualified_views": None,

            "validated_payout_usd": None,

            "withdrawable_usd": None,

            "paid_usd": None,

            "post_url": None,

            "submission_id": None,
        },
    )

    ass.unlink(
        missing_ok=True
    )


# ============================================================
# TAGESPAKET
# ============================================================

def render(day):
    state = load_state()

    if day not in state["days"]:
        raise ValueError(
            "Für diesen Tag wurde noch "
            "keine Quelle reserviert"
        )

    batch = state[
        "days"
    ][day]

    folder = (
        OUTPUT
        / day
    )

    # Bei erneutem Run keine alten Dateien
    # mitnehmen.
    if folder.exists():
        shutil.rmtree(
            folder
        )

    folder.mkdir(
        parents=True,
        exist_ok=True,
    )

    for index, item in enumerate(
        batch,
        1,
    ):
        target = (
            folder
            / (
                f"{index:02d}_"
                f"{item['variant']}"
            )
        )

        target.mkdir(
            parents=True,
            exist_ok=True,
        )

        render_one(
            item,
            target,
            index,
        )

    (
        folder
        / "VOR_DEM_POSTEN.txt"
    ).write_text(
        (
            "ENTWÜRFE: "
            "keine automatische Freigabe."
            "\n\n"
        )
        +
        "\n".join(
            "[ ] " + item
            for item in CHECKS
        )
        +
        (
            "\n\n"
            "2.000 Views sind die "
            "Review-Schwelle: NICHT bis "
            "dahin mit der Submission warten."
            "\n"
            "Zeiten sind Empfehlungen."
            "\n"
            "Fehlende Analytics und "
            "Payouts bleiben unbekannt."
            "\n"
        ),
        encoding="utf-8",
    )

    fields = [
        "post_id",
        "post_url",
        "published_at",
        "submission_id",
        "submitted_at",
        "variant",
        "topic",
        "duration_s",
        "views_1h",
        "views_6h",
        "views_24h",
        "views_72h",
        "views_7d",
        "average_watch_s",
        "completion_rate",
        "likes",
        "comments",
        "shares",
        "follows",
        "de_at_ch_lu_percent",
        "campaign_status",
        "qualified_views",
        "validated_usd",
        "withdrawable_usd",
        "paid_usd",
        "fees_usd",
        "costs_usd",
        "manual_minutes",
    ]

    with (
        folder
        / "metrics.csv"
    ).open(
        "w",
        newline="",
        encoding="utf-8",
    ) as stream:

        writer = csv.DictWriter(
            stream,
            fieldnames=fields,
        )

        writer.writeheader()

        for index, item in enumerate(
            batch,
            1,
        ):
            current = {
                **item,
                **CATALOG[
                    item["source_id"]
                ],
            }

            writer.writerow(
                {
                    "post_id": (
                        f"{day}_{index:02d}"
                    ),
                    "variant": (
                        current["variant"]
                    ),
                    "topic": (
                        current["topic"]
                    ),
                    "duration_s": (
                        current["duration"]
                    ),
                    "campaign_status": (
                        "NOT_POSTED"
                    ),
                }
            )

    archive = (
        OUTPUT
        / f"MW4_{day}.zip"
    )

    with zipfile.ZipFile(
        archive,
        "w",
        zipfile.ZIP_DEFLATED,
    ) as bundle:

        for path in sorted(
            folder.rglob("*")
        ):
            if path.is_file():

                info = zipfile.ZipInfo(
                    str(
                        path.relative_to(
                            folder
                        )
                    ),
                    (
                        2026,
                        1,
                        1,
                        0,
                        0,
                        0,
                    ),
                )

                info.compress_type = (
                    zipfile.ZIP_DEFLATED
                )

                bundle.writestr(
                    info,
                    path.read_bytes(),
                )

    print(
        "Zwei Entwürfe gerendert:",
        archive,
    )


# ============================================================
# GOOGLE DRIVE OUTPUT
# ============================================================

def _drive_query_escape(value):
    return (
        value
        .replace(
            "\\",
            "\\\\",
        )
        .replace(
            "'",
            "\\'",
        )
    )


def _drive_find_by_name(
    headers,
    folder_id,
    name,
):
    response = requests.get(
        DRIVE,
        headers=headers,
        params={
            "q": (
                f"'{folder_id}' "
                "in parents "
                "and trashed=false "
                "and name='"
                f"{_drive_query_escape(name)}"
                "'"
            ),
            "fields": (
                "files("
                "id,"
                "name,"
                "md5Checksum"
                ")"
            ),
            "pageSize": 100,
        },
        timeout=60,
    )

    response.raise_for_status()

    return (
        response
        .json()
        .get(
            "files",
            [],
        )
    )


def _drive_upload_or_update(
    headers,
    folder_id,
    path,
    name,
    mime_type,
):
    path = Path(
        path
    )

    if not path.is_file():
        raise ValueError(
            f"Drive-Datei fehlt: {path}"
        )

    existing = (
        _drive_find_by_name(
            headers,
            folder_id,
            name,
        )
    )

    local_md5 = digest(
        path,
        "md5",
    )

    if len(existing) > 1:
        raise ValueError(
            "Mehrere Drive-Dateien "
            "mit gleichem Namen: "
            + name
        )

    if (
        existing
        and existing[0].get(
            "md5Checksum"
        ) == local_md5
    ):
        print(
            "Drive bereits aktuell:",
            name,
        )

        return existing[
            0
        ]["id"]

    metadata = {
        "name": name
    }

    if not existing:
        metadata[
            "parents"
        ] = [
            folder_id
        ]

    with path.open(
        "rb"
    ) as stream:

        multipart = {
            "metadata": (
                None,
                json.dumps(
                    metadata
                ),
                (
                    "application/json; "
                    "charset=UTF-8"
                ),
            ),

            "file": (
                name,
                stream,
                mime_type,
            ),
        }

        if existing:
            response = requests.patch(
                (
                    "https://www.googleapis.com/"
                    "upload/drive/v3/files/"
                    + existing[0]["id"]
                ),
                headers=headers,
                params={
                    "uploadType": "multipart",
                    "fields": (
                        "id,md5Checksum"
                    ),
                },
                files=multipart,
                timeout=360,
            )

        else:
            response = requests.post(
                (
                    "https://www.googleapis.com/"
                    "upload/drive/v3/files"
                ),
                headers=headers,
                params={
                    "uploadType": "multipart",
                    "fields": (
                        "id,md5Checksum"
                    ),
                },
                files=multipart,
                timeout=360,
            )

    response.raise_for_status()

    payload = response.json()

    remote_md5 = payload.get(
        "md5Checksum"
    )

    if (
        remote_md5
        and remote_md5
        != local_md5
    ):
        raise ValueError(
            "Drive-Prüfsumme "
            "stimmt nicht: "
            + name
        )

    print(
        "Drive OK:",
        name,
    )

    return payload["id"]


def upload(day):
    folder_id = (
        os.environ.get(
            "MW4_DRIVE_FOLDER_ID",
            "",
        )
        .strip()
    )

    if not folder_id:
        raise ValueError(
            "MW4_DRIVE_FOLDER_ID fehlt. "
            "Die zwei fertigen Videos "
            "sollen zwingend im "
            "MW4-Drive-Ordner landen."
        )

    if not re.fullmatch(
        r"[A-Za-z0-9_-]+",
        folder_id,
    ):
        raise ValueError(
            "Ungültige Drive-Ordner-ID"
        )

    folder = (
        OUTPUT
        / day
    )

    if not folder.exists():
        raise ValueError(
            "Tagesausgabe fehlt"
        )

    headers = {
        "Authorization": (
            "Bearer "
            + token()
        )
    }

    state = load_state()

    if day not in state["days"]:
        raise ValueError(
            "Tagesreservierung fehlt"
        )

    batch = state[
        "days"
    ][day]

    for index, item in enumerate(
        batch,
        1,
    ):
        source = (
            folder
            / (
                f"{index:02d}_"
                f"{item['variant']}"
            )
        )

        slot = (
            item["slot"]
            .replace(
                ":",
                "",
            )
        )

        stem = (
            f"MW4_{day}_"
            f"{slot}_"
            f"{item['variant']}"
        )

        _drive_upload_or_update(
            headers,
            folder_id,
            source
            / "video.mp4",
            stem
            + ".mp4",
            "video/mp4",
        )

        _drive_upload_or_update(
            headers,
            folder_id,
            source
            / "caption.txt",
            stem
            + "_CAPTION.txt",
            "text/plain",
        )

        _drive_upload_or_update(
            headers,
            folder_id,
            source
            / "metadata.json",
            stem
            + "_METADATA.json",
            "application/json",
        )

    _drive_upload_or_update(
        headers,
        folder_id,
        folder
        / "VOR_DEM_POSTEN.txt",
        (
            f"MW4_{day}_"
            "VOR_DEM_POSTEN.txt"
        ),
        "text/plain",
    )

    print(
        "Zwei fertige MW4-Videos "
        "+ Postingdateien im "
        "Drive-Ordner verifiziert."
    )


# ============================================================
# MAIN
# ============================================================

def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "action",
        choices=[
            "prepare",
            "render",
            "upload",
        ],
    )

    parser.add_argument(
        "--day",
        default=(
            datetime.now(
                ZoneInfo(
                    "Europe/Berlin"
                )
            )
            .date()
            .isoformat()
        ),
    )

    args = parser.parse_args()

    date.fromisoformat(
        args.day
    )

    globals()[
        args.action
    ](
        args.day
    )


if __name__ == "__main__":
    main()