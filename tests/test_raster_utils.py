from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin

from src.raster_utils import inspect_geotiff


class RasterUtilsTest(unittest.TestCase):
    def test_inspect_integer_raster_with_nodata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "integer_with_nodata.tif"
            values = np.array([[1, 2], [-9999, 4]], dtype=np.int16)
            with rasterio.open(
                path,
                "w",
                driver="GTiff",
                width=2,
                height=2,
                count=1,
                dtype="int16",
                crs="EPSG:32615",
                transform=from_origin(0, 20, 10, 10),
                nodata=-9999,
            ) as dataset:
                dataset.write(values, 1)

            metadata = inspect_geotiff(path)

        self.assertEqual(metadata.valid_pixels, 3)
        self.assertEqual(metadata.total_pixels, 4)
        self.assertEqual(metadata.valid_coverage_pct, 75.0)


if __name__ == "__main__":
    unittest.main()
