from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np

from src import dataset_ml as dm
from src.config import ESCENAS_OFICIALES, LAGOS


def _tabla_valida(filas_por_escena: int = 2):
    """Tabla mínima que cumple el contrato, para probar las verificaciones."""

    import pandas as pd

    registros = []
    for scene in ESCENAS_OFICIALES:
        lago = LAGOS[scene.lago]
        lon_media = (lago.west + lago.east) / 2
        lat_media = (lago.south + lago.north) / 2
        for i in range(filas_por_escena):
            registros.append(
                {
                    "lago": scene.lago,
                    "fecha": scene.fecha,
                    "x_utm": 700000.0 + i,
                    "y_utm": 1600000.0 + i,
                    "lon": lon_media,
                    "lat": lat_media,
                    "B03": 0.02,
                    "B04": 0.01,
                    "B08": 0.005,
                    "ndvi": -0.3,
                    "ndwi": 0.6,
                    "cianobacteria_ugl": 5.0,
                    "n_pixeles_validos": 25,
                    "frac_valida": 1.0,
                }
            )
    tabla = pd.DataFrame(registros)[list(dm.NOMBRES_COLUMNAS)]
    return tabla.astype({nombre: tipo for nombre, tipo in dm.COLUMNAS_DATASET})


class TestAgregacion(unittest.TestCase):
    def test_umbral_es_mayoria_estricta(self):
        self.assertEqual(dm.PIXELES_POR_CELDA, 25)
        self.assertEqual(dm.MIN_PIXELES_VALIDOS_CELDA, 13)
        self.assertEqual(dm.RESOLUCION_DATASET_M, 50)

    def test_cuenta_validos_por_celda(self):
        valida = np.ones((10, 10), dtype=bool)
        valida[0, 0] = False
        conteos = dm.contar_validos_por_celda(valida)
        self.assertEqual(conteos.shape, (2, 2))
        self.assertEqual(conteos[0, 0], 24)
        self.assertEqual(conteos[1, 1], 25)

    def test_promedia_solo_pixeles_validos(self):
        valores = np.zeros((5, 5), dtype=np.float32)
        valores[0, 0] = 10.0
        valores[0, 1] = 20.0
        valida = np.zeros((5, 5), dtype=bool)
        valida[0, 0] = True
        valida[0, 1] = True
        promedio = dm.promediar_por_celda(valores, valida)
        self.assertEqual(promedio.shape, (1, 1))
        self.assertAlmostEqual(float(promedio[0, 0]), 15.0, places=5)

    def test_celda_sin_validos_queda_nan(self):
        valores = np.full((5, 5), 7.0, dtype=np.float32)
        valida = np.zeros((5, 5), dtype=bool)
        promedio = dm.promediar_por_celda(valores, valida)
        self.assertTrue(np.isnan(promedio[0, 0]))

    def test_descarta_bloques_incompletos_del_borde(self):
        valida = np.ones((12, 12), dtype=bool)
        conteos = dm.contar_validos_por_celda(valida)
        self.assertEqual(conteos.shape, (2, 2))
        self.assertTrue((conteos == 25).all())

    def test_valores_enmascarados_no_contaminan_el_promedio(self):
        valores = np.full((5, 5), 1000.0, dtype=np.float32)
        valores[2, 2] = 4.0
        valida = np.zeros((5, 5), dtype=bool)
        valida[2, 2] = True
        promedio = dm.promediar_por_celda(valores, valida)
        self.assertAlmostEqual(float(promedio[0, 0]), 4.0, places=5)


class TestCentroides(unittest.TestCase):
    def test_centro_de_la_celda_queda_a_media_celda_del_origen(self):
        from rasterio.transform import from_origin

        profile = {"transform": from_origin(700000.0, 1600000.0, 10.0, 10.0)}
        x, y = dm.centroides_de_celdas(profile, (2, 2))
        self.assertAlmostEqual(float(x[0, 0]), 700025.0, places=6)
        self.assertAlmostEqual(float(y[0, 0]), 1599975.0, places=6)
        self.assertAlmostEqual(float(x[0, 1]), 700075.0, places=6)
        self.assertAlmostEqual(float(y[1, 0]), 1599925.0, places=6)


