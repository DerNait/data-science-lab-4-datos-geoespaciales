from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Sequence

import numpy as np

try:  # Permite `python src/indices.py` y `python -m src.indices`.
    from .config import (
        CYANO_SCRIPT,
        DIR_INDICES,
        DIR_PROCESSED,
        DIR_RASTERS,
        ESCENAS_OFICIALES,
        INDICES,
        LAGOS,
        MANIFEST_INDICES_FIELDS,
        RAIZ,
        RESOLUCION_OBJETIVO_M,
        RUTA_CYANO_EVALSCRIPT_NUMERICO,
        RUTA_MANIFEST_INDICES,
        SENTINEL_HUB_CLIENT_ID,
        SENTINEL_HUB_CLIENT_SECRET,
        SENTINEL_HUB_PROCESS_URL,
        SENTINEL_HUB_TOKEN_URL,
        SENTINEL2_L1C_TYPE,
        UMBRAL_FRACCION_VALORES_ATIPICOS,
        EscenaOficial,
    )
except ImportError:  # pragma: no cover - ruta usada al ejecutar el archivo
    from config import (  # type: ignore
        CYANO_SCRIPT,
        DIR_INDICES,
        DIR_PROCESSED,
        DIR_RASTERS,
        ESCENAS_OFICIALES,
        INDICES,
        LAGOS,
        MANIFEST_INDICES_FIELDS,
        RAIZ,
        RESOLUCION_OBJETIVO_M,
        RUTA_CYANO_EVALSCRIPT_NUMERICO,
        RUTA_MANIFEST_INDICES,
        SENTINEL_HUB_CLIENT_ID,
        SENTINEL_HUB_CLIENT_SECRET,
        SENTINEL_HUB_PROCESS_URL,
        SENTINEL_HUB_TOKEN_URL,
        SENTINEL2_L1C_TYPE,
        UMBRAL_FRACCION_VALORES_ATIPICOS,
        EscenaOficial,
    )

# Clases de la banda SCL (Scene Classification Layer) de Sentinel-2 L2A que
# se consideran válidas para calcular NDVI/NDWI y agua abierta. Referencia:
# https://sentiwiki.copernicus.eu/web/s2-processing (Scene Classification).
SCL_NODATA = 0
SCL_SATURATED = 1
SCL_DARK_AREA = 2
SCL_CLOUD_SHADOW = 3
SCL_WATER = 6
SCL_CLOUD_MEDIUM = 8
SCL_CLOUD_HIGH = 9
SCL_CIRRUS = 10
SCL_SNOW_ICE = 11

SCL_CLASES_INVALIDAS = (
    SCL_NODATA,
    SCL_SATURATED,
    SCL_DARK_AREA,
    SCL_CLOUD_SHADOW,
    SCL_CLOUD_MEDIUM,
    SCL_CLOUD_HIGH,
    SCL_CIRRUS,
    SCL_SNOW_ICE,
)


# Falta o es ambiguo un insumo requerido: fecha, lago, banda o raster.
class InputDataError(ValueError):
    pass


# --------------------------------------------------------------------------
# NDVI / NDWI
# --------------------------------------------------------------------------


# NDVI = (B08 - B04) / (B08 + B04); nodata si el denominador es 0.
def compute_ndvi(b04: np.ndarray, b08: np.ndarray) -> np.ndarray:
    b04 = b04.astype(np.float32)
    b08 = b08.astype(np.float32)
    denom = b08 + b04
    with np.errstate(invalid="ignore", divide="ignore"):
        ndvi = np.where(denom != 0, (b08 - b04) / denom, np.nan)
    return ndvi.astype(np.float32)


# NDWI = (B03 - B08) / (B03 + B08); nodata si el denominador es 0.
def compute_ndwi(b03: np.ndarray, b08: np.ndarray) -> np.ndarray:
    b03 = b03.astype(np.float32)
    b08 = b08.astype(np.float32)
    denom = b03 + b08
    with np.errstate(invalid="ignore", divide="ignore"):
        ndwi = np.where(denom != 0, (b03 - b08) / denom, np.nan)
    return ndwi.astype(np.float32)


# True donde SCL no es nube, sombra, nieve, saturado ni nodata.
def scl_valid_mask(scl: np.ndarray) -> np.ndarray:
    invalid = np.isin(scl, SCL_CLASES_INVALIDAS)
    return ~invalid


