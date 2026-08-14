from __future__ import annotations

import unittest
from collections import Counter

from src.config import (
    BANDAS_MINIMAS,
    ESCENAS_OFICIALES,
    LAGOS,
    OSM_LAKE_NAME_CANDIDATES,
    RUTA_GEOJSON_BOUNDARY,
    UMBRAL_CIANOBACTERIA_ALTO_UGL,
    validate_configuration,
)


class ConfigTest(unittest.TestCase):
    def test_configuration_contract(self) -> None:
        validate_configuration()
        self.assertEqual(len(ESCENAS_OFICIALES), 22)
        self.assertEqual(Counter(scene.lago for scene in ESCENAS_OFICIALES), {
            "amatitlan": 11,
            "atitlan": 11,
        })

    def test_scene_keys_are_unique(self) -> None:
        keys = {(scene.lago, scene.fecha) for scene in ESCENAS_OFICIALES}
        self.assertEqual(len(keys), 22)

    def test_boxes_are_valid(self) -> None:
        for lago in LAGOS.values():
            self.assertLess(lago.west, lago.east)
            self.assertLess(lago.south, lago.north)

    def test_minimum_bands_cover_indices_and_quality(self) -> None:
        self.assertEqual(BANDAS_MINIMAS, ("B03", "B04", "B08", "SCL"))

    def test_partial_scene_warning_is_preserved(self) -> None:
        scene = next(
            item
            for item in ESCENAS_OFICIALES
            if item.lago == "amatitlan" and item.fecha == "2026-02-07"
        )
        self.assertEqual(scene.cobertura_valida_oficial_pct, 57.1)
        self.assertIn("57.1", scene.observacion_oficial)

    def test_boundary_paths_cover_both_lakes(self) -> None:
        self.assertEqual(set(RUTA_GEOJSON_BOUNDARY), set(LAGOS))
        self.assertEqual(set(OSM_LAKE_NAME_CANDIDATES), set(LAGOS))

    def test_alert_threshold_is_positive(self) -> None:
        self.assertGreater(UMBRAL_CIANOBACTERIA_ALTO_UGL, 0)


if __name__ == "__main__":
    unittest.main()

