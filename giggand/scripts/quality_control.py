from pathlib import Path
import importlib.util


REPO_ROOT = Path(__file__).resolve().parents[2]
GIGGAND_ROOT = REPO_ROOT / "giggand"
CORE_FILE = REPO_ROOT / "scripts" / "quality_control.py"


def load_core():
    spec = importlib.util.spec_from_file_location(
        "clipcrip2_core_quality_control",
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

    core.INPUT_DIR = str(
        GIGGAND_ROOT / "downloaded_clips"
    )

    core.FINAL_DIR = str(
        GIGGAND_ROOT / "selected_clips"
    )

    core.INPUT_JSON = str(
        GIGGAND_ROOT / "clips_today.json"
    )

    core.USED_FILE = str(
        GIGGAND_ROOT / "used_clips.json"
    )

    core.HISTORY_FILE = str(
        GIGGAND_ROOT / "clip_history.json"
    )

    core.REPORT_FILE = str(
        GIGGAND_ROOT / "selection_report.json"
    )

    core.STREAMER_NAME = "Giggand"

    core.WHISPER_PROMPT = (
        "Deutscher Twitch-Stream von Giggand. Die Sprecher reden schnell, "
        "locker und umgangssprachlich. Namen und Wörter: Giggand, Chat, "
        "Bro, Bruder, Digga, Wallah, crashout. Transkribiere wortgetreu "
        "und behalte Jugendsprache bei."
    )

    print("")
    print(
        "=========================================="
    )
    print(
        "CLIPCRIP5 GIGGAND – QUALITY CONTROL"
    )
    print(
        "=========================================="
    )
    print(
        "QC-Engine: gemeinsame Viral Quality Gate V4"
    )
    print(
        "Eigene Giggand-History: "
        + core.HISTORY_FILE
    )
    print("")

    core.main()


if __name__ == "__main__":
    main()
