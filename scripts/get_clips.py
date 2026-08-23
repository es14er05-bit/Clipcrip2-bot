import os, json, datetime, requests

CLIENT_ID = os.environ["TWITCH_CLIENT_ID"]
CLIENT_SECRET = os.environ["TWITCH_CLIENT_SECRET"]
BROADCASTER_LOGIN = "jussef"  # <-- HIER Jussefs genauen Twitch-Namen eintragen (aus twitch.tv/NAME)
ANZAHL_CLIPS = 10
USED_FILE = "used_clips.json"

def get_token():
    r = requests.post("https://id.twitch.tv/oauth2/token", data={
        "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET,
        "grant_type": "client_credentials"})
    r.raise_for_status()
    return r.json()["access_token"]

def get_broadcaster_id(token):
    h = {"Client-Id": CLIENT_ID, "Authorization": f"Bearer {token}"}
    r = requests.get("https://api.twitch.tv/helix/users",
                      params={"login": BROADCASTER_LOGIN}, headers=h)
    r.raise_for_status()
    data = r.json()["data"]
    if not data:
        raise SystemExit(f"Twitch-User '{BROADCASTER_LOGIN}' nicht gefunden!")
    return data[0]["id"]

def get_top_clips(token, bid):
    h = {"Client-Id": CLIENT_ID, "Authorization": f"Bearer {token}"}
    since = (datetime.datetime.utcnow() - datetime.timedelta(hours=24)).isoformat("T") + "Z"
    r = requests.get("https://api.twitch.tv/helix/clips", headers=h,
                      params={"broadcaster_id": bid, "started_at": since, "first": 30})
    r.raise_for_status()
    return r.json()["data"]

def load_used():
    if os.path.exists(USED_FILE):
        return set(json.load(open(USED_FILE)))
    return set()

def main():
    token = get_token()
    bid = get_broadcaster_id(token)
    clips = get_top_clips(token, bid)
    used = load_used()

    auswahl = []
    for c in clips:
        if c["id"] in used or c["duration"] < 5:
            continue
        download_url = c["thumbnail_url"].split("-preview-")[0] + ".mp4"
        auswahl.append({"id": c["id"], "title": c["title"], "url": c["url"],
                         "view_count": c["view_count"], "download_url": download_url})
        if len(auswahl) >= ANZAHL_CLIPS:
            break

    json.dump(auswahl, open("clips_today.json", "w"), indent=2, ensure_ascii=False)
    print(f"{len(auswahl)} neue Clips ausgewählt.")

if __name__ == "__main__":
    main()
