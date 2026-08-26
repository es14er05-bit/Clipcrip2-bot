import glob
import json
import mimetypes
import os
import time
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


REPO_ROOT = Path(__file__).resolve().parents[2]
GIGGAND_ROOT = REPO_ROOT / "giggand"
OUTPUT_DIR = GIGGAND_ROOT / "tiktok_ready"

TOKEN_URL = "https://oauth2.googleapis.com/token"

DRIVE_API = (
    "https://www.googleapis.com/drive/v3"
)

DRIVE_UPLOAD_API = (
    "https://www.googleapis.com/"
    "upload/drive/v3/files"
)


def build_session():
    retry = Retry(
        total=6,
        connect=6,
        read=6,
        status=6,
        backoff_factor=2,
        status_forcelist=[
            408,
            429,
            500,
            502,
            503,
            504,
        ],
        allowed_methods=[
            "GET",
            "POST",
            "DELETE",
        ],
        raise_on_status=False,
    )

    adapter = HTTPAdapter(
        max_retries=retry
    )

    session = requests.Session()

    session.mount(
        "https://",
        adapter,
    )

    session.headers.update({
        "User-Agent":
            "ClipCrip5-Giggand-GitHub-Actions/1.0",

        "Connection":
            "close",
    })

    return session


def get_access_token(session):
    response = session.post(
        TOKEN_URL,
        data={
            "client_id":
                os.environ[
                    "GOOGLE_CLIENT_ID"
                ],

            "client_secret":
                os.environ[
                    "GOOGLE_CLIENT_SECRET"
                ],

            "refresh_token":
                os.environ[
                    "GOOGLE_REFRESH_TOKEN"
                ],

            "grant_type":
                "refresh_token",
        },
        timeout=60,
    )

    response.raise_for_status()

    data = response.json()

    token = data.get(
        "access_token"
    )

    if not token:
        raise RuntimeError(
            "Google Access Token fehlt."
        )

    return token


def auth_headers(token):
    return {
        "Authorization":
            f"Bearer {token}",
    }


def escape_drive_query_value(value):
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


def find_existing(
    session,
    token,
    folder_id,
    filename,
):
    safe_name = (
        escape_drive_query_value(
            filename
        )
    )

    query = (
        f"name='{safe_name}' "
        f"and '{folder_id}' in parents "
        "and trashed=false"
    )

    response = session.get(
        f"{DRIVE_API}/files",
        headers=auth_headers(
            token
        ),
        params={
            "q":
                query,

            "fields":
                "files(id,name,size)",

            "spaces":
                "drive",
        },
        timeout=60,
    )

    response.raise_for_status()

    return response.json().get(
        "files",
        []
    )


def upload_video(
    session,
    token,
    folder_id,
    path,
):
    filename = path.name

    mime_type = (
        mimetypes.guess_type(
            filename
        )[0]
        or "video/mp4"
    )

    metadata = {
        "name":
            filename,

        "parents":
            [folder_id],
    }

    with open(
        path,
        "rb",
    ) as video_file:

        response = session.post(
            DRIVE_UPLOAD_API,
            headers=auth_headers(
                token
            ),
            params={
                "uploadType":
                    "multipart",

                "fields":
                    "id,name,size",
            },
            files={
                "metadata": (
                    None,
                    json.dumps(
                        metadata
                    ),
                    "application/json; charset=UTF-8",
                ),

                "file": (
                    filename,
                    video_file,
                    mime_type,
                ),
            },
            timeout=300,
        )

    response.raise_for_status()

    return response.json()


def delete_file(
    session,
    token,
    file_id,
):
    response = session.delete(
        f"{DRIVE_API}/files/{file_id}",
        headers=auth_headers(
            token
        ),
        timeout=60,
    )

    if response.status_code not in (
        200,
        204,
    ):
        response.raise_for_status()


def main():
    folder_id = os.environ[
        "DRIVE_FOLDER_ID"
    ]

    files = [
        Path(path)
        for path in sorted(
            glob.glob(
                str(
                    OUTPUT_DIR
                    / "*.mp4"
                )
            )
        )
    ]

    print(
        f"{len(files)} fertige "
        "ClipCrip5 Giggand-Videos gefunden."
    )

    if len(files) != 5:
        raise RuntimeError(
            "Es müssen genau 5 fertige "
            "Giggand-MP4-Dateien vorhanden sein. "
            f"Gefunden: {len(files)}"
        )

    session = build_session()

    token = get_access_token(
        session
    )

    print(
        "Google Drive Login erfolgreich."
    )

    uploaded_count = 0

    for index, path in enumerate(
        files,
        start=1,
    ):
        filename = path.name

        print("")
        print(
            "======================================"
        )
        print(
            f"CLIPCRIP5 GIGGAND DRIVE VIDEO {index}/5"
        )
        print(
            "======================================"
        )
        print(
            f"Datei: {filename}"
        )

        existing = find_existing(
            session,
            token,
            folder_id,
            filename,
        )

        print(
            "Alte Versionen gefunden: "
            f"{len(existing)}"
        )

        uploaded = upload_video(
            session,
            token,
            folder_id,
            path,
        )

        new_id = uploaded.get(
            "id"
        )

        if not new_id:
            raise RuntimeError(
                "Drive Upload lieferte "
                "keine Datei-ID."
            )

        print(
            "Neue Version erfolgreich "
            f"hochgeladen: {filename}"
        )

        for old in existing:
            old_id = old.get(
                "id"
            )

            if (
                old_id
                and old_id != new_id
            ):
                delete_file(
                    session,
                    token,
                    old_id,
                )

                print(
                    "Alte Version gelöscht: "
                    + old_id
                )

                time.sleep(
                    0.5
                )

        uploaded_count += 1

    if uploaded_count != 5:
        raise RuntimeError(
            "Nicht alle 5 Giggand-Videos "
            "wurden hochgeladen."
        )

    print("")
    print(
        "Alle 5 ClipCrip5 Giggand-Videos "
        "erfolgreich in Google Drive gespeichert."
    )


if __name__ == "__main__":
    main()