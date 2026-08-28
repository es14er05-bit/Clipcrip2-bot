"""Synchronize the current rendered batch to its dedicated Drive folder.

The folder is a current-batch inbox, not an archive. New videos are uploaded
and verified first. Only then are older video files moved to Drive's trash, so
the folder never mixes clips from multiple runs and failures keep the previous
batch recoverable.
"""

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
MAX_EXPECTED_FILES = 5


def build_session() -> requests.Session:
    retry = Retry(
        total=6,
        connect=6,
        read=6,
        status=6,
        backoff_factor=1.5,
        status_forcelist=(408, 429, 500, 502, 503, 504),
        allowed_methods=("GET", "POST", "PATCH"),
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


def list_folder_files(
    session: requests.Session, token: str, folder_id: str
) -> list[dict]:
    query = f"'{escape_query(folder_id)}' in parents and trashed=false"
    page_token = ""
    files: list[dict] = []
    while True:
        params = {
            "q": query,
            "fields": "nextPageToken,files(id,name,size,mimeType)",
            "spaces": "drive",
            "pageSize": 1000,
        }
        if page_token:
            params["pageToken"] = page_token
        response = session.get(
            f"{DRIVE_API}/files",
            headers=auth_headers(token),
            params=params,
            timeout=60,
        )
        response.raise_for_status()
        payload = response.json()
        files.extend(item for item in payload.get("files", []) if isinstance(item, dict))
        page_token = str(payload.get("nextPageToken", "")).strip()
        if not page_token:
            return files


def is_video_file(item: dict) -> bool:
    name = str(item.get("name", "")).lower()
    mime_type = str(item.get("mimeType", "")).lower()
    return name.endswith(".mp4") or mime_type.startswith("video/")


def stale_video_files(folder_files: list[dict], current_ids: set[str]) -> list[dict]:
    return [
        item
        for item in folder_files
        if is_video_file(item) and str(item.get("id", "")) not in current_ids
    ]


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


def verify_upload(session: requests.Session, token: str, file_id: str) -> dict:
    response = session.get(
        f"{DRIVE_API}/files/{file_id}",
        headers=auth_headers(token),
        params={"fields": "id,name,size,parents,trashed"},
        timeout=60,
    )
    response.raise_for_status()
    return response.json()


def trash_file(session: requests.Session, token: str, file_id: str) -> None:
    response = session.patch(
        f"{DRIVE_API}/files/{file_id}",
        headers={**auth_headers(token), "Content-Type": "application/json"},
        params={"fields": "id,trashed"},
        json={"trashed": True},
        timeout=60,
    )
    response.raise_for_status()


def main() -> None:
    output_dir = Path(os.environ.get("OUTPUT_DIR", "tiktok_ready"))
    folder_id = os.environ.get("DRIVE_FOLDER_ID", "").strip()
    if not folder_id:
        raise RuntimeError("DRIVE_FOLDER_ID fehlt.")

    files = sorted(output_dir.glob("*.mp4"))
    print(f"{len(files)} fertige Videos in {output_dir} gefunden.")
    if len(files) > MAX_EXPECTED_FILES:
        raise RuntimeError(
            f"Sicherheitsstopp: maximal {MAX_EXPECTED_FILES} Outputs erwartet, "
            f"gefunden: {len(files)}"
        )

    session = build_session()
    uploaded_ids: set[str] = set()
    try:
        token = get_access_token(session)
        try:
            for index, path in enumerate(files, start=1):
                print(f"DRIVE {index}/{len(files)} | {path.name}")
                uploaded = upload_video(session, token, folder_id, path)
                new_id = str(uploaded.get("id", "")).strip()
                if not new_id:
                    raise RuntimeError(f"Drive lieferte keine Datei-ID für {path.name}.")
                uploaded_ids.add(new_id)

                verification = verify_upload(session, token, new_id)
                if (
                    str(verification.get("id", "")) != new_id
                    or bool(verification.get("trashed", False))
                    or folder_id not in verification.get("parents", [])
                ):
                    raise RuntimeError(f"Drive-Verifikation fehlgeschlagen: {path.name}")
                print(f"UPLOAD OK | {path.name} | {new_id}")
                if index < len(files):
                    time.sleep(1.0)
        except Exception:
            print("Upload fehlgeschlagen; neue Teil-Uploads werden zurückgerollt.")
            for new_id in uploaded_ids:
                try:
                    trash_file(session, token, new_id)
                except Exception as rollback_error:
                    print(f"WARNUNG: Rollback für {new_id} fehlgeschlagen: {rollback_error}")
            raise

        folder_files = list_folder_files(session, token, folder_id)
        stale = stale_video_files(folder_files, uploaded_ids)
        print(f"Alte Videos aus früheren Runs: {len(stale)}")
        for old in stale:
            old_id = str(old.get("id", "")).strip()
            if old_id:
                trash_file(session, token, old_id)
                print(f"IN PAPIERKORB | {old.get('name', old_id)}")
    finally:
        session.close()

    print(f"Drive-Sync abgeschlossen: aktueller Batch enthält {len(files)} Videos.")


if __name__ == "__main__":
    main()
