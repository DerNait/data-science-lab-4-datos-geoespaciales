"""Análisis espacial de cianobacteria: contorno real del lago, mapas por
fecha, extensión de valores altos y zonas persistentes.

Lee exclusivamente los raster ya exportados por el cálculo de índices
(`data/processed/manifest_indices.csv`); no reabre bandas crudas ni cambia
la máscara SCL-agua que produjo esos raster. La geometría real del lago
(obtenida de OpenStreetMap) se aplica aquí, sobre los productos ya
calculados, como una intersección adicional.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Callable, Sequence

import numpy as np

try:  # Permite `python src/analisis_espacial.py` y `python -m src.analisis_espacial`.
    from .config import (
        DIR_ANALISIS_ESPACIAL,
        DIR_GEOJSON,
        DIR_RESULTS_FIGURES,
        DIR_RESULTS_MAPS,
        DIR_RESULTS_TABLES,
        EXTENSION_FLORACION_FIELDS,
        LAGOS,
        METADATA_MAPAS_FIELDS,
        OSM_LAKE_NAME_CANDIDATES,
        OVERPASS_API_URL,
        RAIZ,
        RESOLUCION_OBJETIVO_M,
        RUTA_EXTENSION_FLORACION,
        RUTA_GEOJSON_BOUNDARY,
        RUTA_METADATA_MAPAS,
        UMBRAL_CIANOBACTERIA_ALTO_UGL,
    )
    from .indices import (
        InputDataError,
        align_to_reference,
        export_index_geotiff,
        validate_manifest_indices,
    )
    from .analisis_temporal import (
        CALIDAD_COMPLETA,
        cianobacteria_rows,
        split_ready_pending,
    )
except ImportError:  # pragma: no cover - ruta usada al ejecutar el archivo
    from config import (  # type: ignore
        DIR_ANALISIS_ESPACIAL,
        DIR_GEOJSON,
        DIR_RESULTS_FIGURES,
        DIR_RESULTS_MAPS,
        DIR_RESULTS_TABLES,
        EXTENSION_FLORACION_FIELDS,
        LAGOS,
        METADATA_MAPAS_FIELDS,
        OSM_LAKE_NAME_CANDIDATES,
        OVERPASS_API_URL,
        RAIZ,
        RESOLUCION_OBJETIVO_M,
        RUTA_EXTENSION_FLORACION,
        RUTA_GEOJSON_BOUNDARY,
        RUTA_METADATA_MAPAS,
        UMBRAL_CIANOBACTERIA_ALTO_UGL,
    )
    from indices import (  # type: ignore
        InputDataError,
        align_to_reference,
        export_index_geotiff,
        validate_manifest_indices,
    )
    from analisis_temporal import (  # type: ignore
        CALIDAD_COMPLETA,
        cianobacteria_rows,
        split_ready_pending,
    )


# Overpass no respondió o no devolvió el lago buscado. Nunca se usa el bbox
# de consulta como sustituto silencioso: si esto se lanza, la geometría real
# del lago sigue sin resolverse.
class OverpassError(RuntimeError):
    pass


def _shapely():
    try:
        import shapely.geometry as geometry
        import shapely.ops as ops
    except ImportError as exc:  # pragma: no cover - depende del entorno local
        raise RuntimeError(
            "Para el análisis espacial instale las dependencias de requirements.txt (shapely)"
        ) from exc
    return geometry, ops


def _folium():
    try:
        import folium
    except ImportError as exc:  # pragma: no cover - depende del entorno local
        raise RuntimeError(
            "Para el mapa interactivo instale las dependencias de requirements.txt (folium)"
        ) from exc
    return folium


# --------------------------------------------------------------------------
# Lectura de raster ya exportados por el cálculo de índices
# --------------------------------------------------------------------------


def _read_index_raster(path: Path) -> tuple[np.ndarray, dict]:
    try:
        import rasterio
    except ImportError as exc:  # pragma: no cover - depende del entorno local
        raise RuntimeError(
            "Para leer los raster de índices instale las dependencias de requirements.txt"
        ) from exc
    with rasterio.open(path) as dataset:
        return dataset.read(1), dataset.profile.copy()


def open_index_raster(row: dict, *, raiz: Path | None = None) -> tuple[np.ndarray, dict]:
    """Abre el GeoTIFF declarado por una fila de `manifest_indices.csv`."""

    raiz = RAIZ if raiz is None else raiz
    if not row.get("ruta_raster"):
        raise InputDataError(
            f"La fila {row.get('lago')} {row.get('fecha')} {row.get('indice')} no declara "
            "'ruta_raster'; no puede leerse todavía."
        )
    ruta = raiz / row["ruta_raster"]
    if not ruta.is_file():
        raise InputDataError(f"No existe el raster declarado: {ruta}")
    return _read_index_raster(ruta)


def _ready_cyano_rows_for_lago(lago: str, *, rows: Sequence[dict] | None = None) -> list[dict]:
    if lago not in LAGOS:
        raise ValueError(f"Lago inválido: {lago}. Opciones: {', '.join(LAGOS)}")
    rows = validate_manifest_indices() if rows is None else rows
    subset = [r for r in rows if r["lago"] == lago]
    ready, _pending = split_ready_pending(subset)
    if not ready:
        raise InputDataError(f"No hay fechas de cianobacteria listas para {lago}")
    ready.sort(key=lambda r: r["fecha"])
    return ready


def _cyano_row(lago: str, fecha: str) -> dict:
    rows = validate_manifest_indices()
    matches = [
        r for r in rows if r["lago"] == lago and r["fecha"] == fecha and r["indice"] == "cianobacteria"
    ]
    if not matches:
        raise InputDataError(f"No existe fila de cianobacteria para {lago} {fecha}")
    return matches[0]


def _write_csv_atomic(path: Path, rows: Sequence[dict[str, object]], fieldnames: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def _write_geojson_atomic(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


# --------------------------------------------------------------------------
# Contorno real del lago vía OpenStreetMap (Overpass API)
# --------------------------------------------------------------------------


def build_overpass_query(nombre: str, *, timeout_s: int = 60) -> str:
    nombre_escapado = nombre.replace('"', '\\"')
    return (
        f'[out:json][timeout:{int(timeout_s)}];\n'
        f'nwr["natural"="water"]["name"="{nombre_escapado}"];\n'
        "out geom;"
    )


_OVERPASS_USER_AGENT = "lab4-uvg-cianobacteria-analisis-espacial/1.0"


def _default_overpass_post(url: str, query: str, timeout_s: int) -> dict:
    try:
        import requests
    except ImportError as exc:  # pragma: no cover - depende del entorno local
        raise RuntimeError(
            "Para consultar Overpass instale las dependencias de requirements.txt"
        ) from exc
    response = requests.post(
        url,
        data={"data": query},
        timeout=timeout_s,
        headers={"User-Agent": _OVERPASS_USER_AGENT},
    )
    response.raise_for_status()
    return response.json()


def _element_to_polygon(element: dict, geometry_module, ops_module):
    etype = element.get("type")

    if etype == "way":
        points = element.get("geometry")
        if not points or len(points) < 4:
            return None
        coords = [(pt["lon"], pt["lat"]) for pt in points]
        try:
            polygon = geometry_module.Polygon(coords)
        except Exception:
            return None
        if not polygon.is_valid:
            polygon = polygon.buffer(0)
        return polygon if not polygon.is_empty and polygon.area > 0 else None

    if etype == "relation":
        members = element.get("members", [])
        outer_lines = [
            geometry_module.LineString([(pt["lon"], pt["lat"]) for pt in member["geometry"]])
            for member in members
            if member.get("role") == "outer" and member.get("geometry") and len(member["geometry"]) >= 2
        ]
        inner_lines = [
            geometry_module.LineString([(pt["lon"], pt["lat"]) for pt in member["geometry"]])
            for member in members
            if member.get("role") == "inner" and member.get("geometry") and len(member["geometry"]) >= 2
        ]
        if not outer_lines:
            return None
        outer_polygons = list(ops_module.polygonize(outer_lines))
        if not outer_polygons:
            return None
        combined = ops_module.unary_union(outer_polygons)
        if inner_lines:
            inner_polygons = list(ops_module.polygonize(inner_lines))
            if inner_polygons:
                combined = combined.difference(ops_module.unary_union(inner_polygons))
        return combined if not combined.is_empty and combined.area > 0 else None

    return None


# De varios elementos candidatos con el mismo nombre (p.ej. otro cuerpo de
# agua homónimo), se elige el de mayor área en grados como heurística
# documentada; no hay forma de desambiguar mejor sin intervención manual.
def _overpass_elements_to_geometry(elements: Sequence[dict]) -> tuple[dict, dict]:
    geometry_module, ops_module = _shapely()
    candidatos = []
    for element in elements:
        polygon = _element_to_polygon(element, geometry_module, ops_module)
        if polygon is not None:
            candidatos.append((polygon.area, polygon, element))
    if not candidatos:
        raise OverpassError(
            "Overpass devolvió elementos pero ninguno con geometría de polígono válida"
        )
    candidatos.sort(key=lambda item: item[0], reverse=True)
    _, polygon, element = candidatos[0]
    metadata = {
        "osm_element_type": element.get("type", ""),
        "osm_element_id": element.get("id", ""),
    }
    return geometry_module.mapping(polygon), metadata


def fetch_osm_lake_boundary(
    lago: str,
    *,
    nombres: Sequence[str] | None = None,
    overpass_url: str | None = None,
    timeout_s: int = 90,
    http_post: Callable[[str, str, int], dict] | None = None,
) -> dict:
    """Busca el contorno real de un lago en OSM (`natural=water`).

    Prueba cada nombre candidato en orden; cualquier fallo de red o "no
    encontrado" se relanza como `OverpassError` explícito, nunca cae en
    silencio al bbox de consulta.
    """

    if lago not in LAGOS:
        raise ValueError(f"Lago inválido: {lago}. Opciones: {', '.join(LAGOS)}")
    nombres = tuple(OSM_LAKE_NAME_CANDIDATES[lago]) if nombres is None else tuple(nombres)
    overpass_url = OVERPASS_API_URL if overpass_url is None else overpass_url
    post = _default_overpass_post if http_post is None else http_post

    intentos: list[tuple[str, int]] = []
    for nombre in nombres:
        query = build_overpass_query(nombre, timeout_s=timeout_s)
        try:
            payload = post(overpass_url, query, timeout_s)
        except Exception as exc:
            raise OverpassError(
                f"Overpass no respondió al buscar '{nombre}' para {lago}: {exc}"
            ) from exc
        elementos = payload.get("elements", []) if isinstance(payload, dict) else []
        intentos.append((nombre, len(elementos)))
        if elementos:
            geometry, metadata = _overpass_elements_to_geometry(elementos)
            return {
                "lago": lago,
                "nombre_encontrado": nombre,
                "geometry": geometry,
                "overpass_url": overpass_url,
                **metadata,
            }
    raise OverpassError(
        f"Ningún nombre candidato de OSM devolvió un cuerpo de agua para {lago}: {intentos}"
    )


def request_lake_boundary(lago: str) -> Path:
    """Pide y cachea el contorno real de un lago; nunca sobrescribe uno existente.

    Mismo patrón que `indices.request_cyano_layer`: se guarda como GeoJSON
    nuevo en `data/raw/geojson/`, sin tocar el bbox de consulta.
    """

    if lago not in LAGOS:
        raise ValueError(f"Lago inválido: {lago}. Opciones: {', '.join(LAGOS)}")
    out_path = RUTA_GEOJSON_BOUNDARY[lago]
    if out_path.exists():
        raise FileExistsError(f"Ya existe un contorno cacheado para {lago}: {out_path}")

    resultado = fetch_osm_lake_boundary(lago)
    geometry_module, _ops = _shapely()
    shp = geometry_module.shape(resultado["geometry"])
    if not shp.is_valid or shp.area <= 0:
        raise OverpassError(f"Geometría inválida devuelta por Overpass para {lago}")

    feature_collection = {
        "type": "FeatureCollection",
        "name": f"lago_{lago}_boundary",
        "crs": {"type": "name", "properties": {"name": "EPSG:4326"}},
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "lago": lago,
                    "nombre": LAGOS[lago].nombre,
                    "geometry_role": "lake_boundary",
                    "is_lake_boundary": True,
                    "source": "OpenStreetMap (Overpass API)",
                    "overpass_url": resultado["overpass_url"],
                    "osm_nombre_encontrado": resultado["nombre_encontrado"],
                    "osm_element_type": resultado.get("osm_element_type", ""),
                    "osm_element_id": resultado.get("osm_element_id", ""),
                    "licencia": "Open Database License (ODbL) 1.0 - (c) OpenStreetMap contributors",
                    "fecha_consulta": date.today().isoformat(),
                },
                "geometry": resultado["geometry"],
            }
        ],
    }
    _write_geojson_atomic(out_path, feature_collection)
    return out_path


def load_lake_boundary_geometry(lago: str) -> dict:
    if lago not in LAGOS:
        raise ValueError(f"Lago inválido: {lago}. Opciones: {', '.join(LAGOS)}")
    path = RUTA_GEOJSON_BOUNDARY[lago]
    if not path.is_file():
        raise InputDataError(
            f"No existe el contorno real cacheado de {lago} ({path}); "
            "ejecute primero request_lake_boundary(lago)."
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    feature = data["features"][0]
    if not feature["properties"].get("is_lake_boundary"):
        raise InputDataError(f"El GeoJSON en {path} no está marcado is_lake_boundary=true")
    return feature["geometry"]


def boundary_area_km2(lago: str, *, crs: str = "EPSG:32615") -> float:
    from rasterio.warp import transform_geom

    geometry_module, _ops = _shapely()
    geometry = load_lake_boundary_geometry(lago)
    projected = transform_geom("EPSG:4326", crs, geometry)
    return geometry_module.shape(projected).area / 1e6


def compare_bbox_vs_boundary_area(lago: str, *, crs: str = "EPSG:32615") -> dict:
    """Chequeo de cordura: el contorno real debe ser más pequeño que el bbox."""

    from rasterio.warp import transform_geom

    geometry_module, _ops = _shapely()
    bbox_path = DIR_GEOJSON / f"aoi_{lago}_bbox.geojson"
    bbox_data = json.loads(bbox_path.read_text(encoding="utf-8"))
    bbox_geom = bbox_data["features"][0]["geometry"]
    bbox_projected = transform_geom("EPSG:4326", crs, bbox_geom)
    area_bbox_km2 = geometry_module.shape(bbox_projected).area / 1e6
    area_boundary_km2 = boundary_area_km2(lago, crs=crs)
    razon = area_boundary_km2 / area_bbox_km2 if area_bbox_km2 else float("nan")
    return {
        "lago": lago,
        "area_bbox_km2": round(area_bbox_km2, 4),
        "area_boundary_km2": round(area_boundary_km2, 4),
        "razon_boundary_bbox": round(razon, 4),
    }


# --------------------------------------------------------------------------
# Máscara combinada: geometría real ∩ máscara SCL-agua ya usada
# --------------------------------------------------------------------------


def lake_geometry_mask(lago: str, profile: dict) -> np.ndarray:
    from rasterio.features import geometry_mask
    from rasterio.warp import transform_geom

    geometry = load_lake_boundary_geometry(lago)
    projected = transform_geom("EPSG:4326", profile["crs"], geometry)
    return geometry_mask(
        [projected],
        out_shape=(profile["height"], profile["width"]),
        transform=profile["transform"],
        invert=True,
    )


# El raster ya exportado por indices.py solo tiene valores numéricos donde
# pasó la máscara SCL-agua de esa escena; intersectar con la geometría real
# sobre ese mismo array logra "geometría real ∩ máscara ya usada" sin
# reabrir las bandas SCL crudas.
def combined_valid_mask(array: np.ndarray, lago: str, profile: dict) -> np.ndarray:
    return np.isfinite(array) & lake_geometry_mask(lago, profile)


# --------------------------------------------------------------------------
# Consistencia de rejilla entre fechas de un mismo lago
# --------------------------------------------------------------------------


def reference_profile_for_lago(lago: str, *, rows: Sequence[dict] | None = None) -> dict:
    ready = _ready_cyano_rows_for_lago(lago, rows=rows)
    _, profile = open_index_raster(ready[0])
    return profile


def check_grid_consistency(
    lago: str, *, raiz: Path | None = None, rows: Sequence[dict] | None = None
) -> dict:
    ready = _ready_cyano_rows_for_lago(lago, rows=rows)
    _, ref_profile = open_index_raster(ready[0], raiz=raiz)
    discrepancias = []
    for row in ready[1:]:
        _, profile = open_index_raster(row, raiz=raiz)
        if (
            profile["crs"] != ref_profile["crs"]
            or profile["transform"] != ref_profile["transform"]
            or profile["width"] != ref_profile["width"]
            or profile["height"] != ref_profile["height"]
        ):
            discrepancias.append(
                {
                    "fecha": row["fecha"],
                    "width": profile["width"],
                    "height": profile["height"],
                    "transform": str(profile["transform"]),
                }
            )
    return {
        "lago": lago,
        "fecha_referencia": ready[0]["fecha"],
        "consistente": not discrepancias,
        "discrepancias": discrepancias,
    }


# --------------------------------------------------------------------------
# Ejercicio 8.1: extensión espacial de valores altos
# --------------------------------------------------------------------------


def pixel_area_m2(resolucion_m: float = RESOLUCION_OBJETIVO_M) -> float:
    """Área de un píxel en m²; el CRS de salida ya es UTM (metros)."""

    return float(resolucion_m) ** 2


def high_value_stats_for_row(
    row: dict, *, umbral: float = UMBRAL_CIANOBACTERIA_ALTO_UGL, raiz: Path | None = None
) -> dict:
    array, profile = open_index_raster(row, raiz=raiz)
    valid = combined_valid_mask(array, row["lago"], profile)
    alto = valid & (array >= umbral)

    resolucion_m = float(row.get("resolucion_m") or RESOLUCION_OBJETIVO_M)
    area_px = pixel_area_m2(resolucion_m)
    pixeles_validos = int(valid.sum())
    pixeles_altos = int(alto.sum())
    area_valida = pixeles_validos * area_px
    area_alta = pixeles_altos * area_px
    porcentaje_alto = 100.0 * pixeles_altos / pixeles_validos if pixeles_validos else 0.0

    return {
        "lago": row["lago"],
        "fecha": row["fecha"],
        "umbral_alto_ugl": umbral,
        "resolucion_m": resolucion_m,
        "area_pixel_m2": area_px,
        "pixeles_validos_lago": pixeles_validos,
        "pixeles_altos": pixeles_altos,
        "area_valida_m2": area_valida,
        "area_alta_m2": area_alta,
        "porcentaje_alto": round(porcentaje_alto, 4),
        "cobertura_valida_pct": row.get("cobertura_valida_pct", ""),
        "quality_flag": row.get("quality_flag", ""),
    }


def build_extension_floracion(
    rows: Sequence[dict] | None = None,
    *,
    umbral: float = UMBRAL_CIANOBACTERIA_ALTO_UGL,
    raiz: Path | None = None,
) -> list[dict]:
    rows = validate_manifest_indices() if rows is None else rows
    ready, _pending = split_ready_pending(rows)
    resultado = [high_value_stats_for_row(row, umbral=umbral, raiz=raiz) for row in ready]
    resultado.sort(key=lambda r: (r["lago"], r["fecha"]))
    return resultado


def write_extension_floracion(rows: Sequence[dict], path: Path | None = None) -> Path:
    path = RUTA_EXTENSION_FLORACION if path is None else path
    _write_csv_atomic(path, rows, EXTENSION_FLORACION_FIELDS)
    return path


def read_extension_floracion(path: Path | None = None) -> list[dict]:
    path = RUTA_EXTENSION_FLORACION if path is None else path
    with Path(path).open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


# --------------------------------------------------------------------------
# Ejercicio 8.2: zonas persistentes
# --------------------------------------------------------------------------


def stack_cianobacteria_arrays(
    lago: str, *, auto_align: bool = True, raiz: Path | None = None, rows: Sequence[dict] | None = None
) -> dict:
    ready = _ready_cyano_rows_for_lago(lago, rows=rows)
    _, ref_profile = open_index_raster(ready[0], raiz=raiz)

    fechas: list[str] = []
    layers: list[np.ndarray] = []
    for row in ready:
        array, profile = open_index_raster(row, raiz=raiz)
        same_grid = (
            profile["crs"] == ref_profile["crs"]
            and profile["transform"] == ref_profile["transform"]
            and profile["width"] == ref_profile["width"]
            and profile["height"] == ref_profile["height"]
        )
        if not same_grid:
            if not auto_align:
                raise InputDataError(
                    f"Rejilla distinta en {lago} {row['fecha']} respecto a la fecha de "
                    f"referencia ({ready[0]['fecha']}) y auto_align=False"
                )
            array = align_to_reference(array, profile, ref_profile)
        valid = combined_valid_mask(array, lago, ref_profile)
        layers.append(np.where(valid, array, np.nan).astype(np.float32))
        fechas.append(row["fecha"])

    return {"stack": np.stack(layers, axis=0), "fechas": fechas, "profile": ref_profile}


def persistence_raster(
    lago: str,
    *,
    umbral: float = UMBRAL_CIANOBACTERIA_ALTO_UGL,
    min_fechas_validas: int = 1,
    auto_align: bool = True,
    raiz: Path | None = None,
    rows: Sequence[dict] | None = None,
) -> dict:
    """Proporción de fechas válidas que exceden el umbral, por píxel.

    El denominador es el número de fechas válidas de ESE píxel (no siempre
    el total de fechas del lago), porque nubes/nodata varían por escena.
    """

    datos = stack_cianobacteria_arrays(lago, auto_align=auto_align, raiz=raiz, rows=rows)
    stack = datos["stack"]
    valido = np.isfinite(stack)
    conteo_valido = valido.sum(axis=0).astype(np.int32)
    conteo_alto = (valido & (stack >= umbral)).sum(axis=0).astype(np.int32)
    with np.errstate(invalid="ignore", divide="ignore"):
        proporcion_alto = np.where(
            conteo_valido >= min_fechas_validas,
            conteo_alto / np.maximum(conteo_valido, 1),
            np.nan,
        ).astype(np.float32)

    return {
        "lago": lago,
        "proporcion_alto": proporcion_alto,
        "conteo_valido": conteo_valido,
        "fechas": datos["fechas"],
        "profile": datos["profile"],
        "min_fechas_validas": min_fechas_validas,
        "umbral": umbral,
    }


def export_persistence_geotiffs(lago: str, resultado: dict, out_dir: Path | None = None) -> dict[str, Path]:
    out_dir = (DIR_ANALISIS_ESPACIAL / lago / "persistencia") if out_dir is None else out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    profile = resultado["profile"]

    proporcion_path = out_dir / "proporcion_alto.tif"
    conteo_path = out_dir / "conteo_valido_fechas.tif"
    export_index_geotiff(
        resultado["proporcion_alto"],
        profile,
        proporcion_path,
        lago=lago,
        fecha="todas_las_fechas_listas",
        indice="proporcion_alto_cianobacteria",
        formula_version="persistencia-v1",
        unidad="fraccion_0_1",
    )
    export_index_geotiff(
        resultado["conteo_valido"].astype(np.float32),
        profile,
        conteo_path,
        lago=lago,
        fecha="todas_las_fechas_listas",
        indice="conteo_valido_fechas",
        formula_version="persistencia-v1",
        unidad="conteo_de_fechas",
    )
    return {"proporcion_alto": proporcion_path, "conteo_valido": conteo_path}


# --------------------------------------------------------------------------
# Mapas estáticos (matplotlib)
# --------------------------------------------------------------------------


def comparison_scale(
    *,
    percentile: float = 98,
    vmax_min: float = UMBRAL_CIANOBACTERIA_ALTO_UGL,
    lagos: Sequence[str] | None = None,
    raiz: Path | None = None,
    rows: Sequence[dict] | None = None,
) -> tuple[float, float]:
    """Escala de color fija (percentil 98 global de píxeles válidos).

    Es una decisión de visualización, distinta del umbral cuantitativo de
    "valor alto" usado en 8.1/8.2 (`vmax_min` solo evita una escala más
    angosta que ese umbral).
    """

    lagos = tuple(LAGOS) if lagos is None else tuple(lagos)
    rows = validate_manifest_indices() if rows is None else rows
    subset = [r for r in rows if r["lago"] in lagos]
    ready, _pending = split_ready_pending(subset)

    valores = []
    for row in ready:
        array, profile = open_index_raster(row, raiz=raiz)
        valid = combined_valid_mask(array, row["lago"], profile)
        if valid.any():
            valores.append(array[valid])
    if not valores:
        raise InputDataError("No hay píxeles válidos para calcular la escala de color")

    todos = np.concatenate(valores)
    p = float(np.percentile(todos, percentile))
    return (0.0, max(p, vmax_min))


def plot_cyano_map(
    lago: str,
    fecha: str,
    *,
    ax=None,
    vmin: float | None = None,
    vmax: float | None = None,
    raiz: Path | None = None,
):
    import matplotlib.pyplot as plt
    from rasterio.transform import array_bounds

    row = _cyano_row(lago, fecha)
    array, profile = open_index_raster(row, raiz=raiz)
    valid = combined_valid_mask(array, lago, profile)
    masked = np.ma.masked_array(array, mask=~valid)

    if vmin is None or vmax is None:
        auto_vmin, auto_vmax = comparison_scale(lagos=(lago,), raiz=raiz)
        vmin = auto_vmin if vmin is None else vmin
        vmax = auto_vmax if vmax is None else vmax

    own_fig = ax is None
    if own_fig:
        fig, ax = plt.subplots(figsize=(6, 5))
    else:
        fig = ax.figure

    # Píxeles inválidos (nube, sombra, fuera del lago) en gris, nunca
    # blanco/0: no deben leerse como "sin cianobacteria".
    cmap = plt.get_cmap("YlOrRd").with_extremes(bad="lightgray")

    left, bottom, right, top = array_bounds(profile["height"], profile["width"], profile["transform"])
    im = ax.imshow(
        masked, cmap=cmap, vmin=vmin, vmax=vmax, extent=(left, right, bottom, top), origin="upper"
    )
    ax.set_title(f"{LAGOS[lago].nombre} · {fecha}")
    ax.set_xlabel("Este (m, UTM)")
    ax.set_ylabel("Norte (m, UTM)")

    cobertura = row.get("cobertura_valida_pct", "")
    calidad = row.get("quality_flag", "")
    ax.text(
        0.02,
        0.02,
        f"cobertura válida: {cobertura}%\ncalidad: {calidad}",
        transform=ax.transAxes,
        fontsize=7,
        va="bottom",
        ha="left",
        bbox={"facecolor": "white", "alpha": 0.7, "boxstyle": "round"},
    )

    if own_fig:
        cbar = fig.colorbar(im, ax=ax, fraction=0.046)
        cbar.set_label("cianobacteria (µg/L, proxy)")

    stats = {
        "lago": lago,
        "fecha": fecha,
        "vmin": vmin,
        "vmax": vmax,
        "cobertura_valida_pct": cobertura,
        "quality_flag": calidad,
    }
    return fig, ax, stats


def save_cyano_map_png(
    lago: str, fecha: str, *, vmin: float | None = None, vmax: float | None = None,
    out_path: Path | None = None, raiz: Path | None = None,
) -> dict:
    import matplotlib.pyplot as plt

    fig, _ax, stats = plot_cyano_map(lago, fecha, vmin=vmin, vmax=vmax, raiz=raiz)
    out_path = (DIR_RESULTS_MAPS / f"{lago}_{fecha}_cianobacteria.png") if out_path is None else out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return {
        "lago": lago,
        "fecha": fecha,
        "indice": "cianobacteria",
        "tipo_mapa": "individual",
        "archivo": out_path.resolve().relative_to(RAIZ.resolve()).as_posix(),
        "formato": "png",
        "vmin": stats["vmin"],
        "vmax": stats["vmax"],
        "umbral_alto_ugl": "",
        "generado_en": datetime.now().isoformat(timespec="seconds"),
    }


def plot_cyano_comparison(lago: str, fechas: Sequence[str], *, vmin: float, vmax: float):
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, len(fechas), figsize=(5 * len(fechas), 4.5), squeeze=False)
    last_im = None
    for ax, fecha in zip(axes[0], fechas):
        plot_cyano_map(lago, fecha, ax=ax, vmin=vmin, vmax=vmax)
        last_im = ax.images[-1]
    fig.suptitle(f"{LAGOS[lago].nombre} - comparación con escala fija")
    if last_im is not None:
        cbar = fig.colorbar(last_im, ax=axes[0].tolist(), fraction=0.03, pad=0.02)
        cbar.set_label("cianobacteria (µg/L, proxy)")
    return fig


def save_cyano_comparison_png(
    lago: str, fechas: Sequence[str], *, vmin: float, vmax: float, out_path: Path | None = None
) -> dict:
    import matplotlib.pyplot as plt

    fig = plot_cyano_comparison(lago, fechas, vmin=vmin, vmax=vmax)
    out_path = (DIR_RESULTS_MAPS / f"{lago}_comparativo_cianobacteria.png") if out_path is None else out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return {
        "lago": lago,
        "fecha": ";".join(fechas),
        "indice": "cianobacteria",
        "tipo_mapa": "comparativo",
        "archivo": out_path.resolve().relative_to(RAIZ.resolve()).as_posix(),
        "formato": "png",
        "vmin": vmin,
        "vmax": vmax,
        "umbral_alto_ugl": "",
        "generado_en": datetime.now().isoformat(timespec="seconds"),
    }


def plot_persistence_map(lago: str, resultado: dict):
    import matplotlib.pyplot as plt

    sin_datos = resultado["conteo_valido"] == 0
    proporcion = np.ma.masked_array(resultado["proporcion_alto"], mask=sin_datos)
    conteo = np.ma.masked_array(resultado["conteo_valido"], mask=sin_datos)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.5))

    cmap1 = plt.get_cmap("YlOrRd").with_extremes(bad="lightgray")
    im1 = ax1.imshow(proporcion, cmap=cmap1, vmin=0, vmax=1, origin="upper")
    ax1.set_title(f"{LAGOS[lago].nombre} - proporción de fechas con valor alto")
    fig.colorbar(im1, ax=ax1, fraction=0.046).set_label("fracción de fechas válidas > umbral")

    cmap2 = plt.get_cmap("viridis").with_extremes(bad="lightgray")
    im2 = ax2.imshow(conteo, cmap=cmap2, origin="upper")
    ax2.set_title("fechas válidas usadas por píxel")
    fig.colorbar(im2, ax=ax2, fraction=0.046).set_label("número de fechas válidas")

    return fig


def save_persistence_map_png(lago: str, resultado: dict, *, out_path: Path | None = None) -> dict:
    import matplotlib.pyplot as plt

    fig = plot_persistence_map(lago, resultado)
    out_path = (
        (DIR_RESULTS_MAPS / f"{lago}_persistencia_cianobacteria.png") if out_path is None else out_path
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return {
        "lago": lago,
        "fecha": ";".join(resultado["fechas"]),
        "indice": "cianobacteria",
        "tipo_mapa": "persistencia",
        "archivo": out_path.resolve().relative_to(RAIZ.resolve()).as_posix(),
        "formato": "png",
        "vmin": 0,
        "vmax": 1,
        "umbral_alto_ugl": resultado["umbral"],
        "generado_en": datetime.now().isoformat(timespec="seconds"),
    }


def plot_extension_floracion_series(lago: str, rows: Sequence[dict] | None = None):
    import matplotlib.pyplot as plt
    import pandas as pd

    rows = read_extension_floracion() if rows is None else rows
    df = pd.DataFrame([r for r in rows if r["lago"] == lago])
    df["fecha"] = pd.to_datetime(df["fecha"])
    df["porcentaje_alto"] = df["porcentaje_alto"].astype(float)
    df = df.sort_values("fecha")

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(df["fecha"], df["porcentaje_alto"], marker="o", linewidth=1)

    parciales = df[df["quality_flag"] == "cobertura_parcial_oficial"]
    if not parciales.empty:
        ax.scatter(
            parciales["fecha"], parciales["porcentaje_alto"], marker="x", color="black", s=90,
            zorder=3, label="cobertura parcial",
        )
        ax.legend()

    ax.set_ylabel("% de área válida con cianobacteria alta")
    ax.set_title(f"{LAGOS[lago].nombre} - extensión de valores altos ({UMBRAL_CIANOBACTERIA_ALTO_UGL} µg/L)")
    fig.tight_layout()
    return fig


def save_extension_floracion_figure(
    lago: str, rows: Sequence[dict] | None = None, *, out_path: Path | None = None
) -> Path:
    import matplotlib.pyplot as plt

    fig = plot_extension_floracion_series(lago, rows)
    out_path = (DIR_RESULTS_FIGURES / f"{lago}_extension_floracion.png") if out_path is None else out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path


# --------------------------------------------------------------------------
# Mapa interactivo (Folium)
# --------------------------------------------------------------------------


def _reproject_to_wgs84(
    array: np.ndarray, profile: dict, *, max_dim: int = 1000
) -> tuple[np.ndarray, list[list[float]]]:
    from rasterio.transform import array_bounds
    from rasterio.warp import Resampling, calculate_default_transform, reproject

    left, bottom, right, top = array_bounds(profile["height"], profile["width"], profile["transform"])
    dst_crs = "EPSG:4326"
    transform, width, height = calculate_default_transform(
        profile["crs"], dst_crs, profile["width"], profile["height"], left, bottom, right, top
    )
    # El mapa interactivo no necesita resolución nativa (10 m): limitar el
    # lado mayor a max_dim evita archivos HTML de decenas de MB por
    # incrustar una imagen de resolución completa por cada fecha.
    if max(width, height) > max_dim:
        scale = max_dim / max(width, height)
        dst_width = max(1, round(width * scale))
        dst_height = max(1, round(height * scale))
        transform, width, height = calculate_default_transform(
            profile["crs"], dst_crs, profile["width"], profile["height"], left, bottom, right, top,
            dst_width=dst_width, dst_height=dst_height,
        )
    destination = np.full((height, width), np.nan, dtype=np.float32)
    reproject(
        source=array.astype(np.float32),
        destination=destination,
        src_transform=profile["transform"],
        src_crs=profile["crs"],
        dst_transform=transform,
        dst_crs=dst_crs,
        resampling=Resampling.bilinear,
        src_nodata=np.nan,
        dst_nodata=np.nan,
    )
    dst_left, dst_bottom, dst_right, dst_top = array_bounds(height, width, transform)
    return destination, [[dst_bottom, dst_left], [dst_top, dst_right]]


def _colorize(array: np.ndarray, vmin: float, vmax: float, *, cmap: str = "YlOrRd") -> np.ndarray:
    import matplotlib.colors as mcolors
    import matplotlib.pyplot as plt

    norm = mcolors.Normalize(vmin=vmin, vmax=vmax, clip=True)
    colormap = plt.get_cmap(cmap)
    valid = np.isfinite(array)
    rgba = colormap(norm(np.where(valid, array, vmin)))
    rgba = (rgba * 255).astype(np.uint8)
    rgba[..., 3] = np.where(valid, 255, 0).astype(np.uint8)
    return rgba


def build_folium_map(lago: str, fechas: Sequence[str], *, vmin: float, vmax: float, raiz: Path | None = None):
    folium = _folium()

    lago_cfg = LAGOS[lago]
    centro = [(lago_cfg.south + lago_cfg.north) / 2, (lago_cfg.west + lago_cfg.east) / 2]
    mapa = folium.Map(location=centro, zoom_start=12, tiles="OpenStreetMap")

    for fecha in fechas:
        row = _cyano_row(lago, fecha)
        if not row.get("ruta_raster"):
            continue
        array, profile = open_index_raster(row, raiz=raiz)
        valid = combined_valid_mask(array, lago, profile)
        masked = np.where(valid, array, np.nan)
        reprojected, bounds = _reproject_to_wgs84(masked, profile)
        rgba = _colorize(reprojected, vmin, vmax)

        capa = folium.FeatureGroup(name=fecha, show=False)
        folium.raster_layers.ImageOverlay(image=rgba, bounds=bounds, opacity=0.75, name=fecha).add_to(capa)
        capa.add_to(mapa)

    boundary = load_lake_boundary_geometry(lago)
    folium.GeoJson(
        {"type": "Feature", "properties": {}, "geometry": boundary},
        name="contorno real del lago",
        style_function=lambda _feature: {"color": "blue", "weight": 2, "fill": False},
    ).add_to(mapa)

    folium.LayerControl(collapsed=False).add_to(mapa)
    return mapa


def save_folium_map(
    lago: str, fechas: Sequence[str], *, vmin: float, vmax: float,
    out_path: Path | None = None, raiz: Path | None = None,
) -> dict:
    mapa = build_folium_map(lago, fechas, vmin=vmin, vmax=vmax, raiz=raiz)
    out_path = (DIR_RESULTS_MAPS / f"{lago}_interactivo.html") if out_path is None else out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    mapa.save(str(out_path))
    return {
        "lago": lago,
        "fecha": ";".join(fechas),
        "indice": "cianobacteria",
        "tipo_mapa": "interactivo",
        "archivo": out_path.resolve().relative_to(RAIZ.resolve()).as_posix(),
        "formato": "html",
        "vmin": vmin,
        "vmax": vmax,
        "umbral_alto_ugl": "",
        "generado_en": datetime.now().isoformat(timespec="seconds"),
    }


# --------------------------------------------------------------------------
# Metadatos de mapas y fechas sospechosas
# --------------------------------------------------------------------------


def write_map_metadata(rows: Sequence[dict], path: Path | None = None) -> Path:
    path = RUTA_METADATA_MAPAS if path is None else path
    _write_csv_atomic(path, rows, METADATA_MAPAS_FIELDS)
    return path


def read_map_metadata(path: Path | None = None) -> list[dict]:
    path = RUTA_METADATA_MAPAS if path is None else path
    with Path(path).open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def suspicious_dates(lago: str | None = None, rows: Sequence[dict] | None = None) -> list[dict]:
    """Fechas de cianobacteria con `quality_flag` distinto de `calculado`.

    Usado para separar artefactos de nubosidad/cobertura de patrones
    espaciales reales; no reimplementa nada, solo filtra lo que ya calculó
    el módulo de índices.
    """

    rows = validate_manifest_indices() if rows is None else rows
    cyano = cianobacteria_rows(rows)
    if lago is not None:
        cyano = [r for r in cyano if r["lago"] == lago]
    return [r for r in cyano if r["quality_flag"] != CALIDAD_COMPLETA]


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=("fetch-boundary", "check-grid", "extension", "persistence", "maps"),
        nargs="?",
        default="extension",
    )
    parser.add_argument("--lago", choices=tuple(LAGOS))
    parser.add_argument("--fecha", help="Fecha oficial YYYY-MM-DD (solo para la acción maps)")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.action == "fetch-boundary":
        if not args.lago:
            raise ValueError("fetch-boundary requiere --lago")
        path = request_lake_boundary(args.lago)
        comparacion = compare_bbox_vs_boundary_area(args.lago)
        print(f"Contorno guardado en {path}")
        print(
            f"Área real: {comparacion['area_boundary_km2']} km2 "
            f"(bbox: {comparacion['area_bbox_km2']} km2, razón {comparacion['razon_boundary_bbox']})"
        )
        return 0

    if args.action == "check-grid":
        lagos = (args.lago,) if args.lago else tuple(LAGOS)
        for lago in lagos:
            resultado = check_grid_consistency(lago)
            print(f"- {lago}: consistente={resultado['consistente']} (referencia {resultado['fecha_referencia']})")
            for d in resultado["discrepancias"]:
                print(f"    discrepancia en {d['fecha']}")
        return 0

    if args.action == "extension":
        filas = build_extension_floracion()
        if not filas:
            print("No hay escenas de cianobacteria calculadas todavía.")
            return 0
        path = write_extension_floracion(filas)
        print(f"extension_floracion.csv escrito con {len(filas)} filas en {path}")
        return 0

    if args.action == "persistence":
        lagos = (args.lago,) if args.lago else tuple(LAGOS)
        for lago in lagos:
            resultado = persistence_raster(lago)
            paths = export_persistence_geotiffs(lago, resultado)
            print(f"- {lago}: {paths}")
        return 0

    if args.action == "maps":
        if not args.lago or not args.fecha:
            raise ValueError("maps requiere --lago y --fecha")
        metadata = save_cyano_map_png(args.lago, args.fecha)
        print(f"Mapa guardado: {metadata['archivo']}")
        return 0

    raise AssertionError(f"Acción no controlada: {args.action}")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, FileExistsError, RuntimeError, InputDataError, OverpassError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
