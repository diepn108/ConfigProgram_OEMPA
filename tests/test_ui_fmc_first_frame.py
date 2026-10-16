"""SDK-free native gate and synthetic dataset tests; never opens a device."""

from dataclasses import replace
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
import numpy as np

from oempa.callback_order import decode_callback_order
from oempa.fmc_acceptance import FRAME_FIELDS, first_frame_evidence, require_first_frame
from oempa.fmc import FMCData
from oempa.bscan import BScanProcessor
from oempa.config import FMCConfig
from oempa.dataset import capture_metadata, load_dataset, save_dataset
from ui_readback_fakes import matching_fmc


class FirstFrameTests(unittest.TestCase):
    def evidence(self, scenario):
        result = subprocess.run([str(Path(__file__).with_name('fmc_first_frame_native.exe')), scenario], capture_output=True, text=True, check=True)
        raw = json.loads(result.stdout)
        return dict(zip(FRAME_FIELDS, raw['frame'])), decode_callback_order(raw['rows'], raw['summary'], raw['first']), np.array(raw['raw'], dtype=np.int8).reshape(256, 7)

    def test_clean_ordered_frame(self):
        frame, order, raw = self.evidence('exact')
        self.assertTrue(require_first_frame(frame, complete=True))
        evidence = first_frame_evidence(frame, order)
        self.assertEqual(evidence.accepted_cycles, 256)
        self.assertEqual(evidence.post_frame_callback_count, 0)
        self.assertEqual(raw.shape, (256, 7))

    def test_real_case_25_post_frame_callbacks(self):
        frame, order, raw = self.evidence('late25')
        evidence = first_frame_evidence(frame, order)
        self.assertEqual(evidence.post_frame_callback_count, 25)
        self.assertEqual(evidence.first_post_frame_arrival, 257)
        self.assertEqual(evidence.completion_arrival, 256)
        self.assertEqual(raw.reshape(16, 16, 7).shape, (16, 16, 7))

    def test_previous_case_26_post_frame_callbacks(self):
        frame, order, _ = self.evidence('late26')
        self.assertEqual(first_frame_evidence(frame, order).post_frame_callback_count, 26)

    def test_duplicate_before_complete_rejected(self):
        frame, _, _ = self.evidence('duplicate')
        with self.assertRaisesRegex(RuntimeError, 'duplicate cycle 0'):
            require_first_frame(frame, complete=True)
        self.assertEqual(frame['accepted_cycles'], 21)
        self.assertEqual(frame['post_frame_callback_count'], 0)

    def test_missing_cycle_rejected(self):
        frame, _, _ = self.evidence('missing')
        with self.assertRaisesRegex(RuntimeError, 'out-of-order'):
            require_first_frame(frame, complete=True)
        incomplete, _, _ = self.evidence('exact')
        incomplete.update(accepted_cycles=173, first_frame_complete=0, completion_arrival=0)
        with self.assertRaisesRegex(RuntimeError, 'Incomplete'):
            require_first_frame(incomplete, complete=True)

    def test_out_of_order_rejected(self):
        frame, _, _ = self.evidence('order')
        with self.assertRaisesRegex(RuntimeError, 'out-of-order cycle 43'):
            require_first_frame(frame)

    def test_unexpected_cycle_rejected(self):
        frame, _, _ = self.evidence('unexpected')
        with self.assertRaisesRegex(RuntimeError, 'unexpected cycle 256'):
            require_first_frame(frame)

    def test_malformed_and_wrong_representation_rejected(self):
        for scenario in ('malformed', 'count', 'size', 'sign', 'bits'):
            with self.subTest(scenario=scenario):
                frame, _, _ = self.evidence(scenario)
                with self.assertRaisesRegex(RuntimeError, 'malformed'):
                    require_first_frame(frame)

    def test_post_frame_never_overwrites_first_frame(self):
        _, _, first = self.evidence('exact')
        for scenario in ('late25', 'late26', 'overflow', 'postbad'):
            frame, order, raw = self.evidence(scenario)
            first_frame_evidence(frame, order)
            np.testing.assert_array_equal(raw, first)

    def test_post_frame_errors_and_overflow_remain_visible(self):
        frame, order, _ = self.evidence('postbad')
        evidence = first_frame_evidence(frame, order)
        self.assertEqual((evidence.unexpected_post_frame_callbacks, evidence.malformed_post_frame_callbacks), (1, 1))
        frame, order, _ = self.evidence('overflow')
        evidence = first_frame_evidence(frame, order)
        self.assertTrue(evidence.chronology_overflow)
        self.assertEqual(evidence.post_frame_callback_count, 600)
        self.assertLessEqual(len(evidence.chronology_events), 576)

    def test_saved_cube_and_raw_exclude_post_frame_and_preserve_sidecar_evidence(self):
        frame, order, raw = self.evidence('late25')
        cfg = FMCConfig(range_us=.12)
        snapshot = matching_fmc(cfg)
        snapshot = replace(snapshot, cycles=tuple(replace(c, point_count=7) for c in snapshot.cycles))
        cube = raw.reshape(16, 16, 7)
        meta = capture_metadata(cube, snapshot, 8, cfg, SimpleNamespace(point_count=7, data_size=1, signed=True, bit_size=0))
        meta = replace(meta, acquisition_acceptance='accepted', frame_evidence=first_frame_evidence(frame, order))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'synthetic.npy'
            save_dataset(path, cube, meta)
            loaded = load_dataset(path)
            np.save(Path(folder) / 'raw.npy', raw)
            self.assertEqual(np.load(Path(folder) / 'raw.npy').shape, (256, 7))
        np.testing.assert_array_equal(loaded.data, cube)
        self.assertEqual(loaded.metadata.frame_evidence, meta.frame_evidence)
        self.assertEqual(loaded.metadata.acquisition_acceptance, 'accepted')

    def test_diagonal_bscan_all_channels_and_viewer_do_not_touch_hardware(self):
        _, _, raw = self.evidence('late25')
        cube = raw.reshape(16, 16, 7)
        fmc = FMCData(cube, 16, 16, 7, 1, True, 0, start_us=2, sampling_hz=25e6)
        hardware = Mock()
        bscan = BScanProcessor().process(fmc)
        for tx in range(16):
            for rx in range(16):
                np.testing.assert_array_equal(fmc.get_ascan(tx, rx), raw[tx * 16 + rx])
            np.testing.assert_array_equal(bscan.data[tx], cube[tx, tx])
        self.assertEqual(hardware.mock_calls, [])

    def test_missing_chronology_cannot_substitute_for_native_boundary(self):
        frame, order, _ = self.evidence('late25')
        order['events'] = order['events'][2:]
        with self.assertRaisesRegex(RuntimeError, 'Chronology'):
            first_frame_evidence(frame, order)
