from __future__ import annotations

import unittest

import numpy as np

from src import mapas_predictivos as mp


class ReconstruccionRejillaTest(unittest.TestCase):
    def test_reconstruye_rejilla_2x2_desde_centroides(self):
        rejilla, x_edges, y_edges = mp.reconstruir_rejilla(
            [25, 75, 25, 75], [25, 25, 75, 75], [1, 2, 3, 4], paso=50
        )
        np.testing.assert_array_equal(rejilla, np.array([[1, 2], [3, 4]], dtype=float))
        np.testing.assert_array_equal(x_edges, [0, 50, 100])
        np.testing.assert_array_equal(y_edges, [0, 50, 100])

    def test_deja_huecos_sin_observacion_como_nan(self):
        rejilla, _x, _y = mp.reconstruir_rejilla([25, 75], [25, 75], [1, 4], paso=50)
        self.assertTrue(np.isnan(rejilla[0, 1]))
        self.assertTrue(np.isnan(rejilla[1, 0]))

    def test_rechaza_dos_observaciones_en_la_misma_celda(self):
        with self.assertRaises(mp.MapasPredictivosError):
            mp.reconstruir_rejilla([25, 25], [25, 25], [1, 2], paso=50)

    def test_promedia_solapes_de_teselas_antes_del_mapa(self):
        import pandas as pd

        tabla = pd.DataFrame(
            {
                "x_utm": [25, 25, 75],
                "y_utm": [25, 25, 25],
                "cyano_alta": [0, 0, 1],
                "probabilidad_alta": [0.2, 0.4, 0.8],
            }
        )
        celdas = mp.agregar_celdas_para_mapa(tabla)
        self.assertEqual(len(celdas), 2)
        self.assertAlmostEqual(float(celdas.loc[celdas["x_utm"] == 25, "probabilidad_alta"].iloc[0]), 0.3)


class EscalaProbabilidadTest(unittest.TestCase):
    def test_clasifica_los_cuatro_intervalos_y_los_bordes(self):
        resultado = mp.clasificar_probabilidades([0, 0.2499, 0.25, 0.4999, 0.5, 0.7499, 0.75, 1])
        self.assertEqual(
            resultado.tolist(),
            ["muy baja", "muy baja", "baja", "baja", "alta", "alta", "muy alta", "muy alta"],
        )

    def test_rechaza_probabilidades_fuera_de_rango(self):
        with self.assertRaises(mp.MapasPredictivosError):
            mp.clasificar_probabilidades([-0.01, 0.5])


class CategoriasErrorTest(unittest.TestCase):
    def test_cuenta_las_cuatro_categorias_en_caso_conocido(self):
        resultado = mp.categorias_error([0, 0, 1, 1], [0, 1, 0, 1])
        conteos = {categoria: int(np.sum(resultado == categoria)) for categoria in set(resultado)}
        self.assertEqual(
            conteos,
            {"verdadero_negativo": 1, "falso_positivo": 1, "falso_negativo": 1, "verdadero_positivo": 1},
        )

    def test_rechaza_tamanos_distintos(self):
        with self.assertRaises(ValueError):
            mp.categorias_error([0, 1], [0])


if __name__ == "__main__":
    unittest.main()
