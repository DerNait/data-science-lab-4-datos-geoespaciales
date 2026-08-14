from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from src import analisis_espacial as ae


def _write_raster(path: Path, array: np.ndarray, *, crs: str = "EPSG:4326", transform=None) -> None:
    import rasterio
    from rasterio.transform import from_origin

    path.parent.mkdir(parents=True, exist_ok=True)
    if transform is None:
        transform = from_origin(0, array.shape[0], 1, 1)
    profile = {
        "driver": "GTiff",
        "height": array.shape[0],
        "width": array.shape[1],
        "count": 1,
        "dtype": "float32",
        "crs": crs,
        "transform": transform,
    }
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(array.astype("float32"), 1)


def _manifest_row(
    *,
    lago: str = "amatitlan",
    fecha: str = "2025-01-28",
    ruta_raster: str,
    quality_flag: str = "calculado",
    cobertura_valida_pct: str = "50.0",
    resolucion_m: str = "10",
) -> dict:
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
        "resolucion_m": resolucion_m,
        "pixeles_validos": "0",
        "pixeles_lago": "0",
        "cobertura_valida_pct": cobertura_valida_pct,
        "frac_valores_atipicos": "0.0",
        "quality_flag": quality_flag,
    }


def _square_geometry(minx: float, miny: float, maxx: float, maxy: float) -> dict:
    return {
        "type": "Polygon",
        "coordinates": [[[minx, miny], [maxx, miny], [maxx, maxy], [minx, maxy], [minx, miny]]],
    }


def _boundary_feature_collection(geometry: dict) -> dict:
    return {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {"is_lake_boundary": True}, "geometry": geometry}
        ],
    }


def _way_element(coords_lon_lat, *, id_=1) -> dict:
    return {"type": "way", "id": id_, "geometry": [{"lat": lat, "lon": lon} for lon, lat in coords_lon_lat]}


class OverpassQueryTest(unittest.TestCase):
    def test_query_contains_water_tag_and_name(self) -> None:
        query = ae.build_overpass_query("Lago de Atitlán")
        self.assertIn('"natural"="water"', query)
        self.assertIn("Lago de Atitlán", query)
        self.assertIn("out geom;", query)


class FetchOsmLakeBoundaryTest(unittest.TestCase):
    def test_returns_geometry_from_first_matching_name(self) -> None:
        calls = []

        def fake_post(url, query, timeout_s):
            calls.append((url, query))
            return {"elements": [_way_element([(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)])]}

        resultado = ae.fetch_osm_lake_boundary("atitlan", http_post=fake_post)
        self.assertEqual(len(calls), 1)
        self.assertEqual(resultado["nombre_encontrado"], ae.OSM_LAKE_NAME_CANDIDATES["atitlan"][0])
        self.assertEqual(resultado["geometry"]["type"], "Polygon")

    def test_falls_back_to_second_name_when_first_is_empty(self) -> None:
        responses = [
            {"elements": []},
            {"elements": [_way_element([(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)])]},
        ]
        calls = []

        def fake_post(url, query, timeout_s):
            calls.append(query)
            return responses[len(calls) - 1]

        resultado = ae.fetch_osm_lake_boundary("atitlan", http_post=fake_post)
        self.assertEqual(len(calls), 2)
        self.assertEqual(resultado["nombre_encontrado"], ae.OSM_LAKE_NAME_CANDIDATES["atitlan"][1])

    def test_raises_overpass_error_when_no_name_matches(self) -> None:
        def fake_post(url, query, timeout_s):
            return {"elements": []}

        with self.assertRaises(ae.OverpassError):
            ae.fetch_osm_lake_boundary("atitlan", http_post=fake_post)

    def test_raises_overpass_error_on_network_failure(self) -> None:
        def fake_post(url, query, timeout_s):
            raise RuntimeError("timeout")

        with self.assertRaises(ae.OverpassError):
            ae.fetch_osm_lake_boundary("atitlan", http_post=fake_post)

    def test_relation_multipolygon_builds_polygon_with_holes(self) -> None:
        outer = [(0, 0), (4, 0), (4, 4), (0, 4), (0, 0)]
        inner = [(1, 1), (1, 2), (2, 2), (2, 1), (1, 1)]
        relation = {
            "type": "relation",
            "id": 99,
            "members": [
                {"type": "way", "role": "outer", "geometry": [{"lat": lat, "lon": lon} for lon, lat in outer]},
                {"type": "way", "role": "inner", "geometry": [{"lat": lat, "lon": lon} for lon, lat in inner]},
            ],
        }

        def fake_post(url, query, timeout_s):
            return {"elements": [relation]}

        resultado = ae.fetch_osm_lake_boundary("atitlan", http_post=fake_post)
        geometry_module, _ops = ae._shapely()
        shp = geometry_module.shape(resultado["geometry"])
        self.assertAlmostEqual(shp.area, 16 - 1, places=5)


