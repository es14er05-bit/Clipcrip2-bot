"""Coachlim configuration for the shared discovery engine."""

from pathlib import Path
import importlib.util


REPO_ROOT = Path(__file__).resolve().parents[2]
COACHLIM_ROOT = REPO_ROOT / "coachlim"
CORE_FILE = REPO_ROOT / "scripts" / "get_clips.py"


def load_core():
    spec = importlib.util.spec_from_file_location(
        "clipcrip_core_get_clips",
        CORE_FILE,
    )

    if spec is None or spec.loader is None:
        raise RuntimeError(
            f"Konnte Core-Datei nicht laden: {CORE_FILE}"
        )

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    return module


def main() -> None:
    COACHLIM_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    core = load_core()

    core.BROADCASTER_LOGIN = "coachlim"

    core.USED_FILE = str(
        COACHLIM_ROOT / "used_clips.json"
    )

    core.HISTORY_FILE = str(
        COACHLIM_ROOT / "clip_history.json"
    )

    core.OUTPUT_FILE = str(
        COACHLIM_ROOT / "clips_today.json"
    )

    print(
        "CLIPCRIP6 | Coachlim | "
        "gemeinsame Discovery-Engine"
    )

    core.main()


if __name__ == "__main__":
    main()