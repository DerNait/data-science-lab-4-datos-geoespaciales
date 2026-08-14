from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from src import analisis_temporal as at
from src import indices


def _write_raster(path: Path, array: np.ndarray) -> None:
    import rasterio
    from rasterio.transform import from_origin

    path.parent.mkdir(parents=True, exist_ok=True)
    transform = from_origin(-90.6, 14.5, 0.0001, 0.0001)
    profile = {
        "driver": "GTiff",
        "height": array.shape[0],
        "width": array.shape[1],
        "count": 1,
        "dtype": "float32",
        "crs": "EPSG:4326",
        "transform": transform,
    }
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(array.astype("float32"), 1)


def _manifest_row(*, lago="amatitlan", fecha="2025-01-28", quality_flag="calculado", ruta_raster="indices/x.tif"):
    return {
        "lago": lago,
        "fecha": fecha,
        "indice": "cianobacteria",
        "ruta_raster": ruta_raster,
        "metodo": "m",
        "formula_version": "v1",
        "unidad": "ug/L",
        "dtype": "float32",
        "nodata": "nan",
        "crs": "EPSG:4326",
        "resolucion_m": "10",
        "pixeles_validos": "3",
        "pixeles_lago": "4",
        "cobertura_valida_pct": "75.0",
        "quality_flag": quality_flag,
    }


class SplitReadyPendingTest(unittest.TestCase):
    def test_pending_rows_are_excluded_from_ready(self) -> None:
        rows = [
            _manifest_row(fecha="2025-01-28", quality_flag="calculado", ruta_raster="a.tif"),
            _manifest_row(fecha="2025-04-15", quality_flag="pendiente_calculo", ruta_raster=""),
        ]
        ready, pending = at.split_ready_pending(rows)
        self.assertEqual(len(ready), 1)
        self.assertEqual(len(pending), 1)
        self.assertEqual(ready[0]["fecha"], "2025-01-28")

    def test_row_without_path_counts_as_pending_even_if_flagged_calculado(self) -> None:
        rows = [_manifest_row(quality_flag="calculado", ruta_raster="")]
        ready, pending = at.split_ready_pending(rows)
        self.assertEqual(ready, [])
        self.assertEqual(len(pending), 1)

    def test_pending_report_counts_against_official_scene_total(self) -> None:
        rows = [_manifest_row(fecha="2025-01-28", quality_flag="calculado", ruta_raster="a.tif")]
        report = at.pending_report(rows)
        self.assertEqual(report["total_escenas"], 22)
        self.assertEqual(report["listas"], 1)
        self.assertEqual(report["pendientes"], 0)


class ValidateIndicesManifestReadyTest(unittest.TestCase):
    def test_missing_field_on_ready_row_raises(self) -> None:
        rows = [_manifest_row(quality_flag="calculado", ruta_raster="a.tif")]
        rows[0]["cobertura_valida_pct"] = ""
        with self.assertRaises(indices.InputDataError):
            at.validate_indices_manifest_ready(rows)

    def test_pending_row_with_missing_fields_does_not_raise(self) -> None:
        rows = [_manifest_row(quality_flag="pendiente_calculo", ruta_raster="")]
        rows[0]["cobertura_valida_pct"] = ""
        at.validate_indices_manifest_ready(rows)  # no debe lanzar