class TestMascaraObservaciones(unittest.TestCase):
    """Usa el contorno real de Amatitlan sobre una rejilla sintetica que cubre
    su caja completa, de modo que existan pixeles dentro del lago."""

    LADO = 60

    def _profile(self):
        from rasterio.transform import from_origin

        lago = LAGOS["amatitlan"]
        paso_x = (lago.east - lago.west) / self.LADO
        paso_y = (lago.north - lago.south) / self.LADO
        return {
            "crs": "EPSG:4326",
            "transform": from_origin(lago.west, lago.north, paso_x, paso_y),
            "width": self.LADO,
            "height": self.LADO,
        }

    def _escena_limpia(self, profile):
        forma = (profile["height"], profile["width"])
        indices = {
            "cianobacteria": np.ones(forma, dtype=np.float32),
            "ndvi": np.zeros(forma, dtype=np.float32),
            "ndwi": np.zeros(forma, dtype=np.float32),
        }
        bandas = {nombre: np.full(forma, 500, dtype=np.int16) for nombre in dm.BANDAS_DATASET}
        bandas["SCL"] = np.full(forma, 6, dtype=np.int16)
        return indices, bandas

    def _pixeles_del_lago(self, profile, cuantos):
        dentro = np.argwhere(dm.lake_geometry_mask("amatitlan", profile))
        self.assertGreaterEqual(len(dentro), cuantos)
        return [tuple(posicion) for posicion in dentro[:cuantos]]

    def test_solo_deja_pixeles_dentro_del_contorno_del_lago(self):
        profile = self._profile()
        indices, bandas = self._escena_limpia(profile)
        mascara = dm.mascara_observaciones_validas(indices, bandas, profile, "amatitlan")
        self.assertTrue(mascara.any())
        self.assertFalse(bool(mascara[0, 0]))

    def test_descarta_nubes_nodata_y_no_agua(self):
        profile = self._profile()
        indices, bandas = self._escena_limpia(profile)
        nube, no_agua, sin_banda, sin_indice, control = self._pixeles_del_lago(profile, 5)

        bandas["SCL"][nube] = 9
        bandas["SCL"][no_agua] = 4
        bandas["B03"][sin_banda] = -32768
        indices["ndvi"][sin_indice] = np.nan

        mascara = dm.mascara_observaciones_validas(indices, bandas, profile, "amatitlan")

        self.assertFalse(bool(mascara[nube]))
        self.assertFalse(bool(mascara[no_agua]))
        self.assertFalse(bool(mascara[sin_banda]))
        self.assertFalse(bool(mascara[sin_indice]))
        self.assertTrue(bool(mascara[control]))

    def test_descarta_indices_fuera_de_su_rango_fisico(self):
        profile = self._profile()
        indices, bandas = self._escena_limpia(profile)
        atipico_ndvi, atipico_ndwi, atipico_cyano, control = self._pixeles_del_lago(profile, 4)

        indices["ndvi"][atipico_ndvi] = 23.0
        indices["ndwi"][atipico_ndwi] = -39.0
        indices["cianobacteria"][atipico_cyano] = -272.0

        mascara = dm.mascara_observaciones_validas(indices, bandas, profile, "amatitlan")

        self.assertFalse(bool(mascara[atipico_ndvi]))
        self.assertFalse(bool(mascara[atipico_ndwi]))
        self.assertFalse(bool(mascara[atipico_cyano]))
        self.assertTrue(bool(mascara[control]))


class TestRangoFisico(unittest.TestCase):
    def test_en_rango_excluye_extremos_y_nan(self):
        valores = np.array([-1.5, -1.0, 0.0, 1.0, 1.5, np.nan], dtype=np.float32)
        dentro = dm.en_rango(valores, dm.RANGO_INDICE_NORMALIZADO)
        self.assertEqual(dentro.tolist(), [False, True, True, True, False, False])

    def test_rango_de_cianobacteria_excluye_negativos(self):
        valores = np.array([-5.0, 0.0, 10.0, 600.0], dtype=np.float32)
        dentro = dm.en_rango(valores, dm.RANGO_CIANOBACTERIA)
        self.assertEqual(dentro.tolist(), [False, True, True, False])


