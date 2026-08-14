from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class RasterMetadata:
    path: str
    width: int
    height: int
    count: int
    crs: str
    resolution_x: float
    resolution_y: float
    dtypes: str
    nodata: str
    valid_pixels: int
    total_pixels: int
    valid_coverage_pct: float

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def inspect_geotiff(path: Path) -> RasterMetadata:
    """Retorna metadatos y cobertura numérica válida de un GeoTIFF."""

    try:
        import numpy as np
        import rasterio
    except ImportError as exc:  # pragma: no cover - depende del entorno local
        raise RuntimeError(
            "Para validar GeoTIFF instale las dependencias de requirements.txt"
        ) from exc

    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)

    with rasterio.open(path) as dataset:
        if dataset.crs is None:
            raise ValueError(f"El raster no declara CRS: {path}")
        if dataset.width <= 0 or dataset.height <= 0 or dataset.count <= 0:
            raise ValueError(f"Dimensiones inválidas en raster: {path}")

        values = dataset.read(masked=True)
        mask = np.ma.getmaskarray(values)
        finite = np.isfinite(values.filled(np.nan))
        valid_by_band = (~mask) & finite
        valid_by_pixel = np.all(valid_by_band, axis=0)
        valid_pixels = int(valid_by_pixel.sum())
        total_pixels = int(dataset.width * dataset.height)
        coverage = 100.0 * valid_pixels / total_pixels if total_pixels else 0.0

        return RasterMetadata(
            path=path.as_posix(),
            width=dataset.width,
            height=dataset.height,
            count=dataset.count,
            crs=dataset.crs.to_string(),
            resolution_x=abs(float(dataset.res[0])),
            resolution_y=abs(float(dataset.res[1])),
            dtypes=";".join(dataset.dtypes),
            nodata="" if dataset.nodata is None else str(dataset.nodata),
            valid_pixels=valid_pixels,
            total_pixels=total_pixels,
            valid_coverage_pct=round(coverage, 4),
        )


def inspect_scene_directory(directory: Path) -> list[RasterMetadata]:
    """Inspecciona todos los `.tif`/`.tiff` de una descarga de openEO."""

    directory = Path(directory)
    candidates = sorted(directory.glob("*.tif")) + sorted(directory.glob("*.tiff"))
    if not candidates:
        raise FileNotFoundError(f"No se encontraron GeoTIFF en {directory}")
    return [inspect_geotiff(path) for path in candidates]

