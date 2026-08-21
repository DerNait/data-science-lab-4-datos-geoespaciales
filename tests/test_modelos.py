from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from src import modelos as md
from src.features import COLUMNA_RESPUESTA


def _matriz_sintetica(n: int = 400, positivos: int = 40, semilla: int = 7):
    """Matriz con la misma forma que la real pero pequena y con desbalance."""

    generador = np.random.default_rng(semilla)
    datos = {
        "B03": generador.random(n).astype("float32"),
        "B08": generador.random(n).astype("float32"),
        "ndwi": generador.random(n).astype("float32"),
        "x_utm": generador.random(n) * 1000 + 700000,
        "y_utm": generador.random(n) * 1000 + 1600000,
        "mes": generador.integers(1, 13, n).astype("int16"),
        "dia_anio_sin": generador.random(n).astype("float32"),
        "dia_anio_cos": generador.random(n).astype("float32"),
        "frac_valida": np.ones(n, dtype="float32"),
        "ratio_B03_B08": generador.random(n).astype("float32"),
        "dist_orilla_m": generador.random(n).astype("float32"),
        "dist_centroide_m": generador.random(n).astype("float32"),
        "ndwi_vecindad_3x3": generador.random(n).astype("float32"),
        "lago_amatitlan": np.zeros(n, dtype="int8"),
        "lago_atitlan": np.ones(n, dtype="int8"),
        "estacion_lluviosa": np.zeros(n, dtype="int8"),
        "estacion_seca": np.ones(n, dtype="int8"),
    }
    respuesta = np.zeros(n, dtype="int8")
    respuesta[:positivos] = 1
    generador.shuffle(respuesta)
    datos[COLUMNA_RESPUESTA] = respuesta
    return pd.DataFrame(datos)


def _particion_sintetica(matriz, semilla: int = md.SEMILLA):
    """Particion equivalente a la real, con lago y fecha inventados."""

    from sklearn.model_selection import train_test_split

    _, prueba = train_test_split(
        matriz.index.to_numpy(),
        test_size=md.FRACCION_PRUEBA,
        random_state=semilla,
        stratify=matriz[COLUMNA_RESPUESTA].to_numpy(),
        shuffle=True,
    )
    particion = pd.DataFrame(
        {
            "indice": matriz.index.to_numpy(),
            "lago": "atitlan",
            "fecha": "2026-04-13",
            "particion": md.ETIQUETA_ENTRENAMIENTO,
        }
    )
    particion.loc[particion["indice"].isin(prueba), "particion"] = md.ETIQUETA_PRUEBA
    return particion[list(md.PARTICION_FIELDS)]


class TestColumnasPorModelo(unittest.TestCase):
    def test_el_modelo_lineal_descarta_los_one_hot_redundantes(self):
        columnas = ["B03", "lago_amatitlan", "lago_atitlan", "estacion_lluviosa", "estacion_seca"]
        elegidas = md.columnas_para("regresion_logistica", columnas)
        self.assertNotIn("lago_atitlan", elegidas)
        self.assertNotIn("estacion_seca", elegidas)
        self.assertIn("lago_amatitlan", elegidas)
        self.assertIn("estacion_lluviosa", elegidas)

    def test_los_modelos_de_arboles_conservan_todas_las_columnas(self):
        columnas = ["B03", "lago_amatitlan", "lago_atitlan", "estacion_seca"]
        for nombre in ("random_forest", "gradient_boosting"):
            self.assertEqual(md.columnas_para(nombre, columnas), columnas)

    def test_identidad_de_lago_incluye_las_coordenadas_absolutas(self):
        # Quitar solo los one-hot no basta: x_utm separa los dos lagos igual.
        self.assertIn("x_utm", md.COLUMNAS_IDENTIDAD_LAGO)
        self.assertIn("y_utm", md.COLUMNAS_IDENTIDAD_LAGO)
        self.assertIn("lago_amatitlan", md.COLUMNAS_IDENTIDAD_LAGO)
        self.assertIn("lago_atitlan", md.COLUMNAS_IDENTIDAD_LAGO)


