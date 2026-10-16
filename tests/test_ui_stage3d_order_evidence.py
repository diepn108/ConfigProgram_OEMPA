"""Offline evidence checks; aggregate counters do not establish arrival order."""

from collections import Counter
import json
from pathlib import Path
import unittest

from tools.validate_phase5_stage3_acquisition import require_records


def counters(arrivals):
    counts = Counter(arrivals)
    return {
        "total": len(arrivals),
        "duplicates": sum(max(count - 1, 0) for cycle, count in counts.items() if 0 <= cycle < 256),
        "unexpected": sum(count for cycle, count in counts.items() if not 0 <= cycle < 256),
        "malformed": 0,
        "first_unexpected": next((cycle for cycle in arrivals if not 0 <= cycle < 256), -1),
        "cycle_counts": tuple(counts[cycle] for cycle in range(256)),
    }


class ArrivalEvidenceTests(unittest.TestCase):
    def test_saved_evidence_cannot_distinguish_precompletion_duplicate_from_spillover(self):
        report_path = Path(__file__).resolve().parents[1] / "artifacts/phase5_stage3d/validation.json"
        report = json.loads(report_path.read_text(encoding="utf-8"))
        ordered = list(range(256)) + list(range(28))
        # Both alternatives have the same first 252 unique records and final totals.
        precompletion = list(range(252)) + [0] + list(range(252, 256)) + list(range(1, 28))
        observed = {**report["callback_stats"], "cycle_counts": tuple(report["callback_stats"]["cycle_counts"])}
        self.assertEqual(counters(ordered), observed)
        self.assertEqual(counters(precompletion), observed)
        self.assertEqual(ordered[:252], precompletion[:252])
        self.assertEqual(report["poll_progress"][-1]["received"], 252)
        self.assertEqual(len(set(ordered[:256])), 256)
        self.assertEqual(len(set(precompletion[:256])), 255)
        for arrivals in (ordered, precompletion):
            with self.assertRaisesRegex(RuntimeError, "rejected"):
                require_records(counters(arrivals), complete=True)

    def test_all_cycle_counters_do_not_prove_ascending_order(self):
        ascending = list(range(256))
        swapped = [1, 0] + list(range(2, 256))
        self.assertEqual(counters(ascending), counters(swapped))
        require_records(counters(ascending), complete=True)
        # This is only aggregate acceptance, not proof of ordered sequence delivery.
        require_records(counters(swapped), complete=True)

    def test_precompletion_duplicate_missing_and_unexpected_stay_rejected(self):
        cases = [list(range(11)) + [5] + list(range(11, 256)), list(range(255)), list(range(256)) + [256]]
        for arrivals in cases:
            with self.subTest(arrivals=arrivals[-3:]), self.assertRaises(RuntimeError):
                require_records(counters(arrivals), complete=True)

    def test_malformed_record_stays_rejected(self):
        stats = counters(list(range(256)))
        stats["malformed"] = 1
        with self.assertRaisesRegex(RuntimeError, "rejected"):
            require_records(stats, complete=True)
