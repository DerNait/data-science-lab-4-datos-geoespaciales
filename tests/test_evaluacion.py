from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np

from src import evaluacion as ev


def _fila(nombre="random_forest", **cambios):
    """Fila de metricas coherente, para probar las verificaciones."""

    base = {
        "modelo": nombre,
        "n_prueba": "100",
        "positivos_prueba": "10",
        "accuracy": "0.9",
        "precision": "0.8",
        "recall": "0.8",
        "f1": "0.8",
        "f2": "0.8",
        "roc_auc": "0.95",
        "pr_auc": "0.85",
        "verdaderos_negativos": "82",
        "falsos_positivos": "8",
        "falsos_negativos": "2",
        "verdaderos_positivos": "8",
    }
    base.update({k: str(v) for k, v in cambios.items()})
    return base


def _filas_completas():
    return [_fila(nombre) for nombre in ev.NOMBRES_MODELOS]


class TestMetricasModelo(unittest.TestCase):
    def test_calcula_la_matriz_de_confusion_sobre_un_caso_conocido(self):
        y = np.array([0, 0, 0, 0, 1, 1, 1, 1])
        predicho = np.array([0, 0, 0, 1, 0, 1, 1, 1])
        probabilidad = np.array([0.1, 0.2, 0.3, 0.6, 0.4, 0.7, 0.8, 0.9])

        metricas = ev.metricas_modelo("prueba", y, predicho, probabilidad)

        self.assertEqual(metricas["verdaderos_negativos"], 3)
        self.assertEqual(metricas["falsos_positivos"], 1)
        self.assertEqual(metricas["falsos_negativos"], 1)
        self.assertEqual(metricas["verdaderos_positivos"], 3)
        self.assertAlmostEqual(metricas["accuracy"], 0.75, places=6)
        self.assertAlmostEqual(metricas["precision"], 0.75, places=6)
        self.assertAlmostEqual(metricas["recall"], 0.75, places=6)
        self.assertEqual(metricas["positivos_prueba"], 4)

    def test_f2_pesa_mas_el_recall_que_la_precision(self):
        # Mucho recall y poca precision debe puntuar mejor en F2 que al reves.
        y = np.array([0] * 90 + [1] * 10)

        recall_alto = np.array([1] * 40 + [0] * 50 + [1] * 10)
        recall_bajo = np.zeros(100, dtype=int)
        recall_bajo[90:92] = 1

        probabilidad = np.linspace(0, 1, 100)
        alta = ev.metricas_modelo("a", y, recall_alto, probabilidad)
        baja = ev.metricas_modelo("b", y, recall_bajo, probabilidad)

        self.assertGreater(alta["recall"], baja["recall"])
        self.assertLess(alta["precision"], baja["precision"])
        self.assertGreater(alta["f2"], baja["f2"])

    def test_no_falla_cuando_no_predice_ningun_positivo(self):
        y = np.array([0] * 9 + [1])
        predicho = np.zeros(10, dtype=int)
        metricas = ev.metricas_modelo("degenerado", y, predicho, np.linspace(0, 1, 10))
        self.assertEqual(metricas["precision"], 0.0)
        self.assertEqual(metricas["recall"], 0.0)
        self.assertEqual(metricas["f2"], 0.0)


class TestSeleccionDeModelo(unittest.TestCase):
    def test_elige_el_de_mayor_f2_por_defecto(self):
        filas = [
            {"modelo": "a", "f2": 0.5, "recall": 0.9},
            {"modelo": "b", "f2": 0.8, "recall": 0.4},
        ]
        self.assertEqual(ev.mejor_modelo(filas), "b")

    def test_permite_comparar_por_otro_criterio(self):
        filas = [
            {"modelo": "a", "f2": 0.5, "recall": 0.9},
            {"modelo": "b", "f2": 0.8, "recall": 0.4},
        ]
        self.assertEqual(ev.mejor_modelo(filas, criterio="recall"), "a")

    def test_rechaza_un_criterio_desconocido(self):
        with self.assertRaises(ev.EvaluacionError):
            ev.mejor_modelo([{"modelo": "a", "f2": 0.5}], criterio="inventado")

    def test_la_metrica_principal_es_f2(self):
        self.assertEqual(ev.METRICA_PRINCIPAL, "f2")


class TestCostoErrores(unittest.TestCase):
    def test_expresa_los_falsos_negativos_como_porcentaje_de_positivos(self):
        filas = [
            {
                "modelo": "a",
                "falsos_negativos": 2,
                "falsos_positivos": 8,
                "positivos_prueba": 10,
                "verdaderos_positivos": 8,
            }
        ]
        resumen = ev.costo_errores(filas)[0]
        self.assertAlmostEqual(resumen["pct_positivos_no_detectados"], 20.0)
        self.assertAlmostEqual(resumen["inspecciones_innecesarias_por_zona_detectada"], 1.0)


class TestVerificarEvaluacion(unittest.TestCase):
    def test_rechaza_una_matriz_de_confusion_que_no_suma(self):
        filas = _filas_completas()
        filas[0]["verdaderos_negativos"] = "80"
        with self.assertRaises(ev.EvaluacionError):
            ev.verificar_evaluacion(filas)

    def test_rechaza_positivos_que_no_cuadran_con_la_matriz(self):
        filas = _filas_completas()
        filas[0]["positivos_prueba"] = "50"
        with self.assertRaises(ev.EvaluacionError):
            ev.verificar_evaluacion(filas)

    def test_rechaza_metricas_fuera_de_rango(self):
        filas = _filas_completas()
        filas[0]["roc_auc"] = "1.4"
        with self.assertRaises(ev.EvaluacionError):
            ev.verificar_evaluacion(filas)

    def test_rechaza_conjuntos_de_prueba_distintos_entre_modelos(self):
        filas = _filas_completas()
        filas[1]["n_prueba"] = "200"
        filas[1]["verdaderos_negativos"] = "182"
        with self.assertRaises(ev.EvaluacionError):
            ev.verificar_evaluacion(filas)

    def test_rechaza_si_falta_algun_modelo(self):
        filas = _filas_completas()[:2]
        with self.assertRaises(ev.EvaluacionError):
            ev.verificar_evaluacion(filas)


class TestEscrituraMetricas(unittest.TestCase):
    def test_escribe_y_relee_las_metricas(self):
        y = np.array([0, 0, 1, 1])
        metricas = ev.metricas_modelo("random_forest", y, np.array([0, 0, 1, 1]), np.array([0.1, 0.2, 0.8, 0.9]))
        with tempfile.TemporaryDirectory() as carpeta:
            destino = Path(carpeta) / "metricas.csv"
            ev.escribir_metricas([metricas], destino)
            leidas = ev.leer_metricas(destino)
        self.assertEqual(leidas[0]["modelo"], "random_forest")
        self.assertAlmostEqual(float(leidas[0]["recall"]), 1.0)


if __name__ == "__main__":
    unittest.main()
