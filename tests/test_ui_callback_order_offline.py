"""Synthetic native bookkeeping only; executable has no SDK/device linkage."""

import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from oempa.callback_order import decode_callback_order


class CallbackOrderTests(unittest.TestCase):
    def evidence(self, scenario):
        executable = Path(__file__).with_name("callback_order_native.exe")
        result = subprocess.run([str(executable), scenario], capture_output=True, text=True, check=True)
        raw = json.loads(result.stdout)
        return decode_callback_order(raw["rows"], raw["summary"], raw["first"])

    def test_distinguishes_duplicate_before_and_after_complete_boundary(self):
        late, early = self.evidence("late"), self.evidence("early")
        self.assertLess(late["unique_complete_event"], late["first_duplicate_event"])
        self.assertGreater(early["unique_complete_event"], early["first_duplicate_event"])
        self.assertEqual(late["first_occurrence_arrivals"], list(range(1, 257)))
        self.assertEqual(early["first_occurrence_arrivals"][12], 14)
        for evidence, cycles in ((late, list(range(256)) + list(range(28))), (early, list(range(12)) + [0] + list(range(12, 256)))):
            callbacks = [event for event in evidence["events"] if event["kind"] == "callback"]
            self.assertEqual([event["cycle_id"] for event in callbacks], cycles)
            self.assertEqual([event["arrival_index"] for event in callbacks], list(range(1, len(cycles) + 1)))

    def test_lifecycle_and_headers_round_trip_in_json_artifact(self):
        evidence = self.evidence("late")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "diagnostic.json"
            path.write_text(json.dumps({"callback_order": evidence}), encoding="utf-8")
            self.assertEqual(json.loads(path.read_text())["callback_order"], evidence)
        events = evidence["events"]
        indices = [event["event_index"] for event in events]
        self.assertEqual(indices, sorted(set(indices)))
        kinds = [event["kind"] for event in events]
        for name in ("on_requested", "on_returned", "first_callback", "unique_required_ids_reached", "first_duplicate", "off_requested", "off_call_entered", "off_call_returned", "final_callback_observed"):
            self.assertIn(name, kinds)
        self.assertLess(kinds.index("first_callback"), kinds.index("on_returned"))
        self.assertLess(kinds.index("off_call_entered"), kinds.index("first_duplicate"))
        self.assertEqual(events[-1]["arrival_index"], 284)
        header = next(event for event in events if event["kind"] == "callback")
        self.assertEqual((header["sample_count"], header["data_size"], header["signed"], header["bit_size"], header["malformed"]), (3001, 1, True, 0, False))

    def test_later_callbacks_never_overwrite_first_occurrence_indices(self):
        exact, late, overflow = (self.evidence(name) for name in ("exact", "late", "overflow"))
        self.assertEqual(exact["first_occurrence_events"], late["first_occurrence_events"])
        self.assertEqual(exact["first_occurrence_events"], overflow["first_occurrence_events"])

    def test_callback_and_marker_capacity_are_bounded_with_explicit_loss(self):
        evidence = self.evidence("overflow")
        self.assertTrue(evidence["overflow"])
        self.assertEqual(sum(event["kind"] == "callback" for event in evidence["events"]), 512)
        self.assertEqual(evidence["dropped_callbacks"], 344)
        self.assertIn("off_call_returned", [event["kind"] for event in evidence["events"]])
        markers = self.evidence("markers")
        self.assertEqual(sum(event["kind"] != "callback" for event in markers["events"]), 64)
        self.assertGreater(markers["dropped_markers"], 0)
        self.assertLessEqual(markers["stored_events"], 576)

    def test_invalid_header_representation_is_visible_without_accepting_it(self):
        callbacks = [event for event in self.evidence("malformed")["events"] if event["kind"] == "callback"]
        self.assertTrue(all(event["malformed"] for event in callbacks[-3:]))
        self.assertTrue(callbacks[-3]["unexpected"])
        self.assertTrue(callbacks[-2]["duplicate"])
