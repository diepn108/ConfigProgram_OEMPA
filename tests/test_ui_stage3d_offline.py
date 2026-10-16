"""Pure acceptance-counter tests: no SDK loading, device or real Tk window."""

import unittest
from tools.validate_phase5_stage3_acquisition import require_records
from oempa.fmc_acceptance import FMCFrameRejected


class RecordAcceptanceTests(unittest.TestCase):
    def test_aggregate_counts_alone_cannot_prove_immutable_first_frame(self):
        stats = self.stats(total=284, duplicates=28, cycle_counts=(2,) * 28 + (1,) * 228)
        with self.assertRaisesRegex(RuntimeError, 'rejected'):
            require_records(stats, complete=True)
        order = {'events': [{'kind': 'callback', 'cycle_id': i, 'malformed': False} for i in list(range(256)) + list(range(28))]}
        error = FMCFrameRejected('duplicate', stats, order)
        self.assertIn('Complete first sequence: Yes', str(error))
        self.assertIn('not accepted/saved', str(error))
        self.assertLess(len(str(error)), 700)
        self.assertIs(error.callback_order, order)

    def stats(self, **changes):
        return {"total": 256, "duplicates": 0, "unexpected": 0, "malformed": 0, "first_unexpected": -1, "cycle_counts": (1,) * 256, **changes}

    def test_exact_complete_sequence_and_partial_progress(self):
        require_records(self.stats(), complete=True)
        require_records(self.stats(total=16, cycle_counts=(1,) * 16 + (0,) * 240))

    def test_duplicates_unexpected_and_malformed_reject_without_retry(self):
        for changes in ({"duplicates": 1}, {"unexpected": 1, "first_unexpected": 256}, {"malformed": 1}, {"cycle_counts": (2,) + (1,) * 255}):
            with self.subTest(changes=changes), self.assertRaisesRegex(RuntimeError, "rejected"):
                require_records(self.stats(**changes))

    def test_missing_records_or_bad_total_block_completion(self):
        for changes in ({"cycle_counts": (1,) * 255 + (0,), "total": 255}, {"total": 257}):
            with self.subTest(changes=changes), self.assertRaisesRegex(RuntimeError, "Incomplete"):
                require_records(self.stats(**changes), complete=True)
