from __future__ import annotations

import unittest

from src.adquisicion import (
    bbox_feature,
    prepare_repository,
    query_spec,
    select_scenes,
    validate_manifest,
)
from src.config import LAGOS


class AcquisitionTest(unittest.TestCase):
    def test_prepare_is_idempotent_and_manifest_is_complete(self) -> None:
        first = prepare_repository()
        second = prepare_repository()
        self.assertEqual(first["scenes"], 22)
        self.assertEqual(second["scenes"], 22)
        self.assertEqual(len(validate_manifest()), 22)

    def test_bbox_is_closed_and_not_a_lake_boundary(self) -> None:
        feature_collection = bbox_feature(LAGOS["atitlan"])
        feature = feature_collection["features"][0]
        coordinates = feature["geometry"]["coordinates"][0]
        self.assertEqual(coordinates[0], coordinates[-1])
        self.assertFalse(feature["properties"]["is_lake_boundary"])
        self.assertEqual(feature["properties"]["geometry_role"], "query_bbox")

    def test_single_day_query_uses_next_day_as_end(self) -> None:
        scene = select_scenes("amatitlan", "2025-01-28")[0]
        spec = query_spec(scene)
        self.assertEqual(spec["temporal_extent"], ["2025-01-28", "2025-01-29"])
        self.assertEqual(spec["bands"], ["B03", "B04", "B08", "SCL"])

    def test_invalid_or_unofficial_selection_fails(self) -> None:
        with self.assertRaises(ValueError):
            select_scenes("atitlan", "2025-01-19")
        with self.assertRaises(ValueError):
            select_scenes("peten", None)


if __name__ == "__main__":
    unittest.main()