class RequestLakeBoundaryTest(unittest.TestCase):
    def test_writes_feature_collection_with_required_properties(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "lago_atitlan_boundary.geojson"
            fake_result = {
                "lago": "atitlan",
                "nombre_encontrado": "Lago de Atitlán",
                "geometry": _square_geometry(0, 0, 1, 1),
                "overpass_url": "http://fake",
                "osm_element_type": "way",
                "osm_element_id": 1,
            }
            with mock.patch.object(ae, "RUTA_GEOJSON_BOUNDARY", {"atitlan": out_path}), mock.patch.object(
                ae, "fetch_osm_lake_boundary", lambda lago, **kwargs: fake_result
            ):
                path = ae.request_lake_boundary("atitlan")

            data = json.loads(path.read_text(encoding="utf-8"))
            props = data["features"][0]["properties"]
            self.assertTrue(props["is_lake_boundary"])
            self.assertEqual(props["source"], "OpenStreetMap (Overpass API)")
            self.assertIn("ODbL", props["licencia"])
            self.assertIn("fecha_consulta", props)

    def test_never_overwrites_existing_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "lago_atitlan_boundary.geojson"
            out_path.write_text('{"original": true}', encoding="utf-8")
            with mock.patch.object(ae, "RUTA_GEOJSON_BOUNDARY", {"atitlan": out_path}):
                with self.assertRaises(FileExistsError):
                    ae.request_lake_boundary("atitlan")
            self.assertEqual(out_path.read_text(encoding="utf-8"), '{"original": true}')


class LakeGeometryMaskTest(unittest.TestCase):
    def test_mask_marks_only_pixels_inside_polygon(self) -> None:
        from rasterio.transform import from_origin

        profile = {"crs": "EPSG:4326", "transform": from_origin(0, 4, 1, 1), "width": 4, "height": 4}
        geometry = _square_geometry(0, 0, 2, 4)  # mitad oeste del raster

        with tempfile.TemporaryDirectory() as tmp:
            boundary_path = Path(tmp) / "x.geojson"
            boundary_path.write_text(json.dumps(_boundary_feature_collection(geometry)), encoding="utf-8")
            with mock.patch.object(ae, "RUTA_GEOJSON_BOUNDARY", {"atitlan": boundary_path}):
                mask = ae.lake_geometry_mask("atitlan", profile)

        self.assertTrue(mask[:, 0].all())
        self.assertTrue(mask[:, 1].all())
        self.assertFalse(mask[:, 2].any())
        self.assertFalse(mask[:, 3].any())


class CombinedValidMaskTest(unittest.TestCase):
    def test_excludes_nan_inside_and_valid_outside_polygon(self) -> None:
        from rasterio.transform import from_origin

        profile = {"crs": "EPSG:4326", "transform": from_origin(0, 4, 1, 1), "width": 4, "height": 4}
        geometry = _square_geometry(0, 0, 2, 4)
        array = np.full((4, 4), 5.0, dtype=np.float32)
        array[0, 0] = np.nan  # NaN dentro del poligono

        with tempfile.TemporaryDirectory() as tmp:
            boundary_path = Path(tmp) / "x.geojson"
            boundary_path.write_text(json.dumps(_boundary_feature_collection(geometry)), encoding="utf-8")
            with mock.patch.object(ae, "RUTA_GEOJSON_BOUNDARY", {"atitlan": boundary_path}):
                mask = ae.combined_valid_mask(array, "atitlan", profile)

        self.assertFalse(mask[0, 0])  # NaN dentro
        self.assertTrue(mask[0, 1])  # valido dentro
        self.assertFalse(mask[0, 2])  # valido pero fuera del poligono
        self.assertFalse(mask[0, 3])


class GridConsistencyTest(unittest.TestCase):
    def test_detects_transform_mismatch_between_dates(self) -> None:
        from rasterio.transform import from_origin

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path_a = root / "a.tif"
            path_b = root / "b.tif"
            _write_raster(path_a, np.ones((2, 2), dtype=np.float32), transform=from_origin(0, 2, 1, 1))
            _write_raster(path_b, np.ones((2, 2), dtype=np.float32), transform=from_origin(0, 2, 2, 2))
            rows = [
                _manifest_row(fecha="2025-01-01", ruta_raster=str(path_a)),
                _manifest_row(fecha="2025-02-01", ruta_raster=str(path_b)),
            ]
            resultado = ae.check_grid_consistency("amatitlan", raiz=Path("."), rows=rows)

        self.assertFalse(resultado["consistente"])
        self.assertEqual(resultado["discrepancias"][0]["fecha"], "2025-02-01")

    def test_consistent_grids_report_no_discrepancies(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path_a = root / "a.tif"
            path_b = root / "b.tif"
            _write_raster(path_a, np.ones((2, 2), dtype=np.float32))
            _write_raster(path_b, np.ones((2, 2), dtype=np.float32))
            rows = [
                _manifest_row(fecha="2025-01-01", ruta_raster=str(path_a)),
                _manifest_row(fecha="2025-02-01", ruta_raster=str(path_b)),
            ]
            resultado = ae.check_grid_consistency("amatitlan", raiz=Path("."), rows=rows)

        self.assertTrue(resultado["consistente"])
        self.assertEqual(resultado["discrepancias"], [])


class HighValueStatsTest(unittest.TestCase):
    def test_counts_and_areas_are_correct(self) -> None:
        array = np.array([[20.0, 5.0], [np.nan, 12.0]], dtype=np.float32)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cyano.tif"
            _write_raster(path, array)
            row = _manifest_row(ruta_raster=str(path), resolucion_m="10")
            with mock.patch.object(ae, "combined_valid_mask", lambda arr, lago, profile: np.isfinite(arr)):
                stats = ae.high_value_stats_for_row(row, umbral=10.0, raiz=Path("."))

        self.assertEqual(stats["pixeles_validos_lago"], 3)
        self.assertEqual(stats["pixeles_altos"], 2)  # 20.0 y 12.0 >= 10
        self.assertAlmostEqual(stats["area_pixel_m2"], 100.0)
        self.assertAlmostEqual(stats["area_valida_m2"], 300.0)
        self.assertAlmostEqual(stats["area_alta_m2"], 200.0)
        self.assertAlmostEqual(stats["porcentaje_alto"], 200.0 / 3.0, places=2)


class ExtensionFloracionCsvTest(unittest.TestCase):
    def test_build_write_read_round_trip(self) -> None:
        array1 = np.array([[20.0, 5.0]], dtype=np.float32)
        array2 = np.array([[3.0, 4.0]], dtype=np.float32)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path1 = root / "amatitlan.tif"
            path2 = root / "atitlan.tif"
            _write_raster(path1, array1)
            _write_raster(path2, array2)
            rows = [
                _manifest_row(lago="amatitlan", fecha="2025-01-01", ruta_raster=str(path1)),
                _manifest_row(lago="atitlan", fecha="2025-02-01", ruta_raster=str(path2)),
            ]
            with mock.patch.object(ae, "combined_valid_mask", lambda arr, lago, profile: np.isfinite(arr)):
                filas = ae.build_extension_floracion(rows, raiz=Path("."))

            self.assertEqual(len(filas), 2)
            self.assertEqual([f["lago"] for f in filas], ["amatitlan", "atitlan"])

            csv_path = root / "extension.csv"
            ae.write_extension_floracion(filas, csv_path)
            leidas = ae.read_extension_floracion(csv_path)

        self.assertEqual(len(leidas), 2)
        self.assertEqual(set(leidas[0]), set(ae.EXTENSION_FLORACION_FIELDS))


class PersistenceRasterTest(unittest.TestCase):
    def test_variable_denominator_and_min_fechas_validas(self) -> None:
        a1 = np.array([[20.0, 5.0], [20.0, 5.0]], dtype=np.float32)
        a2 = np.array([[20.0, np.nan], [5.0, 5.0]], dtype=np.float32)
        a3 = np.array([[np.nan, np.nan], [20.0, 5.0]], dtype=np.float32)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = []
            for i, array in enumerate([a1, a2, a3]):
                path = root / f"f{i}.tif"
                _write_raster(path, array)
                rows.append(_manifest_row(lago="amatitlan", fecha=f"2025-0{i + 1}-01", ruta_raster=str(path)))

            with mock.patch.object(ae, "combined_valid_mask", lambda arr, lago, profile: np.isfinite(arr)):
                resultado = ae.persistence_raster(
                    "amatitlan", umbral=10.0, min_fechas_validas=2, rows=rows, raiz=Path(".")
                )

        # [0,0]: 20 (alto), 20 (alto), NaN -> 2 validas, 2 altas -> proporcion 1.0
        self.assertEqual(resultado["conteo_valido"][0, 0], 2)
        self.assertAlmostEqual(resultado["proporcion_alto"][0, 0], 1.0)

        # [0,1]: 5(no), NaN, NaN -> 1 valida < min_fechas_validas=2 -> NaN
        self.assertEqual(resultado["conteo_valido"][0, 1], 1)
        self.assertTrue(np.isnan(resultado["proporcion_alto"][0, 1]))

        # [1,0]: 20(si), 5(no), 20(si) -> 3 validas, 2 altas -> 2/3
        self.assertEqual(resultado["conteo_valido"][1, 0], 3)
        self.assertAlmostEqual(resultado["proporcion_alto"][1, 0], 2.0 / 3.0, places=5)


class MapMetadataCsvTest(unittest.TestCase):
    def test_round_trip(self) -> None:
        rows = [
            {
                "lago": "amatitlan",
                "fecha": "2025-01-01",
                "indice": "cianobacteria",
                "tipo_mapa": "individual",
                "archivo": "results/maps/x.png",
                "formato": "png",
                "vmin": 0,
                "vmax": 10,
                "umbral_alto_ugl": "",
                "generado_en": "2025-01-01T00:00:00",
            }
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "metadata.csv"
            ae.write_map_metadata(rows, path)
            leidas = ae.read_map_metadata(path)

        self.assertEqual(len(leidas), 1)
        self.assertEqual(set(leidas[0]), set(ae.METADATA_MAPAS_FIELDS))


class SuspiciousDatesTest(unittest.TestCase):
    def test_filters_non_calculado_rows(self) -> None:
        rows = [
            _manifest_row(lago="atitlan", fecha="2025-01-01", ruta_raster="a.tif", quality_flag="calculado"),
            _manifest_row(
                lago="atitlan", fecha="2025-02-01", ruta_raster="b.tif", quality_flag="revisar_valores_atipicos"
            ),
            _manifest_row(
                lago="amatitlan", fecha="2025-03-01", ruta_raster="c.tif", quality_flag="cobertura_parcial_oficial"
            ),
        ]
        sospechosas = ae.suspicious_dates(rows=rows)
        self.assertEqual(
            {(r["lago"], r["fecha"]) for r in sospechosas},
            {("atitlan", "2025-02-01"), ("amatitlan", "2025-03-01")},
        )

        solo_atitlan = ae.suspicious_dates("atitlan", rows=rows)
        self.assertEqual(len(solo_atitlan), 1)
        self.assertEqual(solo_atitlan[0]["fecha"], "2025-02-01")


class MapSmokeTest(unittest.TestCase):
    def test_save_cyano_map_png_creates_file(self) -> None:
        array = np.array([[5.0, 12.0], [8.0, np.nan]], dtype=np.float32)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raster_path = root / "cyano.tif"
            _write_raster(raster_path, array)
            row = _manifest_row(lago="amatitlan", fecha="2025-01-01", ruta_raster=str(raster_path))
            out_path = root / "mapa.png"
            with mock.patch.object(ae, "_cyano_row", lambda lago, fecha: row), mock.patch.object(
                ae, "combined_valid_mask", lambda arr, lago, profile: np.isfinite(arr)
            ), mock.patch.object(ae, "RAIZ", root):
                metadata = ae.save_cyano_map_png(
                    "amatitlan", "2025-01-01", vmin=0, vmax=20, out_path=out_path, raiz=Path(".")
                )

            self.assertTrue(out_path.is_file())
            self.assertEqual(metadata["tipo_mapa"], "individual")

    def test_save_folium_map_creates_html_file(self) -> None:
        array = np.array([[5.0, 12.0], [8.0, np.nan]], dtype=np.float32)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raster_path = root / "cyano.tif"
            _write_raster(raster_path, array)
            row = _manifest_row(lago="amatitlan", fecha="2025-01-01", ruta_raster=str(raster_path))

            boundary_path = root / "boundary.geojson"
            boundary_path.write_text(
                json.dumps(_boundary_feature_collection(_square_geometry(0, 0, 1, 1))), encoding="utf-8"
            )
            out_path = root / "mapa.html"
            with mock.patch.object(ae, "_cyano_row", lambda lago, fecha: row), mock.patch.object(
                ae, "combined_valid_mask", lambda arr, lago, profile: np.isfinite(arr)
            ), mock.patch.object(ae, "RUTA_GEOJSON_BOUNDARY", {"amatitlan": boundary_path}), mock.patch.object(
                ae, "RAIZ", root
            ):
                metadata = ae.save_folium_map(
                    "amatitlan", ["2025-01-01"], vmin=0, vmax=20, out_path=out_path, raiz=Path(".")
                )

            self.assertTrue(out_path.is_file())
            self.assertEqual(metadata["formato"], "html")


if __name__ == "__main__":
    unittest.main()
