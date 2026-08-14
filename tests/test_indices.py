from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from src import indices
from src.config import (
    CYANO_SCRIPT,
    ESCENAS_OFICIALES,
    INDICES,
    RUTA_CYANO_EVALSCRIPT_ORIGINAL,
)
from src.indices import (
    InputDataError,
    align_to_reference,
    compute_ndvi,
    compute_ndwi,
    expected_manifest_indices_rows,
    scl_valid_mask,
    scl_water_mask,
    select_scenes,
    summarize_array,
)


def _write_raster(path: Path, array: np.ndarray, *, descriptions=None, dtype=None):
    import rasterio
    from rasterio.transform import from_origin

    path.parent.mkdir(parents=True, exist_ok=True)
    if array.ndim == 2:
        array = array[np.newaxis, ...]
    count, height, width = array.shape
    transform = from_origin(-90.6, 14.5, 0.0001, 0.0001)
    profile = {
        "driver": "GTiff",
        "height": height,
        "width": width,
        "count": count,
        "dtype": dtype or array.dtype,
        "crs": "EPSG:4326",
        "transform": transform,
    }
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(array.astype(profile["dtype"]))
        if descriptions:
            for i, desc in enumerate(descriptions, start=1):
                dst.set_band_description(i, desc)


class NdviNdwiTest(unittest.TestCase):
    def test_ndvi_matches_formula(self) -> None:
        b04 = np.array([[0.1, 0.2]], dtype=np.float32)
        b08 = np.array([[0.4, 0.5]], dtype=np.float32)
        result = compute_ndvi(b04, b08)
        expected = (b08 - b04) / (b08 + b04)
        np.testing.assert_allclose(result, expected, rtol=1e-6)

    def test_ndwi_matches_formula(self) -> None:
        b03 = np.array([[0.3, 0.1]], dtype=np.float32)
        b08 = np.array([[0.1, 0.5]], dtype=np.float32)
        result = compute_ndwi(b03, b08)
        expected = (b03 - b08) / (b03 + b08)
        np.testing.assert_allclose(result, expected, rtol=1e-6)

    def test_zero_denominator_is_nodata_not_error(self) -> None:
        b04 = np.array([[0.0]], dtype=np.float32)
        b08 = np.array([[0.0]], dtype=np.float32)
        self.assertTrue(np.isnan(compute_ndvi(b04, b08)[0, 0]))
        self.assertTrue(np.isnan(compute_ndwi(b04, b08)[0, 0]))


class SclMaskTest(unittest.TestCase):
    def test_valid_mask_excludes_clouds_and_nodata(self) -> None:
        scl = np.array([0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11])
        valid = scl_valid_mask(scl)
        expected = np.array(
            [False, False, False, False, True, True, True, True, False, False, False, False]
        )
        np.testing.assert_array_equal(valid, expected)

    def test_water_mask_is_only_class_six(self) -> None:
        scl = np.array([4, 5, 6, 7])
        np.testing.assert_array_equal(scl_water_mask(scl), [False, False, True, False])


class ManifestIndicesTest(unittest.TestCase):
    def test_expected_rows_cover_22_scenes_times_3_indices(self) -> None:
        rows = expected_manifest_indices_rows()
        self.assertEqual(len(rows), len(ESCENAS_OFICIALES) * len(INDICES))
        keys = {(r["lago"], r["fecha"], r["indice"]) for r in rows}
        self.assertEqual(len(keys), len(rows))

    def test_prepare_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_path = root / "data" / "processed" / "manifest_indices.csv"
            with mock.patch.object(indices, "DIR_PROCESSED", root / "data" / "processed"), \
                 mock.patch.object(indices, "DIR_INDICES", root / "data" / "processed" / "indices"), \
                 mock.patch.object(indices, "RUTA_MANIFEST_INDICES", manifest_path):
                first = indices.prepare_indices_repository()
                second = indices.prepare_indices_repository()
                self.assertEqual(first["rows"], second["rows"])
                self.assertEqual(first["rows"], len(ESCENAS_OFICIALES) * len(INDICES))


class SelectScenesTest(unittest.TestCase):
    def test_invalid_lake_raises(self) -> None:
        with self.assertRaises(ValueError):
            select_scenes("peten", None)

    def test_unofficial_date_raises(self) -> None:
        with self.assertRaises(ValueError):
            select_scenes("atitlan", "2025-01-19")


class LoadSceneBandsTest(unittest.TestCase):
    def test_missing_scene_directory_raises_input_data_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(indices, "DIR_RASTERS", Path(tmp) / "rasters"):
                scene = select_scenes("amatitlan", "2025-01-28")[0]
                with self.assertRaises(InputDataError):
                    indices.load_scene_bands(scene, ("B03", "B04", "B08", "SCL"))

    def test_single_multiband_file_with_descriptions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with mock.patch.object(indices, "DIR_RASTERS", root):
                scene = select_scenes("amatitlan", "2025-01-28")[0]
                data = np.stack(
                    [
                        np.full((2, 2), 300, dtype=np.uint16),
                        np.full((2, 2), 400, dtype=np.uint16),
                        np.full((2, 2), 2000, dtype=np.uint16),
                        np.full((2, 2), 6, dtype=np.uint16),
                    ]
                )
                _write_raster(
                    root / scene.lago / scene.fecha / "openeo.tif",
                    data,
                    descriptions=["B03", "B04", "B08", "SCL"],
                    dtype="uint16",
                )
                loaded = indices.load_scene_bands(scene, ("B03", "B04", "B08", "SCL"))
                self.assertEqual(loaded["arrays"]["SCL"][0, 0], 6)
                self.assertEqual(loaded["arrays"]["B08"][0, 0], 2000)


class AlignAndSummarizeTest(unittest.TestCase):
    def test_align_is_noop_when_grids_match(self) -> None:
        profile = {
            "crs": "EPSG:4326",
            "transform": (1, 0, 0, 0, -1, 0),
            "width": 2,
            "height": 2,
        }
        array = np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float32)
        result = align_to_reference(array, profile, profile)
        np.testing.assert_array_equal(result, array)

    def test_summarize_array_counts_finite_values_only(self) -> None:
        array = np.array([[1.0, np.nan], [3.0, np.nan]], dtype=np.float32)
        stats = summarize_array(array)
        self.assertEqual(stats["valid_pixels"], 2)
        self.assertEqual(stats["total_pixels"], 4)
        self.assertAlmostEqual(stats["coverage_pct"], 50.0)
        self.assertAlmostEqual(stats["mean"], 2.0)


