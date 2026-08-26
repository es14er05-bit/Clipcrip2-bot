from pathlib import Path
import importlib.util


REPO_ROOT = Path(__file__).resolve().parents[2]
ROHAT_ROOT = REPO_ROOT / "rohat"
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
    ROHAT_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    core = load_core()

    core.INPUT_DIR = str(
        ROHAT_ROOT / "downloaded_clips"
    )

    core.FINAL_DIR = str(
        ROHAT_ROOT / "selected_clips"
    )

    core.INPUT_JSON = str(
        ROHAT_ROOT / "clips_today.json"
    )

    core.USED_FILE = str(
        ROHAT_ROOT / "used_clips.json"
    )

    core.HISTORY_FILE = str(
        ROHAT_ROOT / "clip_history.json"
    )

    print("")
    print("==========================================")
    print("CLIPCRIP4 ROHAT – QUALITY CONTROL")
    print("==========================================")

    print(
        "QC-Engine: identisch mit ClipCrip2"
    )

    print(
        "Eigene Rohat-History: "
        + core.HISTORY_FILE
    )

    print("")

    core.main()


if __name__ == "__main__":
    main()