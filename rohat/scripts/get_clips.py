from pathlib import Path
import importlib.util


REPO_ROOT = Path(__file__).resolve().parents[2]
ROHAT_ROOT = REPO_ROOT / "rohat"
CORE_FILE = REPO_ROOT / "scripts" / "get_clips.py"


def load_core():
    spec = importlib.util.spec_from_file_location(
        "clipcrip2_core_get_clips",
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
    ROHAT_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    core = load_core()

    core.BROADCASTER_LOGIN = "xrohat"

    core.USED_FILE = str(
        ROHAT_ROOT / "used_clips.json"
    )

    core.OUTPUT_FILE = str(
        ROHAT_ROOT / "clips_today.json"
    )

    print("")
    print("================================")
    print("CLIPCRIP4 – ROHAT")
    print("================================")
    print("Twitch: xrohat")

    print(
        "Eigene Used-History: "
        + core.USED_FILE
    )

    print(
        "Eigene Kandidaten-Datei: "
        + core.OUTPUT_FILE
    )

    print("")

    core.main()


if __name__ == "__main__":
    main()