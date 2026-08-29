from pathlib import Path
import importlib.util


REPO_ROOT = Path(__file__).resolve().parents[2]
COACHLIM_ROOT = REPO_ROOT / "coachlim"
CORE_FILE = REPO_ROOT / "scripts" / "download_clips.py"


def load_core():
    spec = importlib.util.spec_from_file_location(
        "clipcrip2_core_download_clips",
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
    COACHLIM_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    core = load_core()

    core.INPUT_FILE = str(
        COACHLIM_ROOT / "clips_today.json"
    )

    core.OUTPUT_DIR = str(
        COACHLIM_ROOT / "downloaded_clips"
    )

    print("")
    print(
        "================================"
    )
    print(
        "CLIPCRIP6 COACHLIM – DOWNLOAD"
    )
    print(
        "================================"
    )

    print(
        "Input: "
        + core.INPUT_FILE
    )

    print(
        "Output: "
        + core.OUTPUT_DIR
    )

    print("")

    core.main()


if __name__ == "__main__":
    main()