from __future__ import annotations

import unittest
from unittest.mock import patch

import numpy as np

from src import correlaciones as corr
from src.indices import InputDataError


class DeterministicSampleTest(unittest.TestCase):
    def test_keeps_aligned_arrays_and_requested_size(self) -> None:
        x = np.arange(100)
        y = x * 2
        sampled_x, sampled_y = corr.deterministic_sample(x, y, max_items=10)
        self.assertEqual(len(sampled_x), 10)
        np.testing.assert_array_equal(sampled_y, sampled_x * 2)
        self.assertEqual(sampled_x[0], 0)
        self.assertEqual(sampled_x[-1], 99)

    def test_rejects_different_lengths(self) -> None:
        with self.assertRaises(ValueError):
            corr.deterministic_sample(np.arange(3), np.arange(2), max_items=2)


class CorrelationResultTest(unittest.TestCase):
    def test_perfect_linear_relationship(self) -> None:
        x = np.arange(1, 20, dtype=float)
        y = 3 * x + 2
        pearson, _ = corr.correlation_result(x, y, "pearson")
        spearman, _ = corr.correlation_result(x, y, "spearman")
        self.assertAlmostEqual(pearson, 1.0)
        self.assertAlmostEqual(spearman, 1.0)

    def test_constant_input_is_indeterminate(self) -> None:
        coefficient, p_value = corr.correlation_result(
            np.ones(5), np.arange(5, dtype=float), "pearson"
        )
        self.assertTrue(np.isnan(coefficient))
        self.assertTrue(np.isnan(p_value))

    def test_labels_direction_and_magnitude(self) -> None:
        self.assertEqual(corr.correlation_label(-0.42), ("negativa", "moderada"))
        self.assertEqual(corr.correlation_label(0.75), ("positiva", "muy_fuerte"))
        self.assertEqual(corr.correlation_label(0.02), ("positiva", "muy_debil"))

    def test_underflow_p_value_is_not_reported_as_exact_zero(self) -> None:
        self.assertEqual(corr._format_p_value(0.0), "<1e-300")


class PairedValuesTest(unittest.TestCase):
    def test_uses_only_simultaneously_valid_pixels(self) -> None:
        scene = {
            "lago": "amatitlan",
            "profile": {},
            "arrays": {
                "cianobacteria": np.array([[1.0, 2.0], [3.0, np.nan]]),
                "ndvi": np.array([[0.1, np.nan], [0.3, 0.4]]),
                "ndwi": np.zeros((2, 2)),
            },
        }
        geometry_and_cyano = np.array([[True, True], [False, False]])
        with patch.object(corr, "combined_valid_mask", return_value=geometry_and_cyano):
            x, y = corr.paired_values(scene, "ndvi")
        np.testing.assert_array_equal(x, np.array([1.0]))
        np.testing.assert_array_equal(y, np.array([0.1]))


class DistributionStatsTest(unittest.TestCase):
    def test_summarizes_only_finite_values(self) -> None:
        stats = corr.distribution_stats(np.array([1.0, 2.0, 3.0, np.nan]))
        self.assertEqual(stats["n_pixeles"], 3)
        self.assertEqual(stats["media"], 2.0)
        self.assertEqual(stats["mediana"], 2.0)

    def test_empty_distribution_raises(self) -> None:
        with self.assertRaises(InputDataError):
            corr.distribution_stats(np.array([np.nan]))

    def test_scene_distribution_uses_all_common_masks(self) -> None:
        scene = {
            "lago": "amatitlan",
            "profile": {},
            "arrays": {
                "cianobacteria": np.array([[1.0, 2.0, 3.0]]),
                "ndvi": np.array([[0.1, np.nan, 0.3]]),
                "ndwi": np.array([[0.4, 0.5, np.nan]]),
            },
        }
        with patch.object(
            corr, "combined_valid_mask", return_value=np.array([[True, True, True]])
        ):
            values = corr.scene_distribution_values(scene)
        np.testing.assert_array_equal(values, np.array([1.0]))


class SelectDistributionDatesTest(unittest.TestCase):
    def test_uses_predeclared_selection_rules_and_merges_reasons(self) -> None:
        temporal = [
            {
                "lago": lago,
                "fecha": fecha,
                "cyano_promedio": mean,
                "quality_flag": "calculado",
            }
            for lago in ("amatitlan", "atitlan")
            for fecha, mean in (
                ("2025-01-01", "1"),
                (corr.FECHA_COMUN_LAGOS, "5"),
                ("2026-06-01", "8"),
            )
        ]
        extension = [
            {"lago": lago, "fecha": "2026-06-01", "porcentaje_alto": "25"}
            for lago in ("amatitlan", "atitlan")
        ]
        selected = corr.select_distribution_dates(temporal, extension)
        for lago in selected:
            self.assertIn("referencia_primera_fecha_completa", selected[lago]["2025-01-01"])
            self.assertIn("pico_promedio_temporal", selected[lago]["2026-06-01"])
            self.assertIn("mayor_extension", selected[lago]["2026-06-01"])
            self.assertEqual(
                selected[lago][corr.FECHA_COMUN_LAGOS], "fecha_comun_entre_lagos"
            )


class DifferenceRasterTest(unittest.TestCase):
    def test_subtracts_final_minus_initial_on_common_mask(self) -> None:
        profile = {"crs": "EPSG:32615", "transform": "same", "width": 2, "height": 1}
        initial = {
            "lago": "amatitlan",
            "profile": profile,
            "arrays": {
                "cianobacteria": np.array([[1.0, 2.0]]),
                "ndvi": np.array([[0.1, 0.2]]),
                "ndwi": np.array([[0.3, 0.4]]),
            },
        }
        final = {
            "lago": "amatitlan",
            "profile": profile,
            "arrays": {
                "cianobacteria": np.array([[4.0, 8.0]]),
                "ndvi": np.array([[0.1, 0.2]]),
                "ndwi": np.array([[0.3, 0.4]]),
            },
        }
        with (
            patch.object(corr, "load_scene_indices", side_effect=[initial, final]),
            patch.object(corr, "combined_valid_mask", return_value=np.array([[True, False]])),
        ):
            result = corr.difference_raster("amatitlan", "inicio", "fin", rows=[])
        self.assertEqual(result["difference"][0, 0], 3.0)
        self.assertTrue(np.isnan(result["difference"][0, 1]))
        self.assertEqual(result["n_pares"], 1)

    def test_rejects_different_grids(self) -> None:
        first = {
            "profile": {"crs": "A", "transform": "x", "width": 1, "height": 1},
            "arrays": {"cianobacteria": np.ones((1, 1))},
        }
        second = {
            "profile": {"crs": "A", "transform": "y", "width": 1, "height": 1},
            "arrays": {"cianobacteria": np.ones((1, 1))},
        }
        with patch.object(corr, "load_scene_indices", side_effect=[first, second]):
            with self.assertRaises(InputDataError):
                corr.difference_raster("amatitlan", "inicio", "fin", rows=[])


if __name__ == "__main__":
    unittest.main()