class ComputeIndicesForSceneTest(unittest.TestCase):
    def test_full_scene_pipeline_without_network(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw_dir = root / "data" / "raw" / "rasters"
            processed_dir = root / "data" / "processed"
            manifest_path = processed_dir / "manifest_indices.csv"

            with mock.patch.object(indices, "RAIZ", root), \
                 mock.patch.object(indices, "DIR_RASTERS", raw_dir), \
                 mock.patch.object(indices, "DIR_PROCESSED", processed_dir), \
                 mock.patch.object(indices, "DIR_INDICES", processed_dir / "indices"), \
                 mock.patch.object(indices, "RUTA_MANIFEST_INDICES", manifest_path):
                scene = select_scenes("amatitlan", "2025-01-28")[0]
                scene_dir = raw_dir / scene.lago / scene.fecha

                bands = np.stack(
                    [
                        np.array([[0.10, 0.12], [0.30, 0.30]], dtype=np.float32),  # B03
                        np.array([[0.05, 0.05], [0.20, 0.20]], dtype=np.float32),  # B04
                        np.array([[0.02, 0.02], [0.35, 0.35]], dtype=np.float32),  # B08
                    ]
                )
                scl = np.array([[6, 9], [6, 6]], dtype=np.uint16)  # agua, nube, agua, agua
                _write_raster(
                    scene_dir / "l2a.tif",
                    np.concatenate([bands, scl[np.newaxis, ...].astype(np.float32)]),
                    descriptions=["B03", "B04", "B08", "SCL"],
                    dtype="float32",
                )
                _write_raster(
                    scene_dir / "cyano_ndci_l1c.tif",
                    np.array([[5.0, np.nan], [8.0, 6.0]], dtype=np.float32),
                    dtype="float32",
                )

                outputs = indices.compute_indices_for_scene(scene, fetch_cyano_remote=False)
                self.assertEqual(set(outputs), {"ndvi", "ndwi", "cianobacteria"})
                for path in outputs.values():
                    self.assertTrue(path.exists())

                rows = indices.read_manifest_indices()
                ndvi_row = next(
                    r for r in rows if r["lago"] == "amatitlan" and r["fecha"] == "2025-01-28" and r["indice"] == "ndvi"
                )
                self.assertEqual(ndvi_row["quality_flag"], "calculado")
                self.assertNotEqual(ndvi_row["pixeles_validos"], "")
                # El píxel con nube (SCL=9) debe quedar fuera de la cuenta de válidos.
                self.assertEqual(int(ndvi_row["pixeles_validos"]), 3)

    def test_missing_cyano_raster_without_remote_flag_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw_dir = root / "data" / "raw" / "rasters"
            processed_dir = root / "data" / "processed"
            manifest_path = processed_dir / "manifest_indices.csv"

            with mock.patch.object(indices, "RAIZ", root), \
                 mock.patch.object(indices, "DIR_RASTERS", raw_dir), \
                 mock.patch.object(indices, "DIR_PROCESSED", processed_dir), \
                 mock.patch.object(indices, "DIR_INDICES", processed_dir / "indices"), \
                 mock.patch.object(indices, "RUTA_MANIFEST_INDICES", manifest_path):
                scene = select_scenes("amatitlan", "2025-01-28")[0]
                scene_dir = raw_dir / scene.lago / scene.fecha
                bands = np.stack(
                    [
                        np.full((2, 2), 0.1, dtype=np.float32),
                        np.full((2, 2), 0.1, dtype=np.float32),
                        np.full((2, 2), 0.1, dtype=np.float32),
                        np.full((2, 2), 6.0, dtype=np.float32),
                    ]
                )
                _write_raster(
                    scene_dir / "l2a.tif",
                    bands,
                    descriptions=["B03", "B04", "B08", "SCL"],
                    dtype="float32",
                )
                with self.assertRaises(InputDataError):
                    indices.compute_indices_for_scene(scene, fetch_cyano_remote=False)


class CyanoScriptFilesTest(unittest.TestCase):
    def test_evalscript_files_preserve_documented_formula(self) -> None:
        original = RUTA_CYANO_EVALSCRIPT_ORIGINAL.read_text(encoding="utf-8")
        numeric = indices.RUTA_CYANO_EVALSCRIPT_NUMERICO.read_text(encoding="utf-8")
        for text in (original, numeric):
            self.assertIn("826.57", text)
            self.assertIn("176.43", text)
            self.assertIn("MNDWI_threshold", text)
        self.assertIn("VERSION=3", numeric)
        self.assertNotIn("VERSION=3", original)

    def test_cyano_metadata_matches_lab_requirements(self) -> None:
        self.assertIn("cyano", CYANO_SCRIPT["nombre"].lower())
        self.assertTrue(CYANO_SCRIPT["url_catalogo"].startswith("https://custom-scripts.sentinel-hub.com"))
        self.assertTrue(CYANO_SCRIPT["url_fuente"].startswith("https://github.com/sentinel-hub/custom-scripts"))
        self.assertEqual(CYANO_SCRIPT["formula_version"], "cyano-ndci-l1c-v1-numeric")
        self.assertEqual(set(CYANO_SCRIPT["bandas"]), {"B02", "B03", "B04", "B05", "B07", "B08", "B8A", "B11", "B12"})


if __name__ == "__main__":
    unittest.main()