class TestInventario(unittest.TestCase):
    def test_reporta_total_lago_fecha_y_variables(self):
        tabla = _tabla_valida()
        filas = dm.construir_inventario(tabla)
        secciones = {fila["seccion"] for fila in filas}
        self.assertEqual(secciones, {"total", "por_lago", "por_fecha", "variable"})

        total = next(f for f in filas if f["seccion"] == "total")
        self.assertEqual(total["n_observaciones"], len(tabla))

        por_fecha = [f for f in filas if f["seccion"] == "por_fecha"]
        self.assertEqual(len(por_fecha), len(ESCENAS_OFICIALES))

        variables = [f for f in filas if f["seccion"] == "variable"]
        self.assertEqual(len(variables), len(dm.NOMBRES_COLUMNAS))
        self.assertTrue(all(f["pct_faltantes"] == 0.0 for f in variables))

    def test_calcula_porcentaje_de_faltantes(self):
        tabla = _tabla_valida()
        tabla.loc[tabla.index[:2], "ndvi"] = np.nan
        filas = dm.construir_inventario(tabla)
        ndvi = next(f for f in filas if f["variable"] == "ndvi")
        self.assertAlmostEqual(ndvi["pct_faltantes"], 100.0 * 2 / len(tabla), places=4)

    def test_escribe_y_relee_el_inventario(self):
        tabla = _tabla_valida()
        with tempfile.TemporaryDirectory() as carpeta:
            destino = Path(carpeta) / "inventario.csv"
            dm.escribir_inventario(dm.construir_inventario(tabla), destino)
            leido = dm.leer_inventario(destino)
        self.assertEqual(int(leido[0]["n_observaciones"]), len(tabla))


class TestVerificarDataset(unittest.TestCase):
    def _verificar(self, tabla):
        return dm.verificar_dataset(tabla, filas_inventario=dm.construir_inventario(tabla))

    def test_acepta_una_tabla_que_cumple_el_contrato(self):
        resumen = self._verificar(_tabla_valida())
        self.assertEqual(resumen["combinaciones"], len(ESCENAS_OFICIALES))
        self.assertEqual(resumen["resolucion_m"], 50)

    def test_rechaza_columnas_faltantes(self):
        tabla = _tabla_valida().drop(columns=["ndwi"])
        with self.assertRaises(dm.DatasetMLError):
            self._verificar(tabla)

    def test_rechaza_escenas_faltantes(self):
        tabla = _tabla_valida()
        tabla = tabla[tabla["fecha"] != ESCENAS_OFICIALES[0].fecha]
        with self.assertRaises(dm.DatasetMLError):
            self._verificar(tabla)

    def test_rechaza_faltantes_en_columnas_clave(self):
        tabla = _tabla_valida()
        tabla.loc[tabla.index[0], "cianobacteria_ugl"] = np.nan
        with self.assertRaises(dm.DatasetMLError):
            self._verificar(tabla)

    def test_rechaza_coordenadas_fuera_de_la_caja_del_lago(self):
        tabla = _tabla_valida()
        tabla.loc[tabla.index[0], "lon"] = 0.0
        with self.assertRaises(dm.DatasetMLError):
            self._verificar(tabla)

    def test_rechaza_celdas_por_debajo_del_minimo_de_validos(self):
        tabla = _tabla_valida()
        tabla.loc[tabla.index[0], "frac_valida"] = 0.2
        with self.assertRaises(dm.DatasetMLError):
            self._verificar(tabla)

    def test_rechaza_inventario_desalineado(self):
        tabla = _tabla_valida()
        inventario = dm.construir_inventario(tabla)
        inventario[0]["n_observaciones"] = len(tabla) + 1
        with self.assertRaises(dm.DatasetMLError):
            dm.verificar_dataset(tabla, filas_inventario=inventario)


if __name__ == "__main__":
    unittest.main()
