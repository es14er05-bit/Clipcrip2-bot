from __future__ import annotations

import datetime as dt
import json
import statistics
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

# The repository dependencies are installed by GitHub Actions. These tiny
# fallbacks let pure scoring/configuration tests run in a bare local runtime
# without pretending to test OpenCV or HTTP itself.
try:
    import requests  # noqa: F401
except ImportError:
    requests_module = types.ModuleType("requests")
    requests_module.Session = object
    adapters_module = types.ModuleType("requests.adapters")
    adapters_module.HTTPAdapter = object
    requests_module.adapters = adapters_module
    sys.modules["requests"] = requests_module
    sys.modules["requests.adapters"] = adapters_module

    urllib3_module = types.ModuleType("urllib3")
    urllib3_util_module = types.ModuleType("urllib3.util")
    urllib3_retry_module = types.ModuleType("urllib3.util.retry")
    urllib3_retry_module.Retry = object
    sys.modules["urllib3"] = urllib3_module
    sys.modules["urllib3.util"] = urllib3_util_module
    sys.modules["urllib3.util.retry"] = urllib3_retry_module

try:
    import numpy  # noqa: F401
except ImportError:
    numpy_module = types.ModuleType("numpy")
    numpy_module.ndarray = object
    numpy_module.median = lambda values: statistics.median(values)
    sys.modules["numpy"] = numpy_module

try:
    import cv2  # noqa: F401
except ImportError:
    sys.modules["cv2"] = types.ModuleType("cv2")

from scripts import get_clips
from scripts import process_clips
from scripts import quality_control


UTC = dt.timezone.utc


class DiscoveryTests(unittest.TestCase):
    def test_discovery_uses_explicit_recent_seven_day_windows(self):
        fixed_now = dt.datetime(2026, 8, 27, 12, 0, tzinfo=UTC)
        windows = []

        def fake_window(session, token, broadcaster_id, started_at, ended_at):
            windows.append((started_at, ended_at))
            return []

        with mock.patch.object(get_clips, "utc_now", return_value=fixed_now), mock.patch.object(
            get_clips, "get_window_clips", side_effect=fake_window
        ):
            result = get_clips.get_all_clips("token", "broadcaster", session=object())

        self.assertEqual(result, [])
        self.assertTrue(windows)
        self.assertEqual(windows[0][1], fixed_now)
        self.assertEqual(windows[-1][0], fixed_now - dt.timedelta(days=90))
        self.assertTrue(
            all(end > start and end - start <= dt.timedelta(days=7) for start, end in windows)
        )

    def test_candidate_pool_filters_used_vod_regions_and_limits_one_vod(self):
        now = get_clips.utc_now()

        def clip(clip_id, video_id, offset, views):
            return {
                "id": clip_id,
                "url": f"https://clips.twitch.tv/{clip_id}",
                "title": f"Starker Clip {clip_id}",
                "duration": 25.0,
                "view_count": views,
                "created_at": get_clips.iso_z(now - dt.timedelta(days=2)),
                "video_id": video_id,
                "vod_offset": offset,
            }

        clips = [
            clip("used", "vod-used", 100, 10_000),
            clip("near-used", "vod-used", 140, 9_000),
            clip("a", "same-vod", 100, 8_000),
            clip("b", "same-vod", 300, 7_000),
            clip("c", "same-vod", 500, 6_000),
            clip("d", "same-vod", 700, 5_000),
            clip("other", "other-vod", 100, 4_000),
        ]
        candidates = get_clips.build_candidates(clips, {"used"}, {})
        ids = {item["id"] for item in candidates}
        self.assertNotIn("used", ids)
        self.assertNotIn("near-used", ids)
        self.assertIn("other", ids)
        self.assertEqual(
            len([item for item in candidates if item.get("video_id") == "same-vod"]),
            get_clips.MAX_CANDIDATES_PER_VOD,
        )


class DuplicateTests(unittest.TestCase):
    @staticmethod
    def candidate(**metadata):
        base_metadata = {
            "id": "new-id",
            "title": "Komplett anderer Talk",
            "video_id": "",
            "vod_offset": None,
        }
        base_metadata.update(metadata)
        return {
            "metadata": base_metadata,
            "frame_hashes": ["0000000000000000"] * 7,
            "legacy_signature": [],
            "transcript_text": "heute reden wir über autos und fahren nach berlin",
        }

    def test_same_layout_without_matching_content_is_not_a_duplicate(self):
        candidate = self.candidate()
        old = {
            "title": "Ein anderes Thema",
            "frame_hashes": ["0000000000000000"] * 7,
            "transcript_excerpt": "der chat diskutiert über fußball und das letzte spiel",
        }
        self.assertIsNone(quality_control.duplicate_reason(candidate, old))

    def test_matching_frames_and_transcript_are_duplicate(self):
        candidate = self.candidate()
        old = {
            "title": "Anderer Titel",
            "frame_hashes": ["0000000000000000"] * 7,
            "transcript_excerpt": "wir reden heute über autos und fahren gemeinsam nach berlin",
        }
        self.assertIsNotNone(quality_control.duplicate_reason(candidate, old))

    def test_same_vod_region_is_always_duplicate(self):
        candidate = self.candidate(video_id="vod-1", vod_offset=500)
        old = {"video_id": "vod-1", "vod_offset": 540}
        self.assertEqual(
            quality_control.duplicate_reason(candidate, old), "gleiche VOD-Position"
        )


class RendererTests(unittest.TestCase):
    def test_hook_is_optional_and_contains_no_emoji(self):
        self.assertEqual(process_clips.create_hook({}), "")
        hook = process_clips.create_hook(
            {
                "id": "abc",
                "title": "lacht",
                "hook_category": "laugh",
                "hook_confidence": 0.9,
            }
        )
        self.assertTrue(hook)
        self.assertNotRegex(hook, r"[^A-Za-z0-9ÄÖÜäöüß?!.,'’\- ]")

    def test_zero_selected_clips_is_a_successful_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_dir = root / "selected"
            output_dir = root / "output"
            input_dir.mkdir()
            metadata = root / "clips_today.json"
            metadata.write_text("[]", encoding="utf-8")

            with mock.patch.object(process_clips, "INPUT_DIR", input_dir), mock.patch.object(
                process_clips, "OUTPUT_DIR", output_dir
            ), mock.patch.object(process_clips, "METADATA_FILE", metadata), mock.patch.object(
                process_clips, "SELECTION_REPORT_FILE", root / "selection_report.json"
            ):
                process_clips.main()

            manifest = json.loads(
                (output_dir / "publish_manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["status"], "no_strong_clips")
            self.assertEqual(manifest["output_count"], 0)


if __name__ == "__main__":
    unittest.main()