class TestPesoClasePositiva(unittest.TestCase):
    def test_razon_entre_negativos_y_positivos(self):
        y = np.array([0] * 90 + [1] * 10)
        self.assertAlmostEqual(md.peso_clase_positiva(y), 9.0)

    def test_falla_si_no_hay_positivos(self):
        with self.assertRaises(md.ModelosError):
            md.peso_clase_positiva(np.zeros(50, dtype=int))


class TestParticion(unittest.TestCase):
    def setUp(self):
        self.matriz = _matriz_sintetica()
        self.particion = _particion_sintetica(self.matriz)

    def test_respeta_la_proporcion_pedida(self):
        prueba = (self.particion["particion"] == md.ETIQUETA_PRUEBA).sum()
        self.assertAlmostEqual(prueba / len(self.particion), md.FRACCION_PRUEBA, places=2)

    def test_entrenamiento_y_prueba_no_se_solapan_y_cubren_todo(self):
        entrenamiento = set(
            self.particion.loc[self.particion["particion"] == md.ETIQUETA_ENTRENAMIENTO, "indice"]
        )
        prueba = set(self.particion.loc[self.particion["particion"] == md.ETIQUETA_PRUEBA, "indice"])
        self.assertEqual(entrenamiento & prueba, set())
        self.assertEqual(entrenamiento | prueba, set(self.matriz.index))

    def test_queda_estratificada(self):
        respuesta = self.matriz[COLUMNA_RESPUESTA]
        tasas = {}
        for etiqueta in (md.ETIQUETA_ENTRENAMIENTO, md.ETIQUETA_PRUEBA):
            indices = self.particion.loc[self.particion["particion"] == etiqueta, "indice"]
            tasas[etiqueta] = respuesta.loc[indices].mean()
        self.assertAlmostEqual(
            tasas[md.ETIQUETA_ENTRENAMIENTO], tasas[md.ETIQUETA_PRUEBA], places=2
        )

    def test_es_reproducible_con_la_misma_semilla(self):
        otra = _particion_sintetica(self.matriz)
        self.assertTrue(self.particion.equals(otra))

    def test_cambia_con_otra_semilla(self):
        otra = _particion_sintetica(self.matriz, semilla=md.SEMILLA + 1)
        self.assertFalse(self.particion.equals(otra))


class TestVerificarParticion(unittest.TestCase):
    def setUp(self):
        self.matriz = _matriz_sintetica()
        self.particion = _particion_sintetica(self.matriz)
        # Metadatos sinteticos para no depender del dataset real en disco.
        self.metadatos = self.particion.set_index("indice")[["lago", "fecha"]]

    def _verificar(self, matriz, particion, **extra):
        return md.verificar_particion(
            matriz, particion, metadatos=self.metadatos, **extra
        )

    def test_acepta_una_particion_correcta(self):
        resumen = self._verificar(self.matriz, self.particion)
        self.assertEqual(
            resumen["entrenamiento"] + resumen["prueba"], len(self.matriz)
        )

    def test_rechaza_solape_entre_entrenamiento_y_prueba(self):
        rota = self.particion.copy()
        indice_prueba = rota.loc[rota["particion"] == md.ETIQUETA_PRUEBA, "indice"].iloc[0]
        duplicada = rota[rota["indice"] == indice_prueba].copy()
        duplicada["particion"] = md.ETIQUETA_ENTRENAMIENTO
        rota = pd.concat([rota, duplicada], ignore_index=True)
        with self.assertRaises(md.ModelosError):
            self._verificar(self.matriz, rota)

    def test_rechaza_una_particion_de_otra_semilla(self):
        otra = _particion_sintetica(self.matriz, semilla=md.SEMILLA + 5)
        with self.assertRaises(md.ModelosError):
            self._verificar(self.matriz, otra)

    def test_rechaza_una_proporcion_distinta(self):
        rota = self.particion.copy()
        rota["particion"] = md.ETIQUETA_ENTRENAMIENTO
        with self.assertRaises(md.ModelosError):
            self._verificar(self.matriz, rota)


if __name__ == "__main__":
    unittest.main()