# True donde ninguna banda trae su valor nodata.
# SCL sola no basta: hay píxeles "agua" con alguna banda en nodata.
def reflectance_valid_mask(*bands: np.ndarray, nodata: float | None) -> np.ndarray:
    if nodata is None:
        return np.ones_like(bands[0], dtype=bool)
    valid = np.ones_like(bands[0], dtype=bool)
    for band in bands:
        valid &= band != nodata
    return valid


# True donde SCL clasifica agua abierta (clase 6).
# Máscara interina del lago mientras no exista el polígono oficial.
def scl_water_mask(scl: np.ndarray) -> np.ndarray:
    return scl == SCL_WATER


# --------------------------------------------------------------------------
# Lectura de bandas crudas
# --------------------------------------------------------------------------


def _raw_scene_dir(scene: EscenaOficial) -> Path:
    return DIR_RASTERS / scene.lago / scene.fecha


CYANO_RAW_FILENAME_PREFIX = "cyano_ndci_l1c"


# Lista los GeoTIFF crudos de una escena.
# Excluye el raster de cianobacteria para no mezclarlo con B03/B04/B08/SCL.
def find_scene_raster_files(
    scene: EscenaOficial, *, exclude_prefixes: Sequence[str] = (CYANO_RAW_FILENAME_PREFIX,)
) -> list[Path]:
    directory = _raw_scene_dir(scene)
    if not directory.is_dir():
        raise InputDataError(
            f"No existe la carpeta de raster crudos para {scene.lago} {scene.fecha}: "
            f"{directory}. Ejecute primero la descarga de bandas "
            "(python src/adquisicion.py download ...)."
        )
    files = sorted(directory.glob("*.tif")) + sorted(directory.glob("*.tiff"))
    files = [f for f in files if not f.stem.lower().startswith(tuple(exclude_prefixes))]
    if not files:
        raise InputDataError(f"No hay GeoTIFF de bandas L2A en {directory}")
    return files


# Carga las bandas pedidas desde los GeoTIFF crudos de una escena.
# Soporta un único archivo multibanda (por descripción o por orden) o un
# archivo por banda (busca el código de banda en el nombre del archivo).
def load_scene_bands(scene: EscenaOficial, band_names: Sequence[str]) -> dict[str, object]:
    try:
        import rasterio
    except ImportError as exc:  # pragma: no cover - depende del entorno local
        raise RuntimeError(
            "Para calcular índices instale las dependencias de requirements.txt"
        ) from exc

    files = find_scene_raster_files(scene)
    band_names = tuple(band_names)

    if len(files) == 1:
        with rasterio.open(files[0]) as dataset:
            descriptions = [d.upper() if d else "" for d in dataset.descriptions]
            profile = dataset.profile.copy()
            if all(name.upper() in descriptions for name in band_names):
                arrays = {
                    name: dataset.read(descriptions.index(name.upper()) + 1)
                    for name in band_names
                }
            elif dataset.count == len(band_names):
                arrays = {
                    name: dataset.read(i + 1) for i, name in enumerate(band_names)
                }
            else:
                raise InputDataError(
                    f"El GeoTIFF de {scene.lago} {scene.fecha} tiene "
                    f"{dataset.count} banda(s) y no declara descripciones; "
                    f"no se puede identificar {band_names} sin ambigüedad."
                )
        return {"arrays": arrays, "profile": profile, "source": files}

    arrays: dict[str, object] = {}
    profile = None
    for name in band_names:
        matches = [f for f in files if name.lower() in f.stem.lower()]
        if len(matches) != 1:
            raise InputDataError(
                f"Se esperaba exactamente un archivo para la banda {name} de "
                f"{scene.lago} {scene.fecha}; se encontraron {len(matches)} en {files}"
            )
        with rasterio.open(matches[0]) as dataset:
            arrays[name] = dataset.read(1)
            if profile is None:
                profile = dataset.profile.copy()
    return {"arrays": arrays, "profile": profile, "source": files}


# --------------------------------------------------------------------------
# Cianobacteria vía Sentinel Hub Process API (script numérico documentado)
# --------------------------------------------------------------------------


