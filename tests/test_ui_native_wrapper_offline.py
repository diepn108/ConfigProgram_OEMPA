"""Exercise ctypes decoding with a fake DLL only; no SDK or hardware loading."""

import ctypes
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


class FakeDLL:
    def __init__(self):
        self.functions = {}

    def __getattr__(self, name):
        return self.functions.setdefault(name, Mock())


class WrapperTests(unittest.TestCase):
    def fill_fmc_batch(self, handle, base, normal, multi, tx, topology):
        topology[:] = (256, 1, 1)
        for index in range(256):
            self.assertEqual(base[index], int(index % 16 == 0))
            normal[index].cycle = index
            normal[index].point_count = 3001
            normal[index].sampling_hz = 100e6
            normal[index].rx_enabled[index % 16] = 1
            multi[index].width_count = multi[index].tx_delay_count = -1
            multi[index].start_count = 16
            tx[index].width_count = tx[index].tx_delay_count = -1
        return 1

    def test_batch_export_decodes_all_cycles_and_preserves_unavailable_not_false(self):
        self.dll.OEMPA_GetFMCSnapshotBatch.side_effect = self.fill_fmc_batch
        batch = self.api.get_fmc_snapshot_batch('fake', tuple(i % 16 == 0 for i in range(256)))
        self.assertEqual(len(batch['normal']), 256)
        self.assertEqual(batch['normal'][255]['cycle'], 255)
        self.assertEqual(batch['normal'][255]['rx_enabled'][15], 1)
        self.assertEqual(batch['normal'][255]['sampling_hz'], 100e6)
        self.assertIsNone(batch['multi'][0]['hw_acquisition'])
        self.assertIsNone(batch['tx'][240]['widths_s'])
        self.assertIsNone(batch['tx'][240]['tx_delays_s'])
        self.assertIs(self.dll.OEMPA_GetFMCSnapshotBatch.argtypes[2]._type_, self.api.OEMPACycleSnapshot)

    def test_batch_export_failure_and_invalid_outputs_never_fall_back(self):
        flags = tuple(i % 16 == 0 for i in range(256))
        self.dll.OEMPA_GetFMCSnapshotBatch.return_value = 0
        with self.assertRaisesRegex(RuntimeError, 'configuration not accepted'):
            self.api.get_fmc_snapshot_batch('fake', flags)
        self.dll.OEMPA_GetCycleSnapshot.assert_not_called()
        def invalid(*args):
            self.fill_fmc_batch(*args)
            args[2][255].cycle = 0
            return 1
        self.dll.OEMPA_GetFMCSnapshotBatch.side_effect = invalid
        with self.assertRaisesRegex(RuntimeError, 'cycle order'):
            self.api.get_fmc_snapshot_batch('fake', flags)
        def invalid_count(*args):
            self.fill_fmc_batch(*args)
            args[3][240].start_count = 17
            return 1
        self.dll.OEMPA_GetFMCSnapshotBatch.side_effect = invalid_count
        with self.assertRaisesRegex(RuntimeError, 'counts'):
            self.api.get_fmc_snapshot_batch('fake', flags)

    def test_batch_old_dll_and_invalid_structure(self):
        self.dll.OEMPA_GetFMCSnapshotBatch = None
        self.assertIsNone(self.api.get_fmc_snapshot_batch('fake', ()))
        self.dll.OEMPA_GetFMCSnapshotBatch = Mock()
        with self.assertRaises(ValueError):
            self.api.get_fmc_snapshot_batch('fake', (True,) * 256)
        self.dll.OEMPA_GetFMCSnapshotBatch.assert_not_called()

    def test_preparation_profile_decodes_bounded_counts_and_nanoseconds(self):
        def fill(index, name, values):
            if index: return 0
            name.value = b'GetCycleSnapshot.UnlockDevice'
            values[:] = (256, 32000000000, 200000000)
            return 1
        self.dll.OEMPA_BeginPreparationTiming.return_value = 1
        self.dll.OEMPA_EndPreparationTiming.return_value = 1
        self.dll.OEMPA_GetPreparationTiming.side_effect = fill
        self.api.begin_preparation_timing()
        result = self.api.end_preparation_timing()
        self.assertEqual(result['calls']['GetCycleSnapshot.UnlockDevice'], {'count': 256, 'total_s': 32, 'max_s': .2})
        self.assertFalse(result['overflow'])
        self.assertEqual(self.dll.OEMPA_GetPreparationTiming.call_count, 2)
        self.assertIs(self.dll.OEMPA_GetPreparationTiming.argtypes[2]._type_, ctypes.c_int64)

    def test_preparation_profile_overflow_and_failure_are_explicit(self):
        self.dll.OEMPA_EndPreparationTiming.return_value = 0
        self.dll.OEMPA_GetPreparationTiming.return_value = 0
        self.assertTrue(self.api.end_preparation_timing()['overflow'])
        self.dll.OEMPA_GetPreparationTiming.return_value = -1
        with self.assertRaisesRegex(RuntimeError, 'read failed'):
            self.api.end_preparation_timing()
        self.dll.OEMPA_BeginPreparationTiming.return_value = 0
        with self.assertRaisesRegex(RuntimeError, 'unavailable'):
            self.api.begin_preparation_timing()

    def test_native_timing_export_decodes_separate_observations(self):
        def fill(handle, values):
            values[:] = (1000, 100, 150, 110, 600, 610, 620, 700)
            return 1
        self.dll.OEMPA_GetFMCTiming.side_effect = fill
        result = self.api.get_fmc_timing(None)
        self.assertEqual(result['first_callback'], 110)
        self.assertEqual(result['sdk_on_return'], 150)
        self.assertEqual(result['frequency'], 1000)
        self.assertIs(self.dll.OEMPA_GetFMCTiming.argtypes[1]._type_, ctypes.c_int64)
        self.dll.OEMPA_GetFMCTiming.side_effect = None
        self.dll.OEMPA_GetFMCTiming.return_value = 0
        with self.assertRaises(RuntimeError):
            self.api.get_fmc_timing(None)
    def test_first_frame_exports_preserve_local_evidence_and_wait_types(self):
        from oempa.fmc_acceptance import FRAME_FIELDS
        def fill(handle, values):
            values[:] = (256, 1, 0, -1, 281, 256, 257, 25, 0, 0, 0, 0, 0, 0)
            return 1
        self.dll.OEMPA_BeginFMCFirstFrame.return_value = 1
        self.dll.OEMPA_WaitFMCFirstFrame.return_value = 1
        self.dll.OEMPA_GetFMCFirstFrame.side_effect = fill
        self.api.begin_fmc_first_frame(None, 3001, 1, True, 0)
        self.api.wait_fmc_first_frame(None, .01)
        result = self.api.get_fmc_first_frame(None)
        self.assertEqual(set(result), set(FRAME_FIELDS))
        self.assertEqual(result['post_frame_callback_count'], 25)
        self.assertIs(self.dll.OEMPA_GetFMCFirstFrame.argtypes[1]._type_, ctypes.c_int64)
        self.assertIs(self.dll.OEMPA_WaitFMCFirstFrame.restype, ctypes.c_int)
        self.dll.OEMPA_WaitFMCFirstFrame.assert_called_once_with(None, 10)

    def test_first_frame_export_failures_never_invent_accepted_evidence(self):
        self.dll.OEMPA_BeginFMCFirstFrame.return_value = 0
        self.dll.OEMPA_GetFMCFirstFrame.return_value = 0
        self.dll.OEMPA_WaitFMCFirstFrame.return_value = 0
        with self.assertRaises(RuntimeError):
            self.api.begin_fmc_first_frame(None, 3001, 1, True, 0)
        with self.assertRaises(RuntimeError):
            self.api.get_fmc_first_frame(None)
        with self.assertRaises(RuntimeError):
            self.api.wait_fmc_first_frame(None, .01)

    def test_callback_order_exports_decode_fixed_integer_buffers(self):
        def fill(handle, rows, summary, first):
            summary[:] = (2, 256, 1, 0, 0, 0, 0, 1, 2)
            rows[:20] = (1, 1, 1, 0, 3001, 1, 1, 0, 0, 0, 2, 10, 1, -1, 0, 0, 0, 0, 0, 0)
            first[0] = 1
            return 1
        self.dll.OEMPA_BeginCallbackOrder.return_value = 1
        self.dll.OEMPA_GetCallbackOrder.side_effect = fill
        self.api.begin_callback_order(None, 256, 3001, 1, True, 0)
        result = self.api.get_callback_order(None)
        self.assertEqual(result["first_occurrence_events"][0], 1)
        self.assertEqual(result["events"][0]["sample_count"], 3001)
        self.assertFalse(result["overflow"])
        self.assertIs(self.dll.OEMPA_GetCallbackOrder.argtypes[1]._type_, ctypes.c_int64)

    def test_callback_order_failures_do_not_invent_empty_evidence(self):
        self.dll.OEMPA_BeginCallbackOrder.return_value = 0
        self.dll.OEMPA_GetCallbackOrder.return_value = 0
        with self.assertRaisesRegex(RuntimeError, "armed"):
            self.api.begin_callback_order(None, 256, 3001, 1, True, 0)
        with self.assertRaisesRegex(RuntimeError, "unavailable"):
            self.api.get_callback_order(None)

    def test_callback_record_stats_preserve_duplicates_and_unexpected_ids(self):
        def fill(handle, capacity, counts, summary):
            self.assertEqual(capacity, 256)
            counts[:] = [1] * 256
            counts[3] = 2
            summary[:] = (258, 1, 1, 0, 256)
            return 1
        self.dll.OEMPA_GetCallbackRecordStats.side_effect = fill
        result = self.api.get_callback_record_stats(None, 256)
        self.assertEqual(result["duplicates"], 1)
        self.assertEqual(result["unexpected"], 1)
        self.assertEqual(result["first_unexpected"], 256)
        self.assertEqual(result["cycle_counts"][3], 2)
        self.assertIs(self.dll.OEMPA_GetCallbackRecordStats.restype, ctypes.c_int)

    def test_callback_stats_export_failure_is_not_zero_records(self):
        self.dll.OEMPA_GetCallbackRecordStats.return_value = 0
        with self.assertRaisesRegex(RuntimeError, "statistics unavailable"):
            self.api.get_callback_record_stats(None, 256)

    def test_emission_diagnostic_preserves_unchanged_seeds_without_inference(self):
        def fill(handle, cycle, getter, capacity, count, seed, aperture, observations, after_call, after_unlock, aperture_call, aperture_unlock):
            observations[:] = (1, capacity, count, 1, capacity, count)
            after_call[:] = seed[:]
            after_unlock[:] = seed[:]
            aperture_call[:] = aperture[:]
            aperture_unlock[:] = aperture[:]
            return 1
        self.dll.OEMPA_GetEmissionGetterDiagnostic.side_effect = fill
        result = self.api.get_emission_getter_diagnostic(None, 16, 1, 64, 16, 1)
        self.assertTrue(result["getter_success"])
        self.assertEqual(result["count_before"], result["count_after_unlock"])
        self.assertEqual(result["output_before"], result["output_after_unlock"])
        self.assertNotIn("verified", result)
        self.assertNotIn("widths_s", result)
        types = self.dll.OEMPA_GetEmissionGetterDiagnostic.argtypes
        self.assertIs(types[6]._type_, ctypes.c_uint32)
        self.assertIs(types[5]._type_, ctypes.c_float)

    def test_emission_diagnostic_distinguishes_deferred_output_and_failure(self):
        def fill(handle, cycle, getter, capacity, count, seed, aperture, observations, after_call, after_unlock, aperture_call, aperture_unlock):
            observations[:] = (0, capacity, count, 1, capacity, 1)
            after_call[:] = seed[:]
            after_unlock[:] = seed[:]
            after_unlock[0] = 0.0
            return 1
        self.dll.OEMPA_GetEmissionGetterDiagnostic.side_effect = fill
        result = self.api.get_emission_getter_diagnostic(None, 0, 2, 16, 0)
        self.assertFalse(result["getter_success"])
        self.assertEqual(result["count_after_call"], 0)
        self.assertEqual(result["count_after_unlock"], 1)
        self.assertEqual(result["output_after_unlock"][0], 0.0)
        self.assertNotEqual(result["output_before"], result["output_after_unlock"])

    def test_cycle_diagnostic_keeps_success_and_state_separate(self):
        def fill(handle, cycle, seed, success, state, unlock):
            success._obj.value = 1
            state._obj.value = 0
            unlock._obj.value = 1
            return 1
        self.dll.OEMPA_GetMultiHWChannelCycleDiagnostic.side_effect = fill
        result = self.api.get_multihw_cycle_diagnostic(None, 16, True)
        self.assertEqual(result, {"getter_success": True, "acquisition_state": False, "unlock_success": True})
        self.assertIs(self.dll.OEMPA_GetMultiHWChannelCycleDiagnostic.restype, ctypes.c_int)

    def test_cycle_diagnostic_preserves_sdk_failure(self):
        def fill(handle, cycle, seed, success, state, unlock):
            success._obj.value = 0
            state._obj.value = seed
            unlock._obj.value = 1
            return 1
        self.dll.OEMPA_GetMultiHWChannelCycleDiagnostic.side_effect = fill
        result = self.api.get_multihw_cycle_diagnostic(None, 0, True)
        self.assertFalse(result["getter_success"])
        self.assertTrue(result["acquisition_state"])

    def test_multichannel_getter_failure_is_not_reported_as_disabled(self):
        self.dll.OEMPA_GetMultiChannelSupport.return_value = 0
        with self.assertRaisesRegex(RuntimeError, "Multi-Channel state"):
            self.api.get_multichannel_state("fake")

    def setUp(self):
        self.dll = FakeDLL()
        spec = importlib.util.spec_from_file_location("offline_api", Path(__file__).resolve().parents[1] / "oempa/api.py")
        self.api = importlib.util.module_from_spec(spec)
        with patch("ctypes.CDLL", return_value=self.dll) as loader, patch("os.add_dll_directory"), patch("pathlib.Path.exists", return_value=True):
            spec.loader.exec_module(self.api)
            loader.assert_called_once()

    def test_struct_layout_matches_native_abi(self):
        self.assertEqual(ctypes.sizeof(self.api.OEMPAExtendedCycleSnapshot), 216)
        self.assertEqual(self.api.OEMPAExtendedCycleSnapshot.multi_decimation_bytes.offset, 208)

    def test_replay_not_read_is_none_not_zero(self):
        def fill(handle, cycle, multi, pointer):
            value = pointer._obj
            value.width_count = -1
            value.tx_delay_count = -1
            value.start_count = 16
            value.multi_starts_s[7] = 6e-6
            return 1
        self.dll.OEMPA_GetExtendedCycleSnapshot.side_effect = fill
        snapshot = self.api.get_extended_cycle_snapshot(None, 1, True)
        self.assertIsNone(snapshot["widths_s"])
        self.assertIsNone(snapshot["tx_delays_s"])
        self.assertAlmostEqual(snapshot["multi_starts_s"][7], 6e-6)
        self.assertEqual(snapshot["multi_decimation_bytes"], (0,) * 8)
        self.assertIsNone(snapshot["hw_acquisition"])

    def test_zero_emission_delay_remains_a_real_zero(self):
        def fill(handle, cycle, multi, pointer):
            pointer._obj.width_count = 1
            pointer._obj.widths_s[0] = 0.5e-6
            pointer._obj.tx_delay_count = 1
            pointer._obj.tx_delays_s[0] = 0.0
            return 1
        self.dll.OEMPA_GetExtendedCycleSnapshot.side_effect = fill
        snapshot = self.api.get_extended_cycle_snapshot(None, 0, False)
        self.assertEqual(snapshot["tx_delays_s"], (0.0,))
        self.assertIsNone(snapshot["multi_starts_s"])

    def test_invalid_counts_rejected(self):
        def fill(handle, cycle, multi, pointer):
            pointer._obj.width_count = 17
            return 1
        self.dll.OEMPA_GetExtendedCycleSnapshot.side_effect = fill
        with self.assertRaisesRegex(RuntimeError, "counts"):
            self.api.get_extended_cycle_snapshot(None, 0, True)


if __name__ == "__main__":
    unittest.main()
