from __future__ import annotations

import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
from shapely.geometry import box

from src import features as feat
from src.config import VARIABLES_EXCLUIDAS_RESPUESTA
from src.respuesta import COLUMNA_RESPUESTA


class AntiFugaTest(unittest.TestCase):
    def test_dispara_si_se_inyecta_una_variable_prohibida(self) -> None:
        with self.assertRaises(feat.FeaturesError):
            feat.verificar_anti_fuga(["B03", "B08", "ndwi", "B04"])

    def test_no_dispara_con_solo_predictores_permitidos(self) -> None:
        feat.verificar_anti_fuga(["B03", "B08", "ndwi", "x_utm", "y_utm"])  # no debe lanzar

    def test_cada_variable_prohibida_dispara_individualmente(self) -> None:
        for variable in VARIABLES_EXCLUIDAS_RESPUESTA:
            with self.assertRaises(feat.FeaturesError):
                feat.verificar_anti_fuga(["B03", variable])


class TemporalesTest(unittest.TestCase):
    def _tabla(self, fechas):
        return pd.DataFrame({"fecha": fechas})

    def test_mes_se_extrae_correctamente(self) -> None:
        resultado = feat.agregar_temporales(self._tabla(["2025-03-15", "2025-11-01"]))
        self.assertEqual(resultado["mes"].tolist(), [3, 11])

    def test_estacion_seca_y_lluviosa(self) -> None:
        resultado = feat.agregar_temporales(self._tabla(["2025-01-10", "2025-07-10"]))
        self.assertEqual(resultado["estacion"].tolist(), ["seca", "lluviosa"])

    def test_codificacion_ciclica_coincide_con_la_formula(self) -> None:
        resultado = feat.agregar_temporales(self._tabla(["2025-01-01"]))
        angulo_esperado = 2 * np.pi * 1 / 365.25
        self.assertAlmostEqual(float(resultado["dia_anio_sin"].iloc[0]), np.sin(angulo_esperado), places=5)
        self.assertAlmostEqual(float(resultado["dia_anio_cos"].iloc[0]), np.cos(angulo_esperado), places=5)

    def test_31_de_diciembre_queda_cerca_de_1_de_enero_en_el_circulo(self) -> None:
        # La codificacion ciclica existe justamente para evitar el salto
        # artificial entre el ultimo y el primer dia del anio: sus vectores
        # (seno, coseno) deben quedar mucho mas cerca entre si que, por
        # ejemplo, el 1 de enero y un dia de mitad de anio.
        resultado = feat.agregar_temporales(self._tabla(["2025-12-31", "2025-01-01", "2025-07-02"]))
        dic31 = resultado.iloc[0][["dia_anio_sin", "dia_anio_cos"]].to_numpy(dtype=float)
        ene1 = resultado.iloc[1][["dia_anio_sin", "dia_anio_cos"]].to_numpy(dtype=float)
        jul2 = resultado.iloc[2][["dia_anio_sin", "dia_anio_cos"]].to_numpy(dtype=float)
        distancia_fin_inicio_anio = np.linalg.norm(dic31 - ene1)
        distancia_mitad_anio = np.linalg.norm(ene1 - jul2)
        self.assertLess(distancia_fin_inicio_anio, distancia_mitad_anio)
        self.assertLess(distancia_fin_inicio_anio, 0.1)


def _geometria_sintetica():
    """Un cuadrado de 100x100 m como contorno, para no depender del GeoJSON real."""

    cuadrado = box(0.0, 0.0, 100.0, 100.0)
    info = {"borde": cuadrado.boundary, "centroide": cuadrado.centroid}
    return {"amatitlan": info, "atitlan": info}


