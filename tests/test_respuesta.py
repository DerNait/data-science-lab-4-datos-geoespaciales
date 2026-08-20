from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from src import respuesta as resp
from src.config import UMBRAL_CIANOBACTERIA_ALTO_UGL, VARIABLES_EXCLUIDAS_RESPUESTA


def _tabla(valores_cyano):
    filas = []
    for i, valor in enumerate(valores_cyano):
        filas.append(
            {
                "lago": "amatitlan" if i % 2 == 0 else "atitlan",
                "fecha": f"2025-01-{(i % 2) + 1:02d}",
                "cianobacteria_ugl": valor,
            }
        )
    return pd.DataFrame(filas)


class BinarizarTest(unittest.TestCase):
    def test_umbral_exacto_es_positivo(self) -> None:
        tabla = _tabla([UMBRAL_CIANOBACTERIA_ALTO_UGL])
        resultado = resp.binarizar(tabla)
        self.assertEqual(resultado["cyano_alta"].iloc[0], 1)

    def test_justo_debajo_del_umbral_es_negativo(self) -> None:
        tabla = _tabla([UMBRAL_CIANOBACTERIA_ALTO_UGL - 0.001])
        resultado = resp.binarizar(tabla)
        self.assertEqual(resultado["cyano_alta"].iloc[0], 0)

    def test_umbral_personalizado(self) -> None:
        tabla = _tabla([5.0])
        resultado = resp.binarizar(tabla, umbral=4.0)
        self.assertEqual(resultado["cyano_alta"].iloc[0], 1)

    def test_no_modifica_la_tabla_original(self) -> None:
        tabla = _tabla([1.0, 20.0])
        resp.binarizar(tabla)
        self.assertNotIn("cyano_alta", tabla.columns)

    def test_nan_en_cianobacteria_no_se_binariza_como_positivo(self) -> None:
        tabla = _tabla([np.nan])
        resultado = resp.binarizar(tabla)
        self.assertEqual(resultado["cyano_alta"].iloc[0], 0)


class DistribucionRespuestaTest(unittest.TestCase):
    def test_global_suma_el_total_de_filas(self) -> None:
        tabla = resp.binarizar(_tabla([1.0, 20.0, 3.0, 40.0]))
        filas = resp.distribucion_respuesta(tabla)
        globales = [f for f in filas if f["corte"] == "global"]
        self.assertEqual(sum(f["n"] for f in globales), len(tabla))
        self.assertEqual({f["cyano_alta"] for f in globales}, {0, 1})

    def test_por_lago_y_por_fecha_presentes(self) -> None:
        tabla = resp.binarizar(_tabla([1.0, 20.0, 3.0, 40.0]))
        filas = resp.distribucion_respuesta(tabla)
        cortes = {f["corte"] for f in filas}
        self.assertEqual(cortes, {"global", "por_lago", "por_fecha"})

    def test_escribe_y_relee(self) -> None:
        tabla = resp.binarizar(_tabla([1.0, 20.0]))
        filas = resp.distribucion_respuesta(tabla)
        with tempfile.TemporaryDirectory() as carpeta:
            destino = Path(carpeta) / "distribucion.csv"
            resp.escribir_distribucion(filas, destino)
            leido = resp.leer_distribucion(destino)
        self.assertEqual(len(leido), len(filas))


class ResumenDesbalanceTest(unittest.TestCase):
    def test_calcula_ratio_y_porcentaje_global(self) -> None:
        tabla = resp.binarizar(_tabla([1.0, 1.0, 1.0, 20.0]))
        resumen = resp.resumen_desbalance(tabla)
        self.assertEqual(resumen["global"]["n_positivos"], 1)
        self.assertEqual(resumen["global"]["n_negativos"], 3)
        self.assertAlmostEqual(resumen["global"]["pct_positivos"], 25.0)
        self.assertEqual(resumen["global"]["ratio_negativos_por_positivo"], 3.0)

    def test_reporta_por_lago(self) -> None:
        tabla = resp.binarizar(_tabla([20.0, 1.0, 20.0, 1.0]))
        resumen = resp.resumen_desbalance(tabla)
        self.assertIn("amatitlan", resumen)
        self.assertIn("atitlan", resumen)

    def test_lago_sin_positivos_da_ratio_infinita(self) -> None:
        tabla = resp.binarizar(_tabla([1.0, 1.0]))
        resumen = resp.resumen_desbalance(tabla)
        self.assertEqual(resumen["global"]["n_positivos"], 0)
        self.assertEqual(resumen["global"]["ratio_negativos_por_positivo"], float("inf"))


class VariablesExcluidasTest(unittest.TestCase):
    def test_declara_las_tres_variables_minimas_por_fuga(self) -> None:
        for variable in ("cianobacteria_ugl", "B04", "ndvi"):
            self.assertIn(variable, VARIABLES_EXCLUIDAS_RESPUESTA)

    def test_cada_exclusion_tiene_una_razon_no_vacia(self) -> None:
        for razon in VARIABLES_EXCLUIDAS_RESPUESTA.values():
            self.assertTrue(razon.strip())


class VerificarRespuestaTest(unittest.TestCase):
    def _tabla_y_distribucion(self, valores):
        tabla = resp.binarizar(_tabla(valores))
        filas = resp.distribucion_respuesta(tabla)
        return tabla, filas

    def test_acepta_una_tabla_correcta(self) -> None:
        tabla, filas = self._tabla_y_distribucion([1.0, 20.0, 3.0, 40.0])
        resumen = resp.verificar_respuesta(tabla, filas_distribucion=filas)
        self.assertEqual(resumen["observaciones"], len(tabla))

    def test_rechaza_columna_faltante(self) -> None:
        tabla = _tabla([1.0, 20.0])  # sin binarizar
        with self.assertRaises(resp.RespuestaError):
            resp.verificar_respuesta(tabla, filas_distribucion=[])

    def test_rechaza_valores_manipulados_que_no_coinciden_con_el_umbral(self) -> None:
        tabla, filas = self._tabla_y_distribucion([1.0, 20.0])
        tabla.loc[tabla.index[0], "cyano_alta"] = 1  # debería ser 0
        with self.assertRaises(resp.RespuestaError):
            resp.verificar_respuesta(tabla, filas_distribucion=filas)

    def test_rechaza_distribucion_desalineada(self) -> None:
        tabla, filas = self._tabla_y_distribucion([1.0, 20.0])
        filas = [dict(f) for f in filas]
        for f in filas:
            if f["corte"] == "global":
                f["n"] = 999
        with self.assertRaises(resp.RespuestaError):
            resp.verificar_respuesta(tabla, filas_distribucion=filas)


if __name__ == "__main__":
    unittest.main()
