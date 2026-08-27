"""Giggand configuration for the shared discovery engine."""

from pathlib import Path
import importlib.util


REPO_ROOT = Path(__file__).resolve().parents[2]
GIGGAND_ROOT = REPO_ROOT / "giggand"
CORE_FILE = REPO_ROOT / "scripts" / "get_clips.py"


def load_core():
    spec = importlib.util.spec_from_file_location("clipcrip_core_get_clips", CORE_FILE)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Konnte Core-Datei nicht laden: {CORE_FILE}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> None:
    GIGGAND_ROOT.mkdir(parents=True, exist_ok=True)
    core = load_core()
    core.BROADCASTER_LOGIN = "giggand"
    core.USED_FILE = str(GIGGAND_ROOT / "used_clips.json")
    core.HISTORY_FILE = str(GIGGAND_ROOT / "clip_history.json")
    core.OUTPUT_FILE = str(GIGGAND_ROOT / "clips_today.json")
    print("CLIPCRIP5 | Giggand | gemeinsame Discovery-Engine")
    core.main()


if __name__ == "__main__":
    main()
