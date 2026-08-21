from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from src import validacion as val
from src.modelos import COLUMNAS_IDENTIDAD_LAGO, NOMBRES_MODELOS


class AsignarBloquesTest(unittest.TestCase):
    def test_asigna_una_rejilla_sintetica_2x2(self):
        # Cuatro puntos en las esquinas de una rejilla 2x2 de 100 m, separados
        # 150 m entre si: cada uno debe caer en un bloque distinto.
        tabla = pd.DataFrame(
            {
                "lago": ["amatitlan"] * 4,
                "x_utm": [700000.0, 700150.0, 700000.0, 700150.0],
                "y_utm": [1600000.0, 1600000.0, 1600150.0, 1600150.0],
            }
        )
        resultado = val.asignar_bloques(tabla, tamano_por_lago={"amatitlan": 100.0})
        self.assertEqual(resultado["bloque"].nunique(), 4)
        self.assertEqual(sorted(resultado["bloque_fila"].tolist()), [0, 0, 1, 1])
        self.assertEqual(sorted(resultado["bloque_columna"].tolist()), [0, 0, 1, 1])

    def test_puntos_cercanos_caen_en_el_mismo_bloque(self):
        tabla = pd.DataFrame(
            {
                "lago": ["amatitlan"] * 3,
                "x_utm": [700000.0, 700010.0, 700400.0],
                "y_utm": [1600000.0, 1600020.0, 1600000.0],
            }
        )
        resultado = val.asignar_bloques(tabla, tamano_por_lago={"amatitlan": 100.0})
        self.assertEqual(resultado["bloque"].iloc[0], resultado["bloque"].iloc[1])
        self.assertNotEqual(resultado["bloque"].iloc[0], resultado["bloque"].iloc[2])

    def test_bloques_de_lagos_distintos_nunca_coinciden(self):
        tabla = pd.DataFrame(
            {
                "lago": ["amatitlan", "atitlan"],
                "x_utm": [700000.0, 700000.0],
                "y_utm": [1600000.0, 1600000.0],
            }
        )
        resultado = val.asignar_bloques(tabla, tamano_por_lago={"amatitlan": 100.0, "atitlan": 100.0})
        self.assertNotEqual(resultado["bloque"].iloc[0], resultado["bloque"].iloc[1])


def _matriz_y_metadatos_sinteticas(n_bloques: int = 10, obs_por_bloque: int = 6, seed: int = 5):
    """Puntos agrupados en `n_bloques` racimos bien separados entre si (5 km),
    suficientes para correr GroupKFold de verdad sobre datos sinteticos."""

    generador = np.random.default_rng(seed)
    filas = []
    for b in range(n_bloques):
        for _ in range(obs_por_bloque):
            filas.append(
                {
                    "x_utm": 700000.0 + b * 5000.0 + generador.uniform(0, 50),
                    "y_utm": 1600000.0 + generador.uniform(0, 50),
                }
            )
    matriz = pd.DataFrame(filas)
    metadatos = pd.DataFrame({"lago": "amatitlan", "fecha": "2026-01-01"}, index=matriz.index)
    return matriz, metadatos


class GroupKFoldNoSeRepartenTest(unittest.TestCase):
    def test_no_lanza_con_bloques_bien_separados(self):
        matriz, metadatos = _matriz_y_metadatos_sinteticas()
        val.verificar_grupos_no_se_reparten(matriz, metadatos=metadatos, n_pliegues=5)  # no debe lanzar

    def test_recorta_los_pliegues_si_hay_menos_bloques_que_pliegues_pedidos(self):
        matriz, metadatos = _matriz_y_metadatos_sinteticas(n_bloques=3, obs_por_bloque=4)
        val.verificar_grupos_no_se_reparten(matriz, metadatos=metadatos, n_pliegues=5)  # no debe lanzar


class MetricasConIndefinidosTest(unittest.TestCase):
    def test_sin_positivos_marca_las_metricas_dependientes_como_indefinido(self):
        y = np.zeros(20, dtype=int)
        predicho = np.zeros(20, dtype=int)
        metricas = val.metricas_con_indefinidos("prueba", y, predicho, np.linspace(0, 0.3, 20))
        for campo in ("precision", "recall", "f1", "f2", "roc_auc", "pr_auc"):
            self.assertEqual(metricas[campo], "indefinido")
        self.assertEqual(metricas["accuracy"], 1.0)
        self.assertEqual(metricas["positivos_prueba"], 0)

    def test_sin_negativos_tambien_marca_todo_como_indefinido(self):
        # Sin ninguna observacion negativa real, ROC-AUC y PR-AUC no tienen
        # definicion (dependen de las dos clases); se marcan junto con el
        # resto de metricas dependientes, no solo esas dos.
        y = np.ones(10, dtype=int)
        predicho = np.ones(10, dtype=int)
        metricas = val.metricas_con_indefinidos("prueba", y, predicho, np.linspace(0.7, 1.0, 10))
        for campo in ("precision", "recall", "f1", "f2", "roc_auc", "pr_auc"):
            self.assertEqual(metricas[campo], "indefinido")
        self.assertEqual(metricas["accuracy"], 1.0)

    def test_caso_normal_calcula_valores_numericos(self):
        y = np.array([0, 0, 0, 0, 1, 1, 1, 1])
        predicho = np.array([0, 0, 0, 1, 0, 1, 1, 1])
        probabilidad = np.array([0.1, 0.2, 0.3, 0.6, 0.4, 0.7, 0.8, 0.9])
        metricas = val.metricas_con_indefinidos("prueba", y, predicho, probabilidad)
        self.assertNotEqual(metricas["f2"], "indefinido")
        self.assertEqual(metricas["verdaderos_positivos"], 3)


class PromedioPorModeloTest(unittest.TestCase):
    def test_los_pliegues_indefinidos_no_cuentan_en_el_promedio(self):
        campos = ("accuracy", "precision", "recall", "f1", "f2", "roc_auc", "pr_auc")
        filas = [
            {"modelo": "random_forest", **{c: 0.8 for c in campos}},
            {"modelo": "random_forest", **{c: "indefinido" for c in campos}},
        ]
        for nombre in NOMBRES_MODELOS:
            if nombre != "random_forest":
                filas.append({"modelo": nombre, **{c: 0.5 for c in campos}})

        resumen = val.promedio_por_modelo(filas)
        self.assertAlmostEqual(resumen["random_forest"]["f2"], 0.8)
        self.assertEqual(resumen["random_forest"]["f2_pliegues_definidos"], 1)
        self.assertEqual(resumen["random_forest"]["n_pliegues"], 2)


class ColumnasGeneralizacionTest(unittest.TestCase):
    def test_excluye_las_columnas_de_identidad_de_lago(self):
        columnas = ["B03", "B08", "x_utm", "y_utm", "lago_amatitlan", "lago_atitlan", "dist_orilla_m"]
        resultado = val.columnas_generalizacion(columnas)
        for prohibida in COLUMNAS_IDENTIDAD_LAGO:
            self.assertNotIn(prohibida, resultado)
        self.assertIn("B03", resultado)
        self.assertIn("dist_orilla_m", resultado)


if __name__ == "__main__":
    unittest.main()
