"""Batched OFF reads use synthetic/deferred outputs only; no SDK/device loading."""

from dataclasses import replace
from pathlib import Path
import subprocess
import unittest
from unittest.mock import Mock

from oempa.hardware_state import collect_snapshot, verify_configuration
from oempa.verified_fmc import approved_fmc_application, inspect_approved_fmc
from ui_readback_fakes import FakeReadbackAPI, matching_fmc

ROOT = Path(__file__).resolve().parents[1]


class BatchReadbackTests(unittest.TestCase):
    def setUp(self):
        path = ROOT / 'configs/fmc16_full.txt'
        self.config = inspect_approved_fmc(path)
        self.provenance = approved_fmc_application(path, dict(entered=True, before_hw=True, after_hw=True, left=True, parsed_cycle_count=256))
        snapshot = matching_fmc(self.config, 100e6)
        self.snapshot = replace(snapshot, cycles=tuple(replace(cycle, gain_analog_db=20, hw_acquisition=None, widths_s=None, tx_delays_s=None) for cycle in snapshot.cycles))
        self.status = dict(cycle_count=256, multichannel_supported=True, multichannel_enabled=True)

    def batch(self, snapshot=None):
        reader = FakeReadbackAPI(snapshot or self.snapshot)
        return {'status': self.status.copy(), 'normal': tuple(reader.get_cycle_snapshot(None, i) for i in range(256)),
                'multi': tuple(reader.get_extended_cycle_snapshot(None, i, True) for i in range(256)),
                'tx': tuple(reader.get_extended_cycle_snapshot(None, i, False) for i in range(256))}

    def collect(self, reader):
        return collect_snapshot(reader, 'fake', 'FMC', self.status, applied_configuration=self.provenance)

    def test_deferred_native_scope_and_equivalent_fields_and_failure_cleanup(self):
        executable = ROOT / 'tests/fmc_batch_readback_native.exe'
        for case in ('exact', 'lock', 'getter', 'throw', 'flush', 'unlock', 'unlock_throw', 'unlock_pending', 'topology', 'sampling', 'invalid_count', 'unreadable_tx', 'functional_flags'):
            with self.subTest(case=case):
                subprocess.run([str(executable), case], check=True, capture_output=True, text=True)

    def test_uncertain_native_output_owner_survives_device_destruction(self):
        source = (ROOT / 'bridge/oempa_bridge.cpp').read_text()
        context = source[source.index('struct OEMPAContext'):source.index('// Configuration diagnostics')]
        self.assertLess(context.index('failed_batch_storage'), context.index('CHWDeviceOEMPA device'))
        begin = source.index('OEMPA_BRIDGE_API int __cdecl OEMPA_GetFMCSnapshotBatch')
        body = source[begin:source.index('// Parse configuration', begin)]
        self.assertIn('if (context->failed_batch_storage) return 0;', body)
        self.assertLess(body.index('if (!ReadFMCBatch'), body.index('storage.reset();'))
        self.assertNotIn('storage.reset()', body[body.index('catch (...)'):])

    def test_batched_snapshot_equals_legacy_all_fields_and_verification_evidence(self):
        legacy_reader = FakeReadbackAPI(self.snapshot)
        legacy = self.collect(legacy_reader)
        reader = FakeReadbackAPI(self.snapshot)
        reader.get_fmc_snapshot_batch = Mock(return_value=self.batch())
        actual = self.collect(reader)
        self.assertEqual(actual, legacy)
        reader.get_fmc_snapshot_batch.assert_called_once_with('fake', self.provenance.cycle_flags)
        self.assertEqual(reader.calls, [])
        self.assertEqual(len(legacy_reader.calls), 528)
        before, after = verify_configuration(self.config, legacy), verify_configuration(self.config, actual)
        self.assertEqual(before, after)
        self.assertTrue(after.verified)
        self.assertFalse(after.hardware_readback_verified)
        self.assertTrue(all(cycle.hw_acquisition is None for cycle in actual.cycles))

    def test_readable_last_cycle_mismatch_still_blocks(self):
        altered = replace(self.snapshot, cycles=self.snapshot.cycles[:-1] + (replace(self.snapshot.cycles[-1], gain_digital_db=4),))
        reader = FakeReadbackAPI(self.snapshot)
        reader.get_fmc_snapshot_batch = Mock(return_value=self.batch(altered))
        report = verify_configuration(self.config, self.collect(reader))
        self.assertFalse(report.verified)
        self.assertTrue(any(item.field == 'cycle[255].gain_digital_db' for item in report.mismatches))

    def test_supported_batch_failure_never_retries_legacy_or_returns_partial_snapshot(self):
        reader = FakeReadbackAPI(self.snapshot)
        reader.get_fmc_snapshot_batch = Mock(side_effect=RuntimeError('OFF unlock failed'))
        with self.assertRaisesRegex(RuntimeError, 'unlock failed'):
            self.collect(reader)
        self.assertEqual(reader.calls, [])

    def test_old_dll_export_absent_retains_full_legacy_coverage(self):
        reader = FakeReadbackAPI(self.snapshot)
        reader.get_fmc_snapshot_batch = Mock(return_value=None)
        result = self.collect(reader)
        self.assertEqual(len(reader.calls), 528)
        self.assertTrue(verify_configuration(self.config, result).verified)

    def test_topology_change_during_batch_blocks(self):
        batch = self.batch()
        batch['status']['multichannel_enabled'] = False
        reader = FakeReadbackAPI(self.snapshot)
        reader.get_fmc_snapshot_batch = Mock(return_value=batch)
        with self.assertRaisesRegex(RuntimeError, 'topology changed'):
            self.collect(reader)
        self.assertEqual(reader.calls, [])

    def test_pa_and_missing_provenance_do_not_enter_batch(self):
        from oempa.pa_config import PAConfig
        from test_ui_phase2 import matching_pa
        reader = FakeReadbackAPI(matching_pa(PAConfig()))
        reader.get_fmc_snapshot_batch = Mock(side_effect=AssertionError('batch forbidden'))
        collect_snapshot(reader, 'fake', 'PA', dict(cycle_count=1, multichannel_supported=True, multichannel_enabled=False))
        reader.get_fmc_snapshot_batch.assert_not_called()
        reader = FakeReadbackAPI(self.snapshot)
        reader.get_fmc_snapshot_batch = Mock(side_effect=AssertionError('no eligible provenance'))
        collect_snapshot(reader, 'fake', 'FMC', self.status)
        reader.get_fmc_snapshot_batch.assert_not_called()

    def test_cancellation_after_native_return_blocks_field_assembly(self):
        reader = FakeReadbackAPI(self.snapshot)
        reader.get_fmc_snapshot_batch = Mock(return_value=self.batch())
        check = Mock(side_effect=[None, RuntimeError('cancelled')])
        with self.assertRaisesRegex(RuntimeError, 'cancelled'):
            collect_snapshot(reader, 'fake', 'FMC', self.status, check_cancelled=check, applied_configuration=self.provenance)
        self.assertEqual(reader.calls, [])
