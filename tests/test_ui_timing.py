"""Synthetic timing diagnostics only; no SDK/device imports."""

from dataclasses import replace
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import numpy as np

from oempa.config import FMCConfig
from oempa.dataset import capture_metadata, load_dataset, save_dataset
from oempa.timing import FMCTiming, NATIVE_MARKS
from ui_readback_fakes import matching_fmc


class TimingTests(unittest.TestCase):
    def test_preparation_stages_measure_success_and_failure_without_changing_results(self):
        profile = FMCTiming()
        with patch('oempa.timing.time.perf_counter', side_effect=[1, 3, 4, 9]):
            self.assertEqual(profile.call('snapshot', lambda: 42), 42)
            with self.assertRaisesRegex(RuntimeError, 'read failed'):
                profile.call('failed', lambda: (_ for _ in ()).throw(RuntimeError('read failed')))
        self.assertEqual(profile.report()['preparation_stages_s'], {'snapshot': 2, 'failed': 5})

    def test_sdk_scope_closes_on_read_failure_and_preserves_original_error(self):
        from unittest.mock import Mock
        reader = SimpleNamespace(begin_preparation_timing=Mock(), end_preparation_timing=Mock(side_effect=RuntimeError('diagnostic failed')))
        profile = FMCTiming()
        with self.assertRaisesRegex(ValueError, 'original read failure'):
            with profile.sdk_preparation(reader, 'off_readback'):
                raise ValueError('original read failure')
        reader.end_preparation_timing.assert_called_once_with()
        self.assertIn('diagnostic failed', profile.warnings[0])

    def test_unavailable_sdk_profile_does_not_skip_measured_operation(self):
        profile = FMCTiming()
        with profile.sdk_preparation(SimpleNamespace(), 'off_readback'):
            value = profile.call('topology', lambda: 256)
        self.assertEqual(value, 256)
        self.assertEqual(profile.preparation_sdk, {})
        self.assertTrue(profile.warnings)

    def test_aggregate_sdk_costs_roundtrip_and_summary_is_bounded(self):
        from unittest.mock import Mock
        calls = {f'getter{i}': {'count': 256, 'total_s': float(i), 'max_s': .2} for i in range(20)}
        observation = {'calls': calls, 'overflow': False}
        reader = SimpleNamespace(begin_preparation_timing=Mock(), end_preparation_timing=Mock(return_value=observation))
        profile = FMCTiming()
        with profile.sdk_preparation(reader, 'off_readback'):
            pass
        self.assertEqual(profile.report()['preparation_sdk']['off_readback'], observation)
        self.assertIn('getter19=19.0000s/256 calls', profile.summary())
        self.assertNotIn('getter0=', profile.summary())

    def test_first_observation_wins_and_counters_do_not_change_acceptance(self):
        profile = FMCTiming()
        profile.mark('frame_complete', 2)
        profile.mark('frame_complete', 9)
        profile.counters = {'accepted_cycles': 256, 'post_frame_callback_count': 28}
        self.assertEqual(profile.report()['marks']['frame_complete'], 2)
        self.assertEqual(profile.report()['counters']['post_frame_callback_count'], 28)
        self.assertEqual(profile.report()['physical_firing_count'], 'Unknown')

    def test_native_timestamps_allow_callback_before_on_return(self):
        profile = FMCTiming()
        values = dict(zip(('frequency',) + NATIVE_MARKS, (1000, 1000, 1300, 1100, 1600, 1610, 1620, 1700)))
        with patch('oempa.timing.time.get_clock_info', return_value=SimpleNamespace(implementation='QueryPerformanceCounter()')):
            profile.native_marks(values)
        duration = profile.report()['durations_s']
        self.assertAlmostEqual(duration['sdk_on'], .3)
        self.assertAlmostEqual(duration['first_callback_latency'], .1)
        self.assertAlmostEqual(duration['first_frame'], .5)
        self.assertAlmostEqual(duration['sdk_off'], .08)
        self.assertLess(profile.marks['first_callback'], profile.marks['sdk_on_return'])

    def test_unaligned_or_unavailable_native_clock_not_invented(self):
        profile = FMCTiming()
        values = dict.fromkeys(('frequency',) + NATIVE_MARKS, 0)
        with patch('oempa.timing.time.get_clock_info', return_value=SimpleNamespace(implementation='other clock')):
            profile.native_marks(values)
        self.assertFalse(profile.marks)
        self.assertTrue(profile.warnings)
        self.assertNotIn('first_frame', profile.report()['durations_s'])

    def test_no_off_return_or_display_return_before_observed(self):
        profile = FMCTiming()
        for mark, value in (('requested', 1), ('worker_start', 2), ('off_request', 3)):
            profile.mark(mark, value)
        durations = profile.report()['durations_s']
        self.assertEqual(durations['worker_queue'], 1)
        self.assertNotIn('shutdown_off', durations)
        self.assertNotIn('total', durations)

    def test_profile_saved_with_full_unmodified_cube_and_mapping(self):
        cfg = FMCConfig(range_us=.12)
        snapshot = matching_fmc(cfg)
        raw = np.arange(256 * 7, dtype=np.int16).reshape(16, 16, 7).astype(np.int8)
        before = raw.copy()
        metadata = capture_metadata(raw, snapshot, 4, cfg, SimpleNamespace(point_count=7, data_size=1, signed=True, bit_size=0))
        profile = FMCTiming()
        profile.mark('requested', 1)
        profile.mark('draw_complete', 2)
        profile.counters = {'accepted_cycles': 256, 'post_frame_callback_count': 25}
        profile.preparation = {'full_snapshot': 35.0}
        profile.preparation_sdk = {'off_readback': {'calls': {'LockDevice': {'count': 528, 'total_s': 20.0, 'max_s': .1}}, 'overflow': False}}
        metadata = replace(metadata, timing_profile=tuple(profile.report().items()))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'synthetic.npy'
            save_dataset(path, raw, metadata)
            loaded = load_dataset(path)
        np.testing.assert_array_equal(loaded.data, before)
        self.assertEqual(loaded.metadata.timing_profile, metadata.timing_profile)
        self.assertEqual(loaded.metadata.cycle_mapping, 'cycle = tx * 16 + rx')

    def test_callback_has_no_device_access_and_no_timing_file_io(self):
        source = (Path(__file__).resolve().parents[1] / 'bridge/oempa_bridge.cpp').read_text()
        begin = source.index('static UINT WINAPI AcquisitionAscanCallback')
        callback = source[begin:source.index('// Device creation', begin)]
        for token in ('device.', 'LockDevice', 'UnlockDevice', 'fopen', 'ofstream'):
            self.assertNotIn(token, callback)
