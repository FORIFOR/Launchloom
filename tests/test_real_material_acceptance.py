"""Tests for the opt-in validator itself; these are not real-media acceptance."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

JOURNEY = Path(__file__).with_name('real_material_browser_journey.py')
sys.path.insert(0, str(JOURNEY.parent))
spec = importlib.util.spec_from_file_location('real_material_acceptance', JOURNEY)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class RealMaterialValidatorTests(unittest.TestCase):
    def probe(self, width=1920, height=1080, duration=26, codec='h264', fps='30/1', decode_error=''):
        metadata = {'streams': [{'codec_type': 'video', 'width': width, 'height': height,
                                'codec_name': codec, 'pix_fmt': 'yuv420p', 'avg_frame_rate': fps}],
                    'format': {'duration': str(duration)}}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'fixture.mp4'; path.write_bytes(b'validator-test-only')
            results = [subprocess.CompletedProcess([], 0, json.dumps(metadata), ''),
                       subprocess.CompletedProcess([], bool(decode_error), '', decode_error)]
            with patch.object(module.subprocess, 'run', side_effect=results):
                return module.probe_video(path, (1920, 1080), 26)

    def test_hd_metadata_and_clean_decode_are_required(self):
        self.assertTrue(self.probe()['full_decode'])

    def test_rejects_draft_size_wrong_codec_fps_duration_and_decode_failure(self):
        for change in [{'width': 960, 'height': 540}, {'codec': 'vp9'}, {'fps': '24/1'},
                       {'duration': 10}, {'decode_error': 'corrupt frame'}]:
            with self.subTest(change=change), self.assertRaises(AssertionError): self.probe(**change)

    def test_missing_provenance_is_not_silent_synthetic_fallback(self):
        result = subprocess.run([sys.executable, str(JOURNEY)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn('--output is required', result.stderr)


if __name__ == '__main__': unittest.main()
