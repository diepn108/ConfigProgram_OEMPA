"""TFM mathematics, deterministic synthetic localization and provenance; no SDK."""

from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from oempa.dataset import AcquisitionDataset, ProbeProvenance
from oempa.probe import ProbeDescription, PROBE_DEFAULTS, DOCUMENTED_MAPPING, MAPPING_SOURCE
from oempa.tfm import ImageGrid, LinearGeometry, TimingAssumption, TFMRequest, dataset_geometry, display_image, reconstruct, result_metadata, save_result
from tfm_synthetic import point_reflector, synthetic_source


class TFMTests(unittest.TestCase):
    def test_sixteen_active_geometry_from_thirty_two_element_probe_label(self):
        source = synthetic_source(np.zeros((16, 16, 64), dtype=np.int8), 25e6)
        probe = ProbeProvenance(description=ProbeDescription.from_values(PROBE_DEFAULTS), logical_to_physical=DOCUMENTED_MAPPING, mapping_source=MAPPING_SOURCE)
        source = AcquisitionDataset(source.data, replace(source.metadata, probe=probe))
        geometry, origin = dataset_geometry(source)
        self.assertEqual(geometry.element_count, 16)
        np.testing.assert_allclose(geometry.positions_m[[0, -1]] * 1e3, [-4.5, 4.5], atol=1e-12)
        np.testing.assert_allclose(np.diff(geometry.positions_m) * 1e3, .6, atol=1e-12)
        self.assertIn('user_supplied_label', origin)
        self.assertIn('not independently calibrated', origin)

    def test_missing_invalid_dataset_pitch_never_uses_probe_gui_defaults(self):
        source = synthetic_source(np.zeros((16, 16, 64), dtype=np.int8), 25e6)
        self.assertIsNone(dataset_geometry(source)[0])
        for pitch in ('0', '-.6', 'nan', 'inf', 'unknown'):
            probe = ProbeProvenance(description=ProbeDescription.from_values({**PROBE_DEFAULTS, 'pitch': pitch}))
            with self.subTest(pitch=pitch), self.assertRaises(ValueError):
                dataset_geometry(AcquisitionDataset(source.data, replace(source.metadata, probe=probe)))

    def test_known_all_pair_distances_start_and_linear_sample_coordinates(self):
        rate, start, velocity = 25e6, 2e-6, 1480
        data = np.broadcast_to(np.arange(1000, dtype=float), (16, 16, 1000)).copy()
        source = synthetic_source(data, rate, start)
        geometry = LinearGeometry(16, .0006)
        grid = ImageGrid(.001, .002, 2, .008, .009, 2)
        result = reconstruct(source, TFMRequest(geometry, velocity, grid, 'linear'))
        for iz, z in enumerate(result.z_m):
            for ix, x in enumerate(result.x_m):
                expected = sum(((np.hypot(x - a, z) + np.hypot(x - b, z)) / velocity - start) * rate for a in geometry.positions_m for b in geometry.positions_m)
                self.assertAlmostEqual(result.image[iz, ix], expected, places=7)

    def test_all_256_pair_weights_contribute_not_only_diagonal(self):
        data = np.broadcast_to(np.arange(1, 257).reshape(16, 16, 1), (16, 16, 64)).copy()
        source = synthetic_source(data, 1e6)
        result = reconstruct(source, TFMRequest(LinearGeometry(16, .0006), 1480, ImageGrid(-.001, .001, 3, .002, .004, 3), 'linear'))
        np.testing.assert_allclose(result.image, sum(range(1, 257)))
        self.assertNotEqual(result.image[1, 1], sum(data[e, e, 0] for e in range(16)))

    def test_off_diagonal_only_synthetic_point_localizes_with_linear_interpolation(self):
        source = point_reflector(16, .0006, 1480, .001, .012, 100e6, 1e-6, 3001)
        for e in range(16):
            source.data[e, e] = 0
        result = reconstruct(source, TFMRequest(LinearGeometry(16, .0006), 1480, ImageGrid(-.004, .004, 81, .01, .014, 81), 'linear'))
        iz, ix = np.unravel_index(np.argmax(np.abs(result.image)), result.image.shape)
        self.assertLessEqual(abs(result.x_m[ix] - .001), .0001)
        self.assertLessEqual(abs(result.z_m[iz] - .012), .00005)
        self.assertGreater(result.image[iz, ix], 100)

    def test_on_axis_symmetric_aperture_has_symmetric_image(self):
        source = point_reflector(16, .0006, 1480, 0, .012, 100e6, 0, 3001)
        result = reconstruct(source, TFMRequest(LinearGeometry(16, .0006), 1480, ImageGrid(-.004, .004, 81, .01, .014, 81), 'linear'))
        np.testing.assert_allclose(result.image, result.image[:, ::-1], atol=1e-8)

    def test_numerical_result_save_includes_model_geometry_and_original_provenance(self):
        source = synthetic_source(np.full((16, 16, 100), -7, dtype=np.int8), 1e6, 1e-6)
        probe = ProbeProvenance(description=ProbeDescription.from_values(PROBE_DEFAULTS), logical_to_physical=DOCUMENTED_MAPPING, mapping_source=MAPPING_SOURCE)
        source = AcquisitionDataset(source.data, replace(source.metadata, probe=probe))
        geometry, origin = dataset_geometry(source)
        result = reconstruct(source, TFMRequest(geometry, 1480, ImageGrid(-.001, .001, 3, .002, .004, 3), 'linear', geometry_origin=origin))
        before = source.data.copy()
        display_image(result, 'normalized')
        display_image(result, 'db')
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'tfm.npz'
            save_result(path, result)
            with np.load(path, allow_pickle=False) as loaded:
                np.testing.assert_array_equal(loaded['image'], result.image)
                np.testing.assert_array_equal(loaded['element_x_m'], geometry.positions_m)
                metadata = json.loads(str(loaded['metadata_json']))
        self.assertEqual(metadata['propagation_model'], 'Homogeneous medium')
        self.assertEqual(metadata['active_elements'], 16)
        self.assertEqual(metadata['source_shape'], [16, 16, 100])
        self.assertEqual(metadata['source_configuration_revision'], 12)
        self.assertEqual(metadata['request']['method'], 'linear')
        self.assertEqual(metadata['mapping_source'], MAPPING_SOURCE)
        self.assertEqual(metadata['physical_wiring_validation'], 'Not independently tested')
        self.assertFalse(metadata['mapping_verified'])
        self.assertEqual(metadata['start_s'], 1e-6)
        self.assertEqual(result_metadata(result)['source_metadata']['buffer_source'], source.metadata.buffer_source)
        np.testing.assert_array_equal(source.data, before)
        self.assertTrue(np.all(result.image < 0))

    def setUp(self):
        self.geometry = LinearGeometry(8, .0006)
        self.grid = ImageGrid(-.004, .004, 81, .004, .012, 81)
        self.request = TFMRequest(self.geometry, 3000, self.grid)

    def assert_localized(self, x, z, pitch=.0006, rate=25e6, start=0, method="nearest"):
        source = point_reflector(8, pitch, 3000, x, z, rate, start)
        request = replace(self.request, geometry=LinearGeometry(8, pitch), method=method)
        result = reconstruct(source, request)
        iz, ix = np.unravel_index(np.argmax(np.abs(result.image)), result.image.shape)
        self.assertLessEqual(abs(result.x_m[ix] - x), .0001)
        self.assertLessEqual(abs(result.z_m[iz] - z), .0001)
        if method == "nearest":
            self.assertEqual(result.image[iz, ix], 64)
        return source, result

    def test_centered_point_reflector(self):
        self.assert_localized(0, .008)

    def test_off_axis_point_reflector(self):
        self.assert_localized(.002, .008)

    def test_nondefault_sampling_frequency(self):
        self.assert_localized(-.001, .009, rate=40e6)

    def test_nonzero_acquisition_start(self):
        self.assert_localized(.001, .008, rate=25e6, start=2e-6)

    def test_different_pitch(self):
        self.assert_localized(-.002, .01, pitch=.0009)

    def test_linear_reflector(self):
        self.assert_localized(.002, .008, method="linear")

    def test_nearest_half_up_and_window_exclusion(self):
        source = synthetic_source(np.array([[[2, 4, 8]]], dtype=np.int8), 1e6, 1e-6)
        # x=0 column: q = -0.25, 0.25, 0.75, 1.25, 1.75, 2.25.
        request = TFMRequest(LinearGeometry(1, .001), 2000, ImageGrid(-1e-6, 1e-6, 3, .00075, .00325, 6))
        result = reconstruct(source, request)
        np.testing.assert_equal(result.image[:, 1], [0, 2, 4, 4, 8, 0])
        # An exact half sample rounds up, rather than ties-to-even.
        request = replace(request, grid=ImageGrid(-1e-6, 1e-6, 3, .0015, .0025, 2))
        np.testing.assert_equal(reconstruct(source, request).image[:, 1], [4, 8])

    def test_linear_interpolation_and_last_sample(self):
        source = synthetic_source(np.array([[[0, 10, 20, 30]]]), 1e6)
        request = TFMRequest(LinearGeometry(1, .001), 2000, ImageGrid(-1e-6, 1e-6, 3, 0, .003, 7), "linear")
        np.testing.assert_allclose(reconstruct(source, request).image[:, 1], [0, 5, 10, 15, 20, 25, 30])

    def test_single_sample_has_no_extrapolation(self):
        source = synthetic_source(np.array([[[7]]]), 1e6)
        request = TFMRequest(LinearGeometry(1, .001), 2000, ImageGrid(-1e-6, 1e-6, 3, 0, .001, 2), "linear")
        np.testing.assert_equal(reconstruct(source, request).image[:, 1], [7, 0])

    def test_invalid_velocity_and_geometry(self):
        source = point_reflector(8, .0006, 3000, 0, .008, 25e6)
        for value in (0, -1, np.nan, np.inf):
            with self.subTest(value=value), self.assertRaises(ValueError):
                reconstruct(source, replace(self.request, velocity_m_s=value))
            with self.subTest(pitch=value), self.assertRaises(ValueError):
                reconstruct(source, replace(self.request, geometry=LinearGeometry(8, value)))

    def test_invalid_grid(self):
        source = point_reflector(8, .0006, 3000, 0, .008, 25e6)
        for grid in (replace(self.grid, x_count=0), replace(self.grid, z_count=1), replace(self.grid, x_count=2.5), replace(self.grid, x_min_m=.01), replace(self.grid, z_min_m=-.001), replace(self.grid, z_max_m=np.nan), replace(self.grid, x_count=1001, z_count=1000)):
            with self.subTest(grid=grid), self.assertRaises(ValueError):
                reconstruct(source, replace(self.request, grid=grid))

    def test_inconsistent_fmc_geometry_or_metadata(self):
        source = point_reflector(8, .0006, 3000, 0, .008, 25e6)
        with self.assertRaises(ValueError):
            reconstruct(source, replace(self.request, geometry=LinearGeometry(7, .0006)))
        for data in (source.data[:7], source.data[:, :, :0], source.data[0], source.data.astype(complex)):
            with self.subTest(shape=data.shape), self.assertRaises(ValueError):
                reconstruct(AcquisitionDataset(data, source.metadata), self.request)
        with self.assertRaises(ValueError):
            reconstruct(AcquisitionDataset(source.data, replace(source.metadata, shape=(8, 8, 5))), self.request)

    def test_inconsistent_cycle_timing_is_rejected(self):
        source = point_reflector(8, .0006, 3000, 0, .008, 25e6)
        hardware = source.metadata.hardware
        altered = (replace(hardware.cycles[0], start_s=1e-6),) + hardware.cycles[1:]
        bad = replace(source.metadata, hardware=replace(hardware, cycles=altered))
        with self.assertRaises(ValueError):
            reconstruct(AcquisitionDataset(source.data, bad), self.request)

    def test_legacy_assumptions_separate_from_metadata(self):
        source = point_reflector(8, .0006, 3000, 0, .008, 25e6, 2e-6)
        legacy = AcquisitionDataset(source.data, replace(source.metadata, complete=False, hardware=None, configuration_revision=None))
        with self.assertRaises(ValueError):
            reconstruct(legacy, self.request)
        result = reconstruct(legacy, replace(self.request, timing_assumption=TimingAssumption(25e6, 2e-6)))
        self.assertIs(result.source_metadata, legacy.metadata)
        self.assertIsNone(result.source_metadata.hardware)
        self.assertIn("user assumption", result.timing_origin)
        self.assertIsNone(result.configuration_revision)
        with self.assertRaises(ValueError):
            reconstruct(source, replace(self.request, timing_assumption=TimingAssumption(25e6, 0)))

    def test_signed_sum_no_integer_overflow_and_display_separation(self):
        source = synthetic_source(np.full((8, 8, 2048), -127, dtype=np.int8), 25e6)
        before = source.data.copy()
        result = reconstruct(source, self.request)
        np.testing.assert_equal(result.image, -8128)
        self.assertIs(result.source_metadata, source.metadata)
        self.assertEqual(result.configuration_revision, 12)
        self.assertFalse(result.mapping_verified)
        self.assertFalse(result.image.flags.writeable)
        for mode in ("raw", "absolute", "normalized", "db"):
            view = display_image(result, mode)
            self.assertTrue(np.isfinite(view.values).all())
        np.testing.assert_equal(source.data, before)
        np.testing.assert_equal(result.image, -8128)

    def test_zero_image_db_is_finite_floor(self):
        source = synthetic_source(np.zeros((8, 8, 100)), 25e6)
        result = reconstruct(source, self.request)
        np.testing.assert_equal(display_image(result, "db").values, -60)
        np.testing.assert_equal(display_image(result, "normalized").values, 0)
        with self.assertRaises(ValueError):
            display_image(result, "db", db_floor=0)

    def test_db_reference_is_twenty_log_of_magnitude(self):
        source = synthetic_source(np.zeros((8, 8, 100)), 25e6)
        result = reconstruct(source, self.request)
        result = replace(result, image=np.array([[-1., .1, .01, 0]]))
        np.testing.assert_allclose(display_image(result, "db").values, [[0, -20, -40, -60]])
        np.testing.assert_allclose(display_image(result, "normalized").values, [[1, .1, .01, 0]])

    def test_invalid_timing_method_or_samples(self):
        source = point_reflector(8, .0006, 3000, 0, .008, 25e6)
        legacy = AcquisitionDataset(source.data, replace(source.metadata, complete=False, hardware=None))
        for rate, start in ((0, 0), (-1, 0), (np.nan, 0), (np.inf, 0), (25e6, np.nan)):
            with self.subTest(rate=rate, start=start), self.assertRaises(ValueError):
                reconstruct(legacy, replace(self.request, timing_assumption=TimingAssumption(rate, start)))
        with self.assertRaises(ValueError):
            reconstruct(source, replace(self.request, method="cubic"))
        bad = source.data.copy()
        bad[0, 0, 0] = np.nan
        with self.assertRaises(ValueError):
            reconstruct(AcquisitionDataset(bad, source.metadata), self.request)
        with self.assertRaises(ValueError):
            reconstruct(AcquisitionDataset(source.data, replace(source.metadata, axis_names=("sample", "TX", "RX"))), self.request)

    def test_geometry_coordinates_centered_and_retained(self):
        source, result = self.assert_localized(0, .008)
        np.testing.assert_allclose(result.element_x_m, [-.0021, -.0015, -.0009, -.0003, .0003, .0009, .0015, .0021])
        self.assertEqual(result.pitch_m, .0006)
        self.assertEqual(result.velocity_m_s, 3000)
        self.assertIn("Unverified", " ".join(result.warnings))

    def test_progress_cancellation_and_chunk_invariance(self):
        source = point_reflector(8, .0006, 3000, 0, .008, 25e6)
        progress = []
        first = reconstruct(source, self.request, chunk_size=256, progress=lambda done, total: progress.append((done, total)))
        second = reconstruct(source, self.request, chunk_size=1500)
        np.testing.assert_equal(first.image, second.image)
        self.assertEqual(progress[-1], (81 * 81, 81 * 81))
        progress.clear()
        def cancel():
            if progress:
                raise InterruptedError("cancelled")
        with self.assertRaises(InterruptedError):
            reconstruct(source, self.request, cancel_check=cancel, progress=lambda done, total: progress.append((done, total)))


if __name__ == "__main__":
    unittest.main()
