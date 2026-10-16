"""Pure synthetic display tests; no native SDK, device or real Tk imports."""

import unittest
import numpy as np
from ui.fmc_inspection import display_traces


class DisplayProcessingTests(unittest.TestCase):
    def setUp(self):
        self.raw = np.array([[-128, 64, 0, 1], [-8, 4, 0, 1], [0, 0, 0, 0]], dtype=np.int8)

    def test_no_normalization_preserves_signed_samples_and_raw(self):
        result = display_traces(self.raw)
        np.testing.assert_array_equal(result.data, self.raw)
        self.assertFalse(np.shares_memory(result.data, self.raw))
        self.assertFalse(result.data.flags.writeable)
        self.assertEqual(result.limit, 128)

    def test_absolute_signed_minimum_has_no_integer_overflow(self):
        result = display_traces(self.raw, 'Absolute')
        self.assertEqual(result.data[0, 0], 128)
        self.assertTrue(np.all(result.data >= 0))

    def test_global_preserves_channel_ratios(self):
        result = display_traces(self.raw, normalization='Global')
        self.assertEqual(result.data[0, 0], -1)
        self.assertEqual(result.data[1, 0], -1 / 16)
        self.assertEqual(result.limit, 1)

    def test_per_trace_scales_each_channel_without_dividing_zero(self):
        result = display_traces(self.raw, normalization='Per trace')
        np.testing.assert_array_equal(result.data[:2, :2], [[-1, .5], [-1, .5]])
        np.testing.assert_array_equal(result.data[2], np.zeros(4))
        self.assertTrue(np.all(np.isfinite(result.data)))

    def test_weak_contrast_preserves_sign_and_increases_relative_visibility(self):
        linear = display_traces(self.raw, normalization='Global')
        boosted = display_traces(self.raw, normalization='Global', contrast='Boost weak (sqrt)')
        self.assertGreater(boosted.data[0, 3], linear.data[0, 3])
        self.assertLess(boosted.data[1, 0], 0)
        self.assertEqual(boosted.data[0, 0], -1)

    def test_normalization_uses_only_selected_gate_samples(self):
        result = display_traces(self.raw[:, 1:], 'Absolute', 'Per trace')
        self.assertEqual(result.data[0, 0], 1)
        self.assertEqual(result.data[1, 0], 1)
        self.assertEqual(result.data[1, 2], .25)

    def test_every_option_leaves_source_bytes_identical(self):
        original = self.raw.tobytes()
        for mode in ('RF', 'Absolute'):
            for normalization in ('None', 'Global', 'Per trace'):
                for contrast in ('Linear', 'Boost weak (sqrt)'):
                    result = display_traces(self.raw, mode, normalization, contrast)
                    self.assertIn('display processing only', result.description)
                    self.assertEqual(self.raw.tobytes(), original)

    def test_zero_traces_have_finite_display_scale(self):
        for normalization in ('None', 'Global', 'Per trace'):
            result = display_traces(np.zeros((16, 1)), 'Absolute', normalization, 'Boost weak (sqrt)')
            self.assertEqual(result.limit, 1)
            np.testing.assert_array_equal(result.data, np.zeros((16, 1)))

    def test_invalid_options_and_nonfinite_or_empty_data_rejected(self):
        for data in (np.zeros((16, 0)), np.array([[np.nan]]), np.array([[np.inf]]), np.array([[1j]]), np.zeros(16)):
            with self.assertRaises(ValueError):
                display_traces(data)
        for kwargs in ({'normalization': 'unknown'}, {'contrast': 'unknown'}, {'representation': 'unknown'}):
            with self.assertRaises(ValueError):
                display_traces(self.raw, **kwargs)