# Pide un token OAuth (client credentials) para la Process API.
def sentinel_hub_token() -> str:
    try:
        import requests
    except ImportError as exc:  # pragma: no cover - depende del entorno local
        raise RuntimeError(
            "Para consultar Sentinel Hub instale las dependencias de requirements.txt"
        ) from exc

    if not SENTINEL_HUB_CLIENT_ID or not SENTINEL_HUB_CLIENT_SECRET:
        raise RuntimeError(
            "Defina SENTINEL_HUB_CLIENT_ID y SENTINEL_HUB_CLIENT_SECRET en su .env "
            "(Dashboard de Copernicus Data Space > User Settings > OAuth clients)."
        )
    response = requests.post(
        SENTINEL_HUB_TOKEN_URL,
        data={
            "grant_type": "client_credentials",
            "client_id": SENTINEL_HUB_CLIENT_ID,
            "client_secret": SENTINEL_HUB_CLIENT_SECRET,
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()["access_token"]


def _cyano_process_body(scene: EscenaOficial, *, width: int, height: int) -> dict[str, object]:
    lago = LAGOS[scene.lago]
    evalscript = RUTA_CYANO_EVALSCRIPT_NUMERICO.read_text(encoding="utf-8")
    return {
        "input": {
            "bounds": {
                "bbox": [lago.west, lago.south, lago.east, lago.north],
                "properties": {"crs": "http://www.opengis.net/def/crs/OGC/1.3/CRS84"},
            },
            "data": [
                {
                    "type": SENTINEL2_L1C_TYPE,
                    "dataFilter": {
                        "timeRange": {
                            "from": f"{scene.fecha}T00:00:00Z",
                            "to": f"{scene.fecha}T23:59:59Z",
                        }
                    },
                }
            ],
        },
        "output": {
            "width": width,
            "height": height,
            "responses": [{"identifier": "default", "format": {"type": "image/tiff"}}],
        },
        "evalscript": evalscript,
    }


# Pide a la Process API el resultado numérico del script de cianobacteria.
# Se guarda sin modificar como raster crudo; nunca sobrescribe uno existente.
def request_cyano_layer(scene: EscenaOficial, *, resolution_m: int = RESOLUCION_OBJETIVO_M) -> Path:
    try:
        import requests
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "Para consultar Sentinel Hub instale las dependencias de requirements.txt"
        ) from exc

    lago = LAGOS[scene.lago]
    width = max(1, round((lago.east - lago.west) * 111_320 / resolution_m))
    height = max(1, round((lago.north - lago.south) * 111_320 / resolution_m))

    out_dir = _raw_scene_dir(scene)
    out_path = out_dir / "cyano_ndci_l1c.tif"
    if out_path.exists():
        raise FileExistsError(f"Ya existe una salida cruda de cianobacteria: {out_path}")
    out_dir.mkdir(parents=True, exist_ok=True)

    token = sentinel_hub_token()
    body = _cyano_process_body(scene, width=width, height=height)
    response = requests.post(
        SENTINEL_HUB_PROCESS_URL,
        json=body,
        headers={"Authorization": f"Bearer {token}"},
        timeout=120,
    )
    response.raise_for_status()
    out_path.write_bytes(response.content)
    return out_path


# --------------------------------------------------------------------------
# Alineación y exportación
# --------------------------------------------------------------------------


# Realinea el array a la rejilla de referencia si CRS/transform difieren.
def align_to_reference(array: np.ndarray, src_profile: dict, ref_profile: dict) -> np.ndarray:
    if (
        src_profile["crs"] == ref_profile["crs"]
        and src_profile["transform"] == ref_profile["transform"]
        and src_profile["width"] == ref_profile["width"]
        and src_profile["height"] == ref_profile["height"]
    ):
        return array

    from rasterio.warp import Resampling, reproject

    destination = np.full(
        (ref_profile["height"], ref_profile["width"]), np.nan, dtype=np.float32
    )
    reproject(
        source=array.astype(np.float32),
        destination=destination,
        src_transform=src_profile["transform"],
        src_crs=src_profile["crs"],
        dst_transform=ref_profile["transform"],
        dst_crs=ref_profile["crs"],
        resampling=Resampling.bilinear,
        src_nodata=np.nan,
        dst_nodata=np.nan,
    )
    return destination


def summarize_array(array: np.ndarray) -> dict[str, float]:
    valid = np.isfinite(array)
    valid_pixels = int(valid.sum())
    total_pixels = int(array.size)
    values = array[valid]
    return {
        "valid_pixels": valid_pixels,
        "total_pixels": total_pixels,
        "coverage_pct": round(100.0 * valid_pixels / total_pixels, 4) if total_pixels else 0.0,
        "min": float(values.min()) if valid_pixels else float("nan"),
        "max": float(values.max()) if valid_pixels else float("nan"),
        "mean": float(values.mean()) if valid_pixels else float("nan"),
        "median": float(np.median(values)) if valid_pixels else float("nan"),
        "std": float(values.std()) if valid_pixels else float("nan"),
    }


# Fracción de valores finitos fuera de [low, high]; NaN si no hay válidos.
def fraction_outside_range(array: np.ndarray, low: float, high: float) -> float:
    finite = array[np.isfinite(array)]
    if finite.size == 0:
        return float("nan")
    return float(((finite < low) | (finite > high)).sum()) / finite.size


def export_index_geotiff(
    array: np.ndarray,
    profile: dict,
    out_path: Path,
    *,
    lago: str,
    fecha: str,
    indice: str,
    formula_version: str,
    unidad: str,
) -> None:
    try:
        import rasterio
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "Para exportar índices instale las dependencias de requirements.txt"
        ) from exc

    out_profile = profile.copy()
    out_profile.update(count=1, dtype="float32", nodata=np.nan)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(out_path, "w", **out_profile) as dst:
        dst.write(array.astype(np.float32), 1)
        dst.set_band_description(1, indice)
        dst.update_tags(
            lago=lago,
            fecha=fecha,
            indice=indice,
            formula_version=formula_version,
            unidad=unidad,
        )