class ComputeRowStatsTest(unittest.TestCase):
    def test_reads_raster_and_matches_summarize_array(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raster_path = root / "indices" / "amatitlan" / "2025-01-28" / "cianobacteria.tif"
            array = np.array([[5.0, np.nan], [8.0, 6.0]], dtype=np.float32)
            _write_raster(raster_path, array)

            row = _manifest_row(ruta_raster="indices/amatitlan/2025-01-28/cianobacteria.tif")
            stats = at.compute_row_stats(row, raiz=root)
            self.assertEqual(stats["valid_pixels"], 3)
            self.assertAlmostEqual(stats["mean"], (5.0 + 8.0 + 6.0) / 3, places=5)

    def test_missing_raster_file_raises_input_data_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            row = _manifest_row(ruta_raster="indices/no_existe.tif")
            with self.assertRaises(indices.InputDataError):
                at.compute_row_stats(row, raiz=Path(tmp))

    def test_empty_path_raises_input_data_error(self) -> None:
        row = _manifest_row(ruta_raster="")
        with self.assertRaises(indices.InputDataError):
            at.compute_row_stats(row, raiz=Path("."))


class BuildResumenTemporalTest(unittest.TestCase):
    def test_only_ready_rows_are_summarized_and_sorted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_raster(
                root / "b.tif", np.array([[1.0, 2.0]], dtype=np.float32)
            )
            _write_raster(
                root / "a.tif", np.array([[10.0, 20.0]], dtype=np.float32)
            )
            rows = [
                _manifest_row(lago="amatitlan", fecha="2025-04-15", ruta_raster="b.tif"),
                _manifest_row(lago="amatitlan", fecha="2025-01-28", ruta_raster="a.tif"),
                _manifest_row(lago="atitlan", fecha="2025-01-18", quality_flag="pendiente_calculo", ruta_raster=""),
            ]
            resumen = at.build_resumen_temporal(rows, raiz=root)
            self.assertEqual(len(resumen), 2)
            self.assertEqual([r["fecha"] for r in resumen], ["2025-01-28", "2025-04-15"])
            self.assertEqual(set(resumen[0]), set(("lago", "fecha", "cyano_promedio", "cyano_mediana", "cyano_std", "pixeles_validos", "cobertura_valida_pct", "quality_flag")))
            self.assertAlmostEqual(resumen[0]["cyano_promedio"], 15.0)

    def test_no_ready_rows_returns_empty_list(self) -> None:
        rows = [_manifest_row(quality_flag="pendiente_calculo", ruta_raster="")]
        self.assertEqual(at.build_resumen_temporal(rows), [])


class WriteReadResumenTemporalTest(unittest.TestCase):
    def test_round_trip_through_csv(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "resumen_temporal.csv"
            rows = [
                {
                    "lago": "amatitlan",
                    "fecha": "2025-01-28",
                    "cyano_promedio": 12.5,
                    "cyano_mediana": 12.0,
                    "cyano_std": 1.1,
                    "pixeles_validos": 100,
                    "cobertura_valida_pct": 88.0,
                    "quality_flag": "calculado",
                }
            ]
            at.write_resumen_temporal(rows, path)
            read_back = at.read_resumen_temporal(path)
            self.assertEqual(len(read_back), 1)
            self.assertEqual(read_back[0]["lago"], "amatitlan")
            self.assertEqual(read_back[0]["cyano_promedio"], "12.5")


class FlagPeaksTest(unittest.TestCase):
    def test_value_far_above_mean_is_flagged(self) -> None:
        resumen = [
            {"lago": "amatitlan", "fecha": "2025-01-01", "cyano_promedio": 10.0, "quality_flag": "calculado"},
            {"lago": "amatitlan", "fecha": "2025-02-01", "cyano_promedio": 11.0, "quality_flag": "calculado"},
            {"lago": "amatitlan", "fecha": "2025-03-01", "cyano_promedio": 9.0, "quality_flag": "calculado"},
            {"lago": "amatitlan", "fecha": "2025-04-01", "cyano_promedio": 50.0, "quality_flag": "calculado"},
        ]
        flagged = at.flag_peaks(resumen)
        peaks = [f for f in flagged if f["es_pico"]]
        self.assertEqual(len(peaks), 1)
        self.assertEqual(peaks[0]["fecha"], "2025-04-01")

    def test_partial_coverage_row_does_not_skew_threshold(self) -> None:
        resumen = [
            {"lago": "amatitlan", "fecha": "2025-01-01", "cyano_promedio": 10.0, "quality_flag": "calculado"},
            {"lago": "amatitlan", "fecha": "2025-02-01", "cyano_promedio": 10.0, "quality_flag": "calculado"},
            {"lago": "amatitlan", "fecha": "2025-03-01", "cyano_promedio": 300.0, "quality_flag": "cobertura_parcial_oficial"},
        ]
        flagged = at.flag_peaks(resumen)
        by_fecha = {f["fecha"]: f for f in flagged}
        self.assertGreater(by_fecha["2025-03-01"]["umbral_pico"], 0)
        self.assertTrue(by_fecha["2025-03-01"]["es_pico"])
        self.assertFalse(by_fecha["2025-01-01"]["es_pico"])

    def test_fewer_than_two_complete_dates_yields_no_peak(self) -> None:
        resumen = [
            {"lago": "atitlan", "fecha": "2025-01-01", "cyano_promedio": 10.0, "quality_flag": "calculado"},
        ]
        flagged = at.flag_peaks(resumen)
        self.assertFalse(flagged[0]["es_pico"])
        self.assertEqual(flagged[0]["umbral_pico"], "")


if __name__ == "__main__":
    unittest.main()
