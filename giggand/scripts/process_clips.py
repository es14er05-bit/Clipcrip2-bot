from pathlib import Path
import importlib.util


REPO_ROOT = Path(__file__).resolve().parents[2]
GIGGAND_ROOT = REPO_ROOT / "giggand"
CORE_FILE = REPO_ROOT / "scripts" / "process_clips.py"


GIGGAND_WHISPER_PROMPT = (
    "Dies ist ein deutscher Twitch-Stream von Giggand. "
    "Die Sprecher reden locker, schnell und umgangssprachlich. "
    "Häufige Wörter und Namen können sein: "
    "Giggand, Twitch, Discord, Stream, Streamer, "
    "Chat, Clip, Gameplay, Game, Bro, Bruder, Digga, Digger, "
    "Junge, Alter, Wallah, Vallah, Mashallah, Inshallah, "
    "Habibi, safe, cringe, crazy, NPC, Chatten, zocken, "
    "TikTok, YouTube, Fortnite, Minecraft, GTA. "
    "Transkribiere das tatsächlich Gesagte möglichst wortgetreu. "
    "Ändere Umgangssprache nicht unnötig in Hochdeutsch."
)


def load_core():
    spec = importlib.util.spec_from_file_location(
        "clipcrip2_core_process_clips",
        CORE_FILE,
    )

    if spec is None or spec.loader is None:
        raise RuntimeError(
            f"Konnte Core-Datei nicht laden: {CORE_FILE}"
        )

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    return module


def main():
    GIGGAND_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    core = load_core()

    core.INPUT_DIR = (
        GIGGAND_ROOT / "selected_clips"
    )

    core.OUTPUT_DIR = (
        GIGGAND_ROOT / "tiktok_ready"
    )

    core.METADATA_FILE = (
        GIGGAND_ROOT / "clips_today.json"
    )

    core.OUTPUT_PREFIX = (
        "giggand_clipcrip5_tiktok"
    )

    core.WATERMARK = "@clipcrip5"

    core.BASE_PROMPT = (
        GIGGAND_WHISPER_PROMPT
    )

    print("")
    print(
        "=========================================="
    )
    print(
        "CLIPCRIP5 GIGGAND – TIKTOK VIDEOS"
    )
    print(
        "=========================================="
    )
    print("Twitch: giggand")
    print("TikTok: @clipcrip5")
    print("Wasserzeichen: @clipcrip5")
    print(
        "Output: "
        + str(core.OUTPUT_DIR)
    )
    print("")

    core.main()


if __name__ == "__main__":
    main()