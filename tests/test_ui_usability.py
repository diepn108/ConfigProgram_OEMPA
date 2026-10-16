"""Pure diagnostics/probe provenance regressions; no native device imports."""

from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
import numpy as np

from oempa.ascan_config import SingleElementAscanConfig
from oempa.probe import PROBE_DEFAULTS, ProbeDescription, DOCUMENTED_MAPPING, MAPPING_SOURCE
from oempa.dataset import ProbeProvenance, capture_metadata, load_dataset, save_dataset
from ui.diagnostics import DiagnosticHistory, append_visible_log
from test_ui_single_ascan import matching


class UsabilityTests(unittest.TestCase):
    def test_documented_mapping_roundtrip_keeps_wiring_unvalidated(self):
        probe = ProbeProvenance(identity=PROBE_DEFAULTS['full_marking'], description=ProbeDescription.from_values(PROBE_DEFAULTS),
                                logical_to_physical=DOCUMENTED_MAPPING, mapping_source=MAPPING_SOURCE,
                                usable_element_count=16, aperture_span_mm=9.0)
        config = SingleElementAscanConfig()
        data = np.zeros(751, dtype=np.int8)
        metadata = capture_metadata(data, matching(config), 9, config,
                                    SimpleNamespace(point_count=751, data_size=1, signed=True, bit_size=0), probe=probe)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'synthetic.npy'
            save_dataset(path, data, metadata)
            loaded = load_dataset(path)
        self.assertEqual(loaded.metadata.probe, probe)
        self.assertFalse(loaded.metadata.probe.mapping_verified)
        self.assertEqual(loaded.metadata.probe.physical_wiring_validation, 'Not independently tested')

    def test_probe_description_roundtrips_without_hardware_or_mapping_claim(self):
        probe = ProbeProvenance(identity=PROBE_DEFAULTS['full_marking'], description=ProbeDescription.from_values(PROBE_DEFAULTS))
        config = SingleElementAscanConfig()
        data = np.zeros(751, dtype=np.int8)
        metadata = capture_metadata(data, matching(config), 9, config,
                                    SimpleNamespace(point_count=751, data_size=1, signed=True, bit_size=0), probe=probe)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'synthetic.npy'
            save_dataset(path, data, metadata)
            loaded = load_dataset(path)
        self.assertEqual(loaded.metadata.probe, probe)
        self.assertFalse(loaded.metadata.probe.identity_verified)
        self.assertFalse(loaded.metadata.probe.mapping_verified)
        self.assertEqual(dict(loaded.metadata.probe.description.values)['elements'], '32')
        self.assertEqual(loaded.metadata.hardware.cycle_count, 1)
        self.assertEqual(loaded.metadata.hardware.cycles[0].tx_aperture, (0,))

    def test_scrolling_history_does_not_force_scroll_to_bottom(self):
        widget = Mock()
        widget.yview.return_value = (.1, .4)
        history = DiagnosticHistory()
        self.assertEqual(append_visible_log(widget, history, '[OK] One', 0), 1)
        widget.see.assert_not_called()
        widget.yview.return_value = (.9, 1.0)
        append_visible_log(widget, history, '[OK] Two', 1)
        widget.see.assert_called_once_with('end')
        self.assertEqual([record[0] for record in history.records], [1, 2])

    def test_log_bounds_and_full_message_are_distinct(self):
        widget = Mock()
        widget.yview.return_value = (0.0, 1.0)
        history = DiagnosticHistory(capacity=2)
        lines = 0
        for message in ('[INFO] One', '[WARN] Two', '[ERROR] ' + 'x'*6000):
            lines = append_visible_log(widget, history, message, lines, limit=2)
        self.assertEqual(lines, 2)
        self.assertEqual(len(history.records), 2)
        self.assertEqual(history.total_messages, 3)
        self.assertEqual(len(widget.insert.call_args.args[1]), 4001)
        self.assertGreater(len(history.records[-1][1]), 6000)
        widget.delete.assert_called_once_with('1.0', '2.0')