class DistanciasGeograficasTest(unittest.TestCase):
    def test_distancia_a_la_orilla_y_al_centroide_sobre_geometria_sintetica(self) -> None:
        tabla = pd.DataFrame(
            {
                "lago": ["amatitlan", "amatitlan", "amatitlan"],
                "x_utm": [50.0, 0.0, 150.0],
                "y_utm": [50.0, 50.0, 50.0],
            }
        )
        with patch("src.features._geometrias_utm", return_value=_geometria_sintetica()):
            resultado = feat.agregar_distancias_geograficas(tabla)

        # centro del cuadrado: coincide con el centroide, a 50 m de cualquier orilla
        self.assertAlmostEqual(float(resultado["dist_centroide_m"].iloc[0]), 0.0, places=3)
        self.assertAlmostEqual(float(resultado["dist_orilla_m"].iloc[0]), 50.0, places=3)
        # sobre la orilla izquierda: a 0 m del borde, a 50 m del centroide
        self.assertAlmostEqual(float(resultado["dist_orilla_m"].iloc[1]), 0.0, places=3)
        self.assertAlmostEqual(float(resultado["dist_centroide_m"].iloc[1]), 50.0, places=3)
        # 50 m fuera del cuadrado, mas alla de la orilla derecha
        self.assertAlmostEqual(float(resultado["dist_orilla_m"].iloc[2]), 50.0, places=3)
        self.assertAlmostEqual(float(resultado["dist_centroide_m"].iloc[2]), 100.0, places=3)


class RatioBandasTest(unittest.TestCase):
    def test_calcula_el_ratio_normal(self) -> None:
        tabla = pd.DataFrame({"B03": [0.02], "B08": [0.01]})
        resultado = feat.agregar_ratio_bandas(tabla)
        self.assertAlmostEqual(float(resultado["ratio_B03_B08"].iloc[0]), 2.0, places=5)

    def test_b08_en_cero_queda_nan_en_vez_de_dividir_por_cero(self) -> None:
        tabla = pd.DataFrame({"B03": [0.02], "B08": [0.0]})
        resultado = feat.agregar_ratio_bandas(tabla)
        self.assertTrue(np.isnan(resultado["ratio_B03_B08"].iloc[0]))


class NdwiVecindadTest(unittest.TestCase):
    def test_promedia_solo_los_vecinos_que_existen_en_la_rejilla(self) -> None:
        tabla = pd.DataFrame(
            {
                "lago": ["amatitlan"] * 4,
                "fecha": ["2025-01-01"] * 4,
                "x_utm": [0.0, 50.0, 0.0, 50.0],
                "y_utm": [100.0, 100.0, 50.0, 50.0],
                "ndwi": [1.0, 2.0, 3.0, 4.0],
            }
        )
        resultado = feat.agregar_ndwi_vecindad(tabla, lado=3)
        promedio_esperado = np.mean([1.0, 2.0, 3.0, 4.0])
        for valor in resultado["ndwi_vecindad_3x3"]:
            self.assertAlmostEqual(float(valor), promedio_esperado, places=5)

    def test_una_celda_aislada_solo_se_promedia_consigo_misma(self) -> None:
        tabla = pd.DataFrame(
            {
                "lago": ["amatitlan"],
                "fecha": ["2025-01-01"],
                "x_utm": [0.0],
                "y_utm": [0.0],
                "ndwi": [7.5],
            }
        )
        resultado = feat.agregar_ndwi_vecindad(tabla, lado=3)
        self.assertAlmostEqual(float(resultado["ndwi_vecindad_3x3"].iloc[0]), 7.5, places=5)


class DiccionarioPredictoresTest(unittest.TestCase):
    def test_falla_si_falta_documentar_una_variable(self) -> None:
        with self.assertRaises(feat.FeaturesError):
            feat.construir_diccionario(["variable_sin_documentar"])

    def test_ignora_la_columna_respuesta(self) -> None:
        filas = feat.construir_diccionario(["B03", COLUMNA_RESPUESTA])
        self.assertEqual([f["variable"] for f in filas], ["B03"])

    def test_completa_dinamicamente_columnas_one_hot(self) -> None:
        feat._completar_diccionario_categoricas(["lago_amatitlan", "estacion_seca"])
        self.assertIn("lago_amatitlan", feat.DICCIONARIO_PREDICTORES)
        self.assertIn("estacion_seca", feat.DICCIONARIO_PREDICTORES)


if __name__ == "__main__":
    unittest.main()
