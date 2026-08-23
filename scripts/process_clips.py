import os, json, subprocess, requests
from faster_whisper import WhisperModel

jussef_livestream = "@jussef"  # <-- Jussefs TikTok-Hauptkanal-Name hier eintragen

os.makedirs("downloads", exist_ok=True)
os.makedirs("processed", exist_ok=True)
model = WhisperModel("base", device="cpu", compute_type="int8")

def download(url, path):
    r = requests.get(url, stream=True)
    r.raise_for_status()
    with open(path, "wb") as f:
        for chunk in r.iter_content(8192):
            f.write(chunk)

def format_ts(seconds):
    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    return f"{int(h):02}:{int(m):02}:{s:06.3f}".replace(".", ",")

def make_srt(segments, path):
    with open(path, "w", encoding="utf-8") as f:
        for i, seg in enumerate(segments, start=1):
            f.write(f"{i}\n{format_ts(seg.start)} --> {format_ts(seg.end)}\n{seg.text.strip()}\n\n")

def process_clip(clip):
    raw = f"downloads/{clip['id']}.mp4"
    vertical = f"downloads/{clip['id']}_v.mp4"
    srt = f"downloads/{clip['id']}.srt"
    final = f"processed/{clip['id']}.mp4"

    download(clip["download_url"], raw)

    subprocess.run(["ffmpeg", "-y", "-i", raw, "-vf",
                     "crop=ih*9/16:ih,scale=1080:1920", "-c:a", "copy", vertical], check=True)

    segments, _ = model.transcribe(vertical, language="de")
    make_srt(segments, srt)

    style = ("FontName=Arial Black,FontSize=16,PrimaryColour=&H00FFFFFF,"
              "OutlineColour=&H00000000,BorderStyle=1,Outline=2,Alignment=2,MarginV=80")
    subprocess.run(["ffmpeg", "-y", "-i", vertical, "-vf",
                     f"subtitles={srt}:force_style='{style}'", "-c:a", "copy", final], check=True)

    caption = f"{clip['title']} 🔥 {MAIN_CHANNEL_TAG} #jussef #twitch #clips"
    return {"id": clip["id"], "video_path": final, "caption": caption}

def main():
    clips = json.load(open("clips_today.json"))
    fertig = [process_clip(c) for c in clips]
    json.dump(fertig, open("clips_ready.json", "w"), indent=2, ensure_ascii=False)
    print(f"{len(fertig)} Clips fertig bearbeitet.")

if __name__ == "__main__":
    main()
