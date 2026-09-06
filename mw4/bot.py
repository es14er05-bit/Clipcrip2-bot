"""MW4: two review packages; never posts, submits, or claims earned money."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import subprocess
import textwrap
import zipfile
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

ROOT = Path(__file__).resolve().parent
STATE = ROOT / "state/mw4.json"
CACHE = ROOT / "cache"
OUTPUT = ROOT / "output"
CAMPAIGN = "2432b187-415b-437c-9545-8cfa032a6155"
RULES = "https://docs.google.com/document/d/1greWI_Iav9EvWzPMUUSczDBJsd_VgYOagYUmu6CjEow/edit"
DRIVE = "https://www.googleapis.com/drive/v3/files"

# Exact IDs from the campaign's authorized source folders, checked 2026-09-06.
# Whole source clips only. No harvesting of a creator's other uploads.
SOURCES = [
    ("1ikTpY_xctEHa9iSuFakTvTEVkIOAVfiv", "Pistole", "Nur 'ne Pistole - schau genau hin"),
    ("1Pbm7v5qE-SyDA5e9aeL7mH61ViW2JfAU", "Sniper", "Achte auf den nächsten Treffer"),
    ("1F9cCbVztPUP7sBiWVnpLescRPdyMqqTr", "Movement", "Achte mal auf seinen Laufweg"),
    ("1MQKZmzlRTz_Xoi5ZGHSfnQ54d9r0lvtB", "Spielzug", "Und dann kommt noch einer"),
    ("11T2_z_-6l6CNJ83OFaEvO4HSU18OmIII", "Spielzug", "Was er hier noch rausholt"),
    ("1eRzChBSJSTH_uGhm9QpkOrQsaRRYo8Av", "Waffenwechsel", "Achte auf den Waffenwechsel"),
    ("1B8QHC8-DS25Z4Tj5U0LhlzSRmi1KQAou", "Spielzug", "Der nächste Gegner wartet schon"),
    ("1_gpXpqmyqns5gGvSQ0rGP5Ip1dCxB7qP", "Movement", "So kommt er um die Ecke"),
    ("19tId1rMDiR5zfWLWv1FpYmuC1CGw0xRV", "Spielzug", "Bis zum letzten Gegner"),
    ("10lvHQPyLU9SVb3IepPWk1oVGRDfCiEc0", "Kulissen", "Ein Blick hinter die MW4-Kulissen"),
]

CATALOG = {
    sid: {
        "topic": topic,
        "hook": hook,
        "creator": "" if topic == "Kulissen" else "@averagejoewo",
    }
    for sid, topic, hook in SOURCES
}

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
        "hook": "Schau dir diesen MW4-Moment an",
        "creator": creator,
    }

CHECKS = [
    "Aktiver Kampagnenstatus, Restbudget und aktuelle Regeln selbst geprüft",
    "Vollständiges Video angesehen: Aussage korrekt, positiv, keine Spielevergleiche",
    "Alle sichtbaren Texte deutsch bzw. zulässige unveränderte Quelltexte geklärt",
    "Keine fremden Logos, Musik, Beleidigungen oder problematischen Szenen",
    "Creator-Gesicht und ursprüngliche Entwicklungs-/ALPHA-Hinweise sichtbar",
    "Caption korrekt; @callofdutyde und gegebenenfalls Creator als echte Tags gewählt",
    "Native TikTok-Werbekennzeichnung für eine andere Marke aktiviert",
    "Öffentlich; Likes/Kommentare aktiviert und Zahlen sichtbar",
    "Post noch nicht veröffentlicht oder eingereicht; keine externe Promotion",
    "Nach Posting sofort einreichen; Livefrist prüfen, vorsorglich unter 30 Minuten",
    "Später mindestens 2000 Views und DE+AT+CH+LU >= 30 Prozent nachweisen",
]


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def digest(path, algorithm="sha256"):
    h = hashlib.new(algorithm)
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
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
        command([
            "ffprobe", "-v", "error",
            "-show_streams", "-show_format",
            "-of", "json", path,
        ])
    )
    video = next(
        s for s in data["streams"] if s["codec_type"] == "video"
    )
    if not any(s["codec_type"] == "audio" for s in data["streams"]):
        raise ValueError("Originalaudio fehlt")

    duration = float(data["format"]["duration"])
    if not 10 <= duration <= 45:
        raise ValueError(
            "Länge außerhalb 10-45 s; 45 s ist unser Produktionslimit"
        )
    return duration, int(video["width"]), int(video["height"])


def token():
    names = (
        "GOOGLE_CLIENT_ID",
        "GOOGLE_CLIENT_SECRET",
        "GOOGLE_REFRESH_TOKEN",
    )
    if not all(os.environ.get(n) for n in names):
        raise ValueError(
            "Google-Secrets fehlen; alternativ Originaldateien "
            "unter cache/DATEI_ID.mp4 ablegen"
        )

    response = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": os.environ[names[0]],
            "client_secret": os.environ[names[1]],
            "refresh_token": os.environ[names[2]],
            "grant_type": "refresh_token",
        },
        timeout=60,
    )
    if response.status_code != 200:
        raise ValueError(
            f"Google OAuth fehlgeschlagen (HTTP {response.status_code}); "
            "Secrets/Berechtigung prüfen"
        )
    return response.json()["access_token"]


def source_file(sid):
    if sid not in CATALOG:
        raise ValueError("Nicht freigegebene Quellen-ID")

    CACHE.mkdir(exist_ok=True)
    path = CACHE / f"{sid}.mp4"

    if path.exists():
        probe(path)
        return path

    headers = {"Authorization": "Bearer " + token()}
    meta = requests.get(
        f"{DRIVE}/{sid}",
        headers=headers,
        params={
            "fields": "mimeType,md5Checksum,capabilities(canDownload)"
        },
        timeout=60,
    )
    if meta.status_code != 200:
        raise ValueError(
            f"Quellenzugriff HTTP {meta.status_code}; "
            "Drive-Leseberechtigung erforderlich"
        )

    meta = meta.json()
    if (
        not meta.get("capabilities", {}).get("canDownload")
        or not meta.get("mimeType", "").startswith("video/")
    ):
        raise ValueError("Kein erlaubter Videodownload")

    tmp = path.with_suffix(".part")
    with requests.get(
        f"{DRIVE}/{sid}",
        headers=headers,
        params={"alt": "media"},
        timeout=120,
        stream=True,
    ) as response:
        response.raise_for_status()
        with tmp.open("wb") as stream:
            for chunk in response.iter_content(1024 * 1024):
                stream.write(chunk)

    if meta.get("md5Checksum") != digest(tmp, "md5"):
        tmp.unlink(missing_ok=True)
        raise ValueError("Download-Prüfsumme stimmt nicht")

    probe(tmp)
    tmp.replace(path)
    return path


def fingerprints(path):
    # Sample 1 frame/second; dHash tolerates encoding differences.
    # Heuristic only.
    raw = command([
        "ffmpeg", "-v", "error",
        "-i", path,
        "-vf", "fps=1,scale=9:8,format=gray",
        "-f", "rawvideo",
        "-pix_fmt", "gray",
        "-",
    ])

    hashes = []
    for offset in range(0, len(raw) - 71, 72):
        frame = raw[offset:offset + 72]
        bits = [
            frame[y * 9 + x] > frame[y * 9 + x + 1]
            for y in range(8)
            for x in range(8)
        ]
        value = sum(int(bit) << i for i, bit in enumerate(bits))
        hashes.append(f"{value:016x}")
    return hashes


def duplicate(item, previous):
    for old in previous:
        if (
            item["source_id"] == old["source_id"]
            or item["sha256"] == old["sha256"]
        ):
            return True

        a, b = item["fingerprints"], old["fingerprints"]
        if a and b:
            shorter, longer = sorted((a, b), key=len)
            matches = sum(
                any(
                    (int(x, 16) ^ int(y, 16)).bit_count() <= 5
                    for y in longer
                )
                for x in shorter
            )
            if matches / len(shorter) >= 0.85:
                return True
    return False


def load_state():
    # Never silently reset a missing or corrupt history.
    data = read_json(STATE)
    if data.get("schema") != 1 or not isinstance(data.get("days"), dict):
        raise ValueError("Ungültige Historie; aus Git wiederherstellen")

    for day, batch in data["days"].items():
        date.fromisoformat(day)
        if not isinstance(batch, list) or len(batch) != 2:
            raise ValueError("Unvollständige Tagesreservierung")

        for item in batch:
            for key in (
                "source_id", "sha256", "fingerprints",
                "duration", "hook", "variant", "slot",
            ):
                if key not in item:
                    raise ValueError("Historieneintrag beschädigt")
    return data


def prepare(day):
    state = load_state()
    if day in state["days"]:
        print("Vorhandener Tagesplan bleibt unverändert:", day)
        return

    previous = [
        item
        for batch in state["days"].values()
        for item in batch
    ]
    chosen = []
    errors = []

    for sid in CATALOG:
        if any(item["source_id"] == sid for item in previous):
            continue

        try:
            path = source_file(sid)
            duration, _, _ = probe(path)
            item = {
                "source_id": sid,
                "sha256": digest(path),
                "duration": duration,
                "fingerprints": fingerprints(path),
                **CATALOG[sid],
            }

            if duplicate(item, previous + chosen):
                errors.append(
                    sid + ": ähnliches Material bereits reserviert"
                )
                continue

            variant = ("A", "B")[
                (len(state["days"]) + len(chosen)) % 2
            ]
            item.update(
                variant=variant,
                slot=("17:30", "20:30")[len(chosen)],
            )

            if variant == "B":
                item["hook"] = "Was fällt dir an dieser Szene auf?"

            chosen.append(item)
            if len(chosen) == 2:
                break

        except (
            ValueError,
            requests.RequestException,
            subprocess.CalledProcessError,
        ) as error:
            errors.append(sid + ": " + str(error)[:200])

    if len(chosen) != 2:
        raise ValueError(
            "Keine zwei neuen geeigneten Quellen. "
            "Historie bleibt erhalten. " + " | ".join(errors)
        )

    state["days"][day] = chosen
    write_json(STATE, state)
    print(
        "Zwei Quellen reserviert. "
        "Noch nicht veröffentlicht oder eingereicht."
    )


def ass_text(text):
    text = re.sub(r"[{}\\\r\n]", " ", text).strip()
    lines = textwrap.wrap(text, width=27)
    if len(lines) > 2:
        raise ValueError("Hook zu lang für zwei Zeilen")
    return r"\N".join(lines)


def render_one(item, folder, index):
    path = source_file(item["source_id"])
    if digest(path) != item["sha256"]:
        raise ValueError("Quelle seit Reservierung verändert")

    duration, width, height = probe(path)
    ass = folder / "overlay.ass"

    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Hook,DejaVu Sans,54,&H00FFFFFF,&H00FFFFFF,&H00181311,&H00181311,-1,0,0,0,100,100,0,0,1,3,0,8,100,180,220,1
Style: Ad,DejaVu Sans,30,&H00FFFFFF,&H00FFFFFF,&H00181311,&H00181311,0,0,0,0,100,100,0,0,1,2,0,7,100,180,160,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ass.write_text(
        header
        + "Dialogue: 0,0:00:00.00,0:01:00.00,Ad,,0,0,0,,Werbung\n"
        + "Dialogue: 0,0:00:00.00,0:01:00.00,Hook,,0,0,0,,"
        + ass_text(item["hook"])
        + "\n",
        encoding="utf-8",
    )

    # Unknown layouts keep the entire frame.
    # JoeWo has an inspected split layout.
    base = (
        "scale=1080:1120:"
        "force_original_aspect_ratio=decrease:"
        "force_divisible_by=2,"
        "setsar=1,"
        "pad=1080:1920:(ow-iw)/2:600:color=0x111318"
    )

    if item["creator"] == "@averagejoewo" and width > height:
        # Reuse the actual facecam and top-left source label.
        # Never synthesize them.
        filters = (
            "[0:v]split=3[game][face][label];"
            "[game]crop=trunc(ih*1080/1120/2)*2:"
            "ih:max(0\\,(iw-ow)/2-iw*0.05):0,"
            "scale=1080:1120,setsar=1,"
            "pad=1080:1920:0:600:color=0x111318[canvas];"
            "[face]crop=trunc(iw*0.28/2)*2:"
            "trunc(ih*0.30/2)*2:"
            "trunc(iw*0.72/2)*2:0,"
            "scale=420:240:force_original_aspect_ratio=decrease,"
            "pad=420:240:(ow-iw)/2:(oh-ih)/2:"
            "color=0x111318[cam];"
            "[label]crop=trunc(iw*0.16/2)*2:"
            "trunc(ih*0.10/2)*2:0:0,"
            "scale=240:-2[tag];"
            "[canvas][cam]overlay=300:350:shortest=1[withcam];"
            "[withcam][tag]overlay=80:620:shortest=1,"
            "ass=overlay.ass[v]"
        )
    else:
        filters = f"[0:v]{base},ass=overlay.ass[v]"

    video = folder / "video.mp4"

    subprocess.run(
        [
            "ffmpeg", "-v", "error", "-y",
            "-i", str(path),
            "-filter_complex", filters,
            "-map", "[v]",
            "-map", "0:a:0",
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "20",
            "-pix_fmt", "yuv420p",
            "-threads", "2",
            "-filter_complex_threads", "1",
            "-c:a", "aac",
            "-b:a", "192k",
            "-movflags", "+faststart",
            str(video),
        ],
        cwd=folder,
        check=True,
    )

    rendered_duration, rw, rh = probe(video)
    if (
        (rw, rh) != (1080, 1920)
        or abs(rendered_duration - duration) > 0.3
    ):
        raise ValueError("Renderprüfung fehlgeschlagen")

    command([
        "ffmpeg", "-v", "error",
        "-i", video,
        "-f", "null", "-",
    ])

    caption = (
        f"Werbung · #Ad {item['hook']} "
        f"@callofdutyde {item['creator']} #MW4 #CallOfDuty"
    )
    caption = " ".join(caption.split())

    if (
        re.findall(r"#\w+", caption)[0] != "#Ad"
        or "@callofdutyde" not in caption
    ):
        raise ValueError("Pflichtangaben fehlen")

    (folder / "caption.txt").write_text(
        caption + "\n",
        encoding="utf-8",
    )

    write_json(
        folder / "metadata.json",
        {
            "status": "NEEDS_HUMAN_REVIEW",
            "automatic_publish": False,
            "campaign_id": CAMPAIGN,
            "rules_url": RULES,
            "rules_checked_on": "2026-09-06",
            "source_url": (
                "https://drive.google.com/file/d/"
                f"{item['source_id']}/view"
            ),
            "source_sha256": item["sha256"],
            "video_sha256": digest(video),
            "variant": item["variant"],
            "topic": item["topic"],
            "suggested_time": item["slot"],
            "timezone": "Europe/Berlin",
            "duration": rendered_duration,
            "source_audio_only": True,
            "speech_subtitles": "not_generated",
            "layout": (
                "joe_split_check_side_action"
                if item["creator"] == "@averagejoewo" and width > height
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

    ass.unlink()


def render(day):
    batch = load_state()["days"][day]
    folder = OUTPUT / day
    folder.mkdir(parents=True, exist_ok=True)

    for index, item in enumerate(batch, 1):
        target = folder / f"{index:02d}_{item['variant']}"
        target.mkdir(exist_ok=True)
        render_one(item, target, index)

    (folder / "VOR_DEM_POSTEN.txt").write_text(
        "ENTWÜRFE: keine automatische Freigabe.\n\n"
        + "\n".join("[ ] " + x for x in CHECKS)
        + "\n\n2.000 Views sind die Review-Schwelle: "
        "NICHT bis dahin mit der Submission warten.\n"
        + "Zeiten sind Empfehlungen. "
        "Fehlende Analytics und Payouts bleiben unbekannt.\n",
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

    with (folder / "metrics.csv").open(
        "w", newline="", encoding="utf-8"
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()

        for index, item in enumerate(batch, 1):
            writer.writerow({
                "post_id": f"{day}_{index:02d}",
                "variant": item["variant"],
                "topic": item["topic"],
                "duration_s": item["duration"],
                "campaign_status": "NOT_POSTED",
            })

    archive = OUTPUT / f"MW4_{day}.zip"
    with zipfile.ZipFile(
        archive, "w", zipfile.ZIP_DEFLATED
    ) as bundle:
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                info = zipfile.ZipInfo(
                    str(path.relative_to(folder)),
                    (2026, 1, 1, 0, 0, 0),
                )
                info.compress_type = zipfile.ZIP_DEFLATED
                bundle.writestr(info, path.read_bytes())

    print("Zwei Entwürfe gerendert:", archive)


def upload(day):
    folder_id = os.environ.get("MW4_DRIVE_FOLDER_ID", "").strip()
    if not folder_id:
        print(
            "Kein Drive-Ausgabeordner gesetzt; "
            "GitHub-Artifact verwenden."
        )
        return

    if not re.fullmatch(r"[A-Za-z0-9_-]+", folder_id):
        raise ValueError("Ungültige Drive-Ordner-ID")

    archive = OUTPUT / f"MW4_{day}.zip"
    headers = {"Authorization": "Bearer " + token()}

    response = requests.get(
        DRIVE,
        headers=headers,
        params={
            "q": (
                f"'{folder_id}' in parents "
                f"and trashed=false and name='{archive.name}'"
            ),
            "fields": "files(id,md5Checksum)",
            "pageSize": 100,
        },
        timeout=60,
    )
    response.raise_for_status()
    existing = response.json().get("files", [])

    if existing:
        if (
            len(existing) == 1
            and existing[0].get("md5Checksum")
            == digest(archive, "md5")
        ):
            print("Identisches Tagespaket ist schon auf Drive.")
            return

        raise ValueError(
            "Tagespaket existiert bereits mit anderem Inhalt; "
            "nichts überschrieben"
        )

    metadata = {
        "name": archive.name,
        "parents": [folder_id],
    }

    with archive.open("rb") as stream:
        response = requests.post(
            "https://www.googleapis.com/upload/drive/v3/files",
            headers=headers,
            params={
                "uploadType": "multipart",
                "fields": "id,md5Checksum",
            },
            files={
                "metadata": (
                    None,
                    json.dumps(metadata),
                    "application/json; charset=UTF-8",
                ),
                "file": (
                    archive.name,
                    stream,
                    "application/zip",
                ),
            },
            timeout=360,
        )

    response.raise_for_status()
    if response.json().get("md5Checksum") != digest(archive, "md5"):
        raise ValueError(
            "Drive-Upload nicht verifiziert; keine Datei gelöscht"
        )

    print(
        "Tagespaket auf Drive verifiziert. "
        "Frühere Pakete bleiben erhalten."
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "action",
        choices=["prepare", "render", "upload"],
    )
    parser.add_argument(
        "--day",
        default=datetime.now(
            ZoneInfo("Europe/Berlin")
        ).date().isoformat(),
    )
    args = parser.parse_args()
    date.fromisoformat(args.day)
    globals()[args.action](args.day)


if __name__ == "__main__":
    main()