"""Upload a variable number of rendered clips to Google Drive safely."""

from __future__ import annotations

import json
import mimetypes
import os
import time
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


TOKEN_URL = "https://oauth2.googleapis.com/token"
DRIVE_API = "https://www.googleapis.com/drive/v3"
DRIVE_UPLOAD_API = "https://www.googleapis.com/upload/drive/v3/files"
MAX_EXPECTED_FILES = 3


def build_session() -> requests.Session:
    retry = Retry(
        total=6,
        connect=6,
        read=6,
        status=6,
        backoff_factor=1.5,
        status_forcelist=(408, 429, 500, 502, 503, 504),
        allowed_methods=("GET", "POST", "DELETE"),
        raise_on_status=False,
    )
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.headers.update(
        {"User-Agent": "ClipCrip-Shared-Drive-Uploader/1.0", "Connection": "close"}
    )
    return session


def get_access_token(session: requests.Session) -> str:
    required = ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REFRESH_TOKEN")
    missing = [name for name in required if not os.environ.get(name, "").strip()]
    if missing:
        raise RuntimeError("Fehlende Google-Secrets: " + ", ".join(missing))
    response = session.post(
        TOKEN_URL,
        data={
            "client_id": os.environ["GOOGLE_CLIENT_ID"],
            "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
            "refresh_token": os.environ["GOOGLE_REFRESH_TOKEN"],
            "grant_type": "refresh_token",
        },
        timeout=60,
    )
    response.raise_for_status()
    token = str(response.json().get("access_token", "")).strip()
    if not token:
        raise RuntimeError("Google lieferte keinen Access Token.")
    return token


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def escape_query(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def find_existing(
    session: requests.Session, token: str, folder_id: str, filename: str
) -> list[dict]:
    query = (
        f"name='{escape_query(filename)}' and '{folder_id}' in parents "
        "and trashed=false"
    )
    response = session.get(
        f"{DRIVE_API}/files",
        headers=auth_headers(token),
        params={"q": query, "fields": "files(id,name,size)", "spaces": "drive"},
        timeout=60,
    )
    response.raise_for_status()
    return response.json().get("files", [])


def upload_video(
    session: requests.Session, token: str, folder_id: str, path: Path
) -> dict:
    mime_type = mimetypes.guess_type(path.name)[0] or "video/mp4"
    metadata = {"name": path.name, "parents": [folder_id]}
    with path.open("rb") as video_file:
        response = session.post(
            DRIVE_UPLOAD_API,
            headers=auth_headers(token),
            params={"uploadType": "multipart", "fields": "id,name,size"},
            files={
                "metadata": (
                    None,
                    json.dumps(metadata),
                    "application/json; charset=UTF-8",
                ),
                "file": (path.name, video_file, mime_type),
            },
            timeout=360,
        )
    response.raise_for_status()
    return response.json()


def delete_file(session: requests.Session, token: str, file_id: str) -> None:
    response = session.delete(
        f"{DRIVE_API}/files/{file_id}",
        headers=auth_headers(token),
        timeout=60,
    )
    if response.status_code not in (200, 204):
        response.raise_for_status()


def main() -> None:
    output_dir = Path(os.environ.get("OUTPUT_DIR", "tiktok_ready"))
    folder_id = os.environ.get("DRIVE_FOLDER_ID", "").strip()
    if not folder_id:
        raise RuntimeError("DRIVE_FOLDER_ID fehlt.")

    files = sorted(output_dir.glob("*.mp4"))
    print(f"{len(files)} fertige Videos in {output_dir} gefunden.")
    if not files:
        print("Kein starker Clip vorhanden. Drive-Upload wird sauber übersprungen.")
        return
    if len(files) > MAX_EXPECTED_FILES:
        raise RuntimeError(
            f"Sicherheitsstopp: maximal {MAX_EXPECTED_FILES} Outputs erwartet, "
            f"gefunden: {len(files)}"
        )

    session = build_session()
    try:
        token = get_access_token(session)
        for index, path in enumerate(files, start=1):
            print(f"DRIVE {index}/{len(files)} | {path.name}")
            existing = find_existing(session, token, folder_id, path.name)
            uploaded = upload_video(session, token, folder_id, path)
            new_id = str(uploaded.get("id", "")).strip()
            if not new_id:
                raise RuntimeError(f"Drive lieferte keine Datei-ID für {path.name}.")

            verification = find_existing(session, token, folder_id, path.name)
            if not any(str(item.get("id", "")) == new_id for item in verification):
                raise RuntimeError(f"Drive-Verifikation fehlgeschlagen: {path.name}")

            for old in existing:
                old_id = str(old.get("id", "")).strip()
                if old_id and old_id != new_id:
                    delete_file(session, token, old_id)
            print(f"UPLOAD OK | {path.name} | {new_id}")
            if index < len(files):
                time.sleep(1.0)
    finally:
        session.close()

    print(f"Drive-Upload abgeschlossen: {len(files)} Videos.")


if __name__ == "__main__":
    main()