# --------------------------------------------------------------------------
# Contrato data/processed/manifest_indices.csv (entrega hacia el ejercicio 4)
# --------------------------------------------------------------------------


def _write_csv_atomic(path: Path, rows: Sequence[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=MANIFEST_INDICES_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def read_manifest_indices(path: Path | None = None) -> list[dict[str, str]]:
    path = RUTA_MANIFEST_INDICES if path is None else path
    with Path(path).open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def expected_manifest_indices_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for scene in ESCENAS_OFICIALES:
        for indice in INDICES:
            unidad = "adimensional" if indice in ("ndvi", "ndwi") else CYANO_SCRIPT["unidad"]
            rows.append(
                {
                    "lago": scene.lago,
                    "fecha": scene.fecha,
                    "indice": indice,
                    "ruta_raster": "",
                    "metodo": "",
                    "formula_version": (
                        "ndvi-v1" if indice == "ndvi" else
                        "ndwi-v1" if indice == "ndwi" else
                        CYANO_SCRIPT["formula_version"]
                    ),
                    "unidad": unidad,
                    "dtype": "float32",
                    "nodata": "nan",
                    "crs": "",
                    "resolucion_m": "",
                    "pixeles_validos": "",
                    "pixeles_lago": "",
                    "cobertura_valida_pct": "",
                    "frac_valores_atipicos": "",
                    "quality_flag": "pendiente_calculo",
                }
            )
    return rows


# Valida estructura y cobertura de lago/fecha/índice del manifiesto.
def validate_manifest_indices(path: Path | None = None) -> list[dict[str, str]]:
    rows = read_manifest_indices(path)
    expected_len = len(ESCENAS_OFICIALES) * len(INDICES)
    if len(rows) != expected_len:
        raise ValueError(
            f"El manifiesto de índices contiene {len(rows)} filas; se esperaban {expected_len}"
        )
    if set(rows[0]) != set(MANIFEST_INDICES_FIELDS):
        missing = set(MANIFEST_INDICES_FIELDS) - set(rows[0])
        extra = set(rows[0]) - set(MANIFEST_INDICES_FIELDS)
        raise ValueError(f"Columnas inválidas. Faltan={sorted(missing)}, extra={sorted(extra)}")

    keys = [(row["lago"], row["fecha"], row["indice"]) for row in rows]
    expected = [
        (scene.lago, scene.fecha, indice) for scene in ESCENAS_OFICIALES for indice in INDICES
    ]
    if len(keys) != len(set(keys)):
        raise ValueError("El manifiesto de índices contiene combinaciones duplicadas")
    if set(keys) != set(expected):
        raise ValueError(
            "El manifiesto de índices no coincide con las 22 escenas oficiales x 3 índices"
        )
    return rows


def _update_manifest_indices_row(
    lago: str, fecha: str, indice: str, **changes: object
) -> None:
    rows = read_manifest_indices()
    found = False
    for row in rows:
        if row["lago"] == lago and row["fecha"] == fecha and row["indice"] == indice:
            for key, value in changes.items():
                if key not in MANIFEST_INDICES_FIELDS:
                    raise KeyError(f"Campo de manifiesto de índices desconocido: {key}")
                row[key] = "" if value is None else str(value)
            found = True
            break
    if not found:
        raise ValueError(f"Combinación no encontrada en manifiesto de índices: {lago} {fecha} {indice}")
    _write_csv_atomic(RUTA_MANIFEST_INDICES, rows)
    validate_manifest_indices()


# Crea el directorio de índices y el manifiesto vacío, de forma idempotente.
def prepare_indices_repository() -> dict[str, object]:
    for directory in (DIR_PROCESSED, DIR_INDICES):
        directory.mkdir(parents=True, exist_ok=True)
    if not RUTA_MANIFEST_INDICES.exists():
        _write_csv_atomic(RUTA_MANIFEST_INDICES, expected_manifest_indices_rows())
    rows = validate_manifest_indices()
    return {"manifest": RUTA_MANIFEST_INDICES, "rows": len(rows)}


# --------------------------------------------------------------------------
# Orquestación por escena
# --------------------------------------------------------------------------


def select_scenes(lago: str | None = None, fecha: str | None = None) -> list[EscenaOficial]:
    if lago is not None and lago not in LAGOS:
        raise ValueError(f"Lago inválido: {lago}. Opciones: {', '.join(LAGOS)}")
    selected = [
        scene
        for scene in ESCENAS_OFICIALES
        if (lago is None or scene.lago == lago) and (fecha is None or scene.fecha == fecha)
    ]
    if not selected:
        raise ValueError("No existe una escena oficial con los filtros indicados")
    return selected


# Calcula NDVI, NDWI y, si hay insumo disponible, cianobacteria; actualiza
# el manifiesto. NDVI/NDWI no dependen de credenciales de Sentinel Hub. Si
# falta el raster de cianobacteria y require_cyano=False (por defecto), esa
# escena se omite solo para cianobacteria (queda pendiente_calculo) sin
# bloquear NDVI/NDWI. Con require_cyano=True lanza InputDataError.
def compute_indices_for_scene(
    scene: EscenaOficial, *, fetch_cyano_remote: bool = False, require_cyano: bool = False
) -> dict[str, Path]:
    prepare_indices_repository()

    bands = load_scene_bands(scene, ("B03", "B04", "B08", "SCL"))
    arrays = bands["arrays"]
    profile = bands["profile"]

    valid = scl_valid_mask(arrays["SCL"])
    water = scl_water_mask(arrays["SCL"])
    reflectance_valid = reflectance_valid_mask(
        arrays["B03"], arrays["B04"], arrays["B08"], nodata=profile.get("nodata")
    )
    lake_valid = valid & water & reflectance_valid

    ndvi = compute_ndvi(arrays["B04"], arrays["B08"])
    ndwi = compute_ndwi(arrays["B03"], arrays["B08"])
    ndvi = np.where(lake_valid, ndvi, np.nan)
    ndwi = np.where(lake_valid, ndwi, np.nan)

    arrays_by_index: dict[str, np.ndarray] = {"ndvi": ndvi, "ndwi": ndwi}

    cyano_dir = _raw_scene_dir(scene)
    cyano_candidates = sorted(cyano_dir.glob("cyano_ndci_l1c*.tif"))
    if not cyano_candidates and fetch_cyano_remote:
        cyano_candidates = [request_cyano_layer(scene)]

    if not cyano_candidates and require_cyano:
        raise InputDataError(
            f"No hay raster crudo de cianobacteria para {scene.lago} {scene.fecha}. "
            "Ejecute request_cyano_layer(scene) primero o pase fetch_cyano_remote=True."
        )

    if cyano_candidates:
        import rasterio

        with rasterio.open(cyano_candidates[0]) as dataset:
            cyano_raw = dataset.read(1).astype(np.float32)
            cyano_profile = dataset.profile.copy()
        arrays_by_index["cianobacteria"] = align_to_reference(cyano_raw, cyano_profile, profile)

    outputs: dict[str, Path] = {}
    metodo_by_index = {
        "ndvi": "local (B04,B08 L2A) + máscara SCL agua/válido",
        "ndwi": "local (B03,B08 L2A) + máscara SCL agua/válido",
        "cianobacteria": (
            f"Sentinel Hub Process API, evalscript numérico adaptado de "
            f"{CYANO_SCRIPT['nombre']} sobre Sentinel-2 L1C"
        ),
    }
    unidad_by_index = {"ndvi": "adimensional", "ndwi": "adimensional", "cianobacteria": CYANO_SCRIPT["unidad"]}
    formula_version_by_index = {
        "ndvi": "ndvi-v1",
        "ndwi": "ndwi-v1",
        "cianobacteria": CYANO_SCRIPT["formula_version"],
    }

    rango_valido_by_index = {
        "ndvi": (-1.0, 1.0),
        "ndwi": (-1.0, 1.0),
        "cianobacteria": CYANO_SCRIPT["rango_valido"],
    }

    out_dir = DIR_INDICES / scene.lago / scene.fecha
    for indice, array in arrays_by_index.items():
        stats = summarize_array(array)
        low, high = rango_valido_by_index[indice]
        frac_atipicos = fraction_outside_range(array, low, high)
        out_path = out_dir / f"{indice}.tif"
        export_index_geotiff(
            array,
            profile,
            out_path,
            lago=scene.lago,
            fecha=scene.fecha,
            indice=indice,
            formula_version=formula_version_by_index[indice],
            unidad=unidad_by_index[indice],
        )
        relative_path = out_path.resolve().relative_to(RAIZ.resolve()).as_posix()
        if scene.cobertura_valida_oficial_pct is not None:
            quality = "cobertura_parcial_oficial"
        elif frac_atipicos == frac_atipicos and frac_atipicos > UMBRAL_FRACCION_VALORES_ATIPICOS:
            quality = "revisar_valores_atipicos"
        else:
            quality = "calculado"
        _update_manifest_indices_row(
            scene.lago,
            scene.fecha,
            indice,
            ruta_raster=relative_path,
            metodo=metodo_by_index[indice],
            unidad=unidad_by_index[indice],
            dtype="float32",
            nodata="nan",
            crs=profile["crs"].to_string() if profile.get("crs") else "",
            resolucion_m=RESOLUCION_OBJETIVO_M,
            pixeles_validos=stats["valid_pixels"],
            pixeles_lago=int(lake_valid.sum()),
            cobertura_valida_pct=stats["coverage_pct"],
            frac_valores_atipicos=round(frac_atipicos, 4) if frac_atipicos == frac_atipicos else "",
            quality_flag=quality,
        )
        outputs[indice] = out_path

    return outputs


def compute_indices_batch(
    scenes: Sequence[EscenaOficial], *, fetch_cyano_remote: bool = False, confirm_batch: bool = False
) -> dict[str, dict[str, Path]]:
    if len(scenes) > 1 and not confirm_batch:
        raise ValueError("El cálculo por lote requiere confirm_batch=True o --confirm-batch")
    results: dict[str, dict[str, Path]] = {}
    for scene in scenes:
        key = f"{scene.lago}_{scene.fecha}"
        results[key] = compute_indices_for_scene(scene, fetch_cyano_remote=fetch_cyano_remote)
    return results


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=("prepare", "validate", "fetch-cyano", "compute"),
        nargs="?",
        default="prepare",
    )
    parser.add_argument("--lago", choices=tuple(LAGOS))
    parser.add_argument("--fecha", help="Fecha oficial YYYY-MM-DD")
    parser.add_argument(
        "--fetch-cyano-remote",
        action="store_true",
        help="Si falta el raster crudo de cianobacteria, pídelo a Sentinel Hub",
    )
    parser.add_argument(
        "--confirm-batch",
        action="store_true",
        help="Confirma conscientemente el cálculo de más de una escena",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.action == "prepare":
        summary = prepare_indices_repository()
        print(f"Manifiesto de índices listo: {summary['rows']} filas en {summary['manifest']}")
        return 0

    prepare_indices_repository()
    if args.action == "validate":
        rows = validate_manifest_indices()
        print(f"Validación correcta: {len(rows)} filas (22 escenas x 3 índices)")
        return 0

    scenes = select_scenes(args.lago, args.fecha)
    if args.action == "fetch-cyano":
        for scene in scenes:
            path = request_cyano_layer(scene)
            print(f"- {scene.lago} {scene.fecha}: {path}")
        return 0
    if args.action == "compute":
        outputs = compute_indices_batch(
            scenes,
            fetch_cyano_remote=args.fetch_cyano_remote,
            confirm_batch=args.confirm_batch,
        )
        for key, paths in outputs.items():
            print(f"- {key}: {[str(p) for p in paths.values()]}")
        return 0
    raise AssertionError(f"Acción no controlada: {args.action}")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, FileExistsError, RuntimeError, InputDataError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
