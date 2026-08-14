from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import timedelta
from pathlib import Path
from typing import Iterable, Sequence

try:  # Permite `python src/adquisicion.py` y `python -m src.adquisicion`.
    from .config import (
        BANDAS_MINIMAS,
        CRS_AOI,
        DIR_GEOJSON,
        DIR_INDICES,
        DIR_PROCESSED,
        DIR_RASTERS,
        DIR_RAW,
        DIR_TABLAS,
        ESCENAS_OFICIALES,
        LAGOS,
        OPENEO_BACKEND_URL,
        OPENEO_COLLECTION_ID,
        RAIZ,
        RUTA_MANIFEST_ESCENAS,
        EscenaOficial,
        Lago,
        validate_configuration,
    )
    from .raster_utils import inspect_scene_directory
except ImportError:  # pragma: no cover - ruta usada al ejecutar el archivo
    from config import (  # type: ignore
        BANDAS_MINIMAS,
        CRS_AOI,
        DIR_GEOJSON,
        DIR_INDICES,
        DIR_PROCESSED,
        DIR_RASTERS,
        DIR_RAW,
        DIR_TABLAS,
        ESCENAS_OFICIALES,
        LAGOS,
        OPENEO_BACKEND_URL,
        OPENEO_COLLECTION_ID,
        RAIZ,
        RUTA_MANIFEST_ESCENAS,
        EscenaOficial,
        Lago,
        validate_configuration,
    )
    from raster_utils import inspect_scene_directory  # type: ignore


MANIFEST_FIELDS = (
    "lago",
    "fecha",
    "satelite_oficial",
    "nubosidad_oficial_pct",
    "cobertura_valida_oficial_pct",
    "west",
    "east",
    "south",
    "north",
    "producto",
    "bandas",
    "metodo_descarga",
    "id_adquisicion",
    "estado",
    "ruta_local",
    "cobertura_valida_pct",
    "crs_salida",
    "resolucion_salida",
    "quality_flag",
    "observaciones",
)


def bbox_feature(lago: Lago) -> dict[str, object]:
    """Crea un GeoJSON del bbox de consulta, no del contorno del lago."""

    coordinates = [
        [lago.west, lago.south],
        [lago.east, lago.south],
        [lago.east, lago.north],
        [lago.west, lago.north],
        [lago.west, lago.south],
    ]
    return {
        "type": "FeatureCollection",
        "name": f"aoi_{lago.slug}_bbox",
        "crs": {"type": "name", "properties": {"name": CRS_AOI}},
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "lago": lago.slug,
                    "nombre": lago.nombre,
                    "geometry_role": "query_bbox",
                    "is_lake_boundary": False,
                    "source": "Coordenadas del enunciado del Laboratorio 4",
                },
                "geometry": {"type": "Polygon", "coordinates": [coordinates]},
            }
        ],
    }


def scene_to_manifest_row(scene: EscenaOficial) -> dict[str, object]:
    lago = LAGOS[scene.lago]
    return {
        "lago": scene.lago,
        "fecha": scene.fecha,
        "satelite_oficial": scene.satelite_oficial,
        "nubosidad_oficial_pct": f"{scene.nubosidad_oficial_pct:.2f}",
        "cobertura_valida_oficial_pct": (
            ""
            if scene.cobertura_valida_oficial_pct is None
            else f"{scene.cobertura_valida_oficial_pct:.1f}"
        ),
        "west": lago.west,
        "east": lago.east,
        "south": lago.south,
        "north": lago.north,
        "producto": OPENEO_COLLECTION_ID,
        "bandas": ";".join(BANDAS_MINIMAS),
        "metodo_descarga": "openEO Copernicus Data Space",
        "id_adquisicion": "",
        "estado": "pendiente",
        "ruta_local": "",
        "cobertura_valida_pct": "",
        "crs_salida": "",
        "resolucion_salida": "",
        "quality_flag": (
            "cobertura_parcial_oficial"
            if scene.cobertura_valida_oficial_pct is not None
            else "pendiente_descarga"
        ),
        "observaciones": scene.observacion_oficial,
    }


def expected_manifest_rows() -> list[dict[str, object]]:
    return [scene_to_manifest_row(scene) for scene in ESCENAS_OFICIALES]


def _write_csv_atomic(path: Path, rows: Sequence[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=MANIFEST_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def read_manifest(path: Path = RUTA_MANIFEST_ESCENAS) -> list[dict[str, str]]:
    with Path(path).open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def validate_manifest(path: Path = RUTA_MANIFEST_ESCENAS) -> list[dict[str, str]]:
    """Valida estructura, unicidad y cobertura de fechas del manifiesto."""

    rows = read_manifest(path)
    if len(rows) != 22:
        raise ValueError(f"El manifiesto contiene {len(rows)} filas; se esperaban 22")

    if set(rows[0]) != set(MANIFEST_FIELDS):
        missing = set(MANIFEST_FIELDS) - set(rows[0])
        extra = set(rows[0]) - set(MANIFEST_FIELDS)
        raise ValueError(f"Columnas inválidas. Faltan={sorted(missing)}, extra={sorted(extra)}")

    keys = [(row["lago"], row["fecha"]) for row in rows]
    expected = [(scene.lago, scene.fecha) for scene in ESCENAS_OFICIALES]
    if len(keys) != len(set(keys)):
        raise ValueError("El manifiesto contiene lago-fecha duplicados")
    if set(keys) != set(expected):
        raise ValueError("El manifiesto no coincide con las 22 fechas oficiales")

    for slug in LAGOS:
        if sum(row["lago"] == slug for row in rows) != 11:
            raise ValueError(f"El manifiesto no contiene 11 fechas de {slug}")
    return rows


def prepare_repository() -> dict[str, object]:
    """Crea directorios, AOI de consulta y manifiesto inicial de forma idempotente."""

    validate_configuration()
    for directory in (
        DIR_GEOJSON,
        DIR_RASTERS,
        DIR_PROCESSED,
        DIR_INDICES,
        DIR_TABLAS,
        RAIZ / "notebooks",
        RAIZ / "results" / "figures",
        RAIZ / "results" / "maps",
        RAIZ / "results" / "tables",
        RAIZ / "informe" / "secciones",
        RAIZ / "tests",
    ):
        directory.mkdir(parents=True, exist_ok=True)

    geojson_paths: list[Path] = []
    for lago in LAGOS.values():
        path = DIR_GEOJSON / f"aoi_{lago.slug}_bbox.geojson"
        expected_feature = bbox_feature(lago)
        expected_text = json.dumps(expected_feature, ensure_ascii=False, indent=2) + "\n"
        if path.exists():
            try:
                existing_feature = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise ValueError(f"GeoJSON inválido y no se sobrescribirá: {path}") from exc
            if existing_feature != expected_feature:
                raise ValueError(f"No se sobrescribirá un AOI existente distinto: {path}")
        if not path.exists():
            path.write_text(expected_text, encoding="utf-8")
        geojson_paths.append(path)

    if not RUTA_MANIFEST_ESCENAS.exists():
        _write_csv_atomic(RUTA_MANIFEST_ESCENAS, expected_manifest_rows())
    validate_manifest()

    return {
        "root": RAIZ,
        "manifest": RUTA_MANIFEST_ESCENAS,
        "geojson": geojson_paths,
        "scenes": len(ESCENAS_OFICIALES),
        "bands": BANDAS_MINIMAS,
    }


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


def query_spec(scene: EscenaOficial, bands: Sequence[str] = BANDAS_MINIMAS) -> dict[str, object]:
    """Representación auditable de la consulta openEO de un día."""

    start = scene.fecha_date()
    end = start + timedelta(days=1)
    return {
        "collection_id": OPENEO_COLLECTION_ID,
        "spatial_extent": LAGOS[scene.lago].bbox(),
        "temporal_extent": [start.isoformat(), end.isoformat()],
        "bands": list(bands),
    }


def connect_openeo(authenticate: bool = True):
    """Conecta al backend oficial; OIDC abre el flujo de autenticación del usuario."""

    try:
        import openeo
    except ImportError as exc:  # pragma: no cover - depende del entorno local
        raise RuntimeError(
            "Falta el cliente openEO. Ejecute: pip install -r requirements.txt"
        ) from exc

    connection = openeo.connect(OPENEO_BACKEND_URL)
    if authenticate:
        connection.authenticate_oidc()
    return connection


def inspect_collection(connection=None) -> dict[str, object]:
    """Comprueba que la colección y las bandas mínimas existan en el backend."""

    connection = connection or connect_openeo(authenticate=True)
    metadata = connection.describe_collection(OPENEO_COLLECTION_ID)
    dimensions = metadata.get("cube:dimensions", {})
    band_values = dimensions.get("bands", {}).get("values", [])
    if band_values:
        missing = set(BANDAS_MINIMAS) - set(band_values)
        if missing:
            raise ValueError(f"El backend no ofrece las bandas: {sorted(missing)}")
    return metadata


def _relative_paths(paths: Iterable[Path]) -> str:
    relative: list[str] = []
    for path in paths:
        try:
            relative.append(path.resolve().relative_to(RAIZ.resolve()).as_posix())
        except ValueError:
            relative.append(path.resolve().as_posix())
    return ";".join(relative)


def _update_manifest_scene(scene: EscenaOficial, **changes: object) -> None:
    rows = read_manifest()
    found = False
    for row in rows:
        if row["lago"] == scene.lago and row["fecha"] == scene.fecha:
            for key, value in changes.items():
                if key not in MANIFEST_FIELDS:
                    raise KeyError(f"Campo de manifiesto desconocido: {key}")
                row[key] = "" if value is None else str(value)
            found = True
            break
    if not found:
        raise ValueError(f"Escena no encontrada en manifiesto: {scene.lago} {scene.fecha}")
    _write_csv_atomic(RUTA_MANIFEST_ESCENAS, rows)
    validate_manifest()


def download_scene(connection, scene: EscenaOficial, bands: Sequence[str] = BANDAS_MINIMAS) -> list[Path]:
    """Ejecuta un batch job para una escena y conserva todos sus assets crudos."""

    spec = query_spec(scene, bands)
    output_dir = DIR_RASTERS / scene.lago / scene.fecha
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(
            f"La salida ya contiene archivos y no será sobrescrita: {output_dir}"
        )
    output_dir.mkdir(parents=True, exist_ok=True)

    job = None
    try:
        cube = connection.load_collection(**spec)
        result = cube.save_result(format="GTiff")
        job = result.create_job(
            title=f"lab4-{scene.lago}-{scene.fecha}-bandas-minimas",
            description=(
                "Laboratorio 4 UVG; AOI bbox oficial; "
                f"bandas {','.join(bands)}"
            ),
        )
        _update_manifest_scene(
            scene,
            id_adquisicion=job.job_id,
            estado="en_proceso",
            bandas=";".join(bands),
            quality_flag="pendiente_resultado",
        )
        job.start_and_wait()
        downloaded = [Path(path) for path in job.get_results().download_files(output_dir)]

        tif_paths = [p for p in downloaded if p.suffix.lower() in {".tif", ".tiff"}]
        if not tif_paths:
            raise RuntimeError("El batch job terminó sin entregar un GeoTIFF")

        metadata = inspect_scene_directory(output_dir)
        valid_pixels = sum(item.valid_pixels for item in metadata)
        total_pixels = sum(item.total_pixels for item in metadata)
        coverage = 100.0 * valid_pixels / total_pixels if total_pixels else 0.0
        crs = ";".join(sorted({item.crs for item in metadata}))
        resolutions = ";".join(
            sorted({f"{item.resolution_x:g}x{item.resolution_y:g}" for item in metadata})
        )
        quality = (
            "revisar_cobertura_parcial"
            if scene.cobertura_valida_oficial_pct is not None
            else "descargado_validado"
        )
        _update_manifest_scene(
            scene,
            estado="validado",
            ruta_local=_relative_paths(downloaded),
            cobertura_valida_pct=f"{coverage:.4f}",
            crs_salida=crs,
            resolucion_salida=resolutions,
            quality_flag=quality,
        )
        return downloaded
    except Exception as exc:
        _update_manifest_scene(
            scene,
            id_adquisicion="" if job is None else job.job_id,
            estado="fallido",
            quality_flag="error_descarga",
            observaciones=(
                f"{scene.observacion_oficial} | " if scene.observacion_oficial else ""
            )
            + f"Error: {type(exc).__name__}: {exc}",
        )
        raise


def download_scenes(
    scenes: Sequence[EscenaOficial],
    *,
    bands: Sequence[str] = BANDAS_MINIMAS,
    confirm_batch: bool = False,
) -> list[Path]:
    """Descarga escenas; exige confirmación explícita si se solicita más de una."""

    if len(scenes) > 1 and not confirm_batch:
        raise ValueError(
            "La descarga múltiple requiere confirm_batch=True o --confirm-batch"
        )
    connection = connect_openeo(authenticate=True)
    inspect_collection(connection)
    downloaded: list[Path] = []
    for scene in scenes:
        downloaded.extend(download_scene(connection, scene, bands))
    return downloaded


def _print_plan(scenes: Sequence[EscenaOficial], bands: Sequence[str]) -> None:
    print(f"Backend: {OPENEO_BACKEND_URL}")
    print(f"Colección: {OPENEO_COLLECTION_ID}")
    print(f"Bandas: {', '.join(bands)}")
    print(f"Escenas seleccionadas: {len(scenes)}")
    for scene in scenes:
        spec = query_spec(scene, bands)
        print(
            f"- {scene.lago} {scene.fecha}: "
            f"{spec['temporal_extent'][0]} a {spec['temporal_extent'][1]}"
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=("prepare", "validate", "plan", "check-connection", "download"),
        nargs="?",
        default="prepare",
    )
    parser.add_argument("--lago", choices=tuple(LAGOS))
    parser.add_argument("--fecha", help="Fecha oficial YYYY-MM-DD")
    parser.add_argument(
        "--bands",
        default=",".join(BANDAS_MINIMAS),
        help="Bandas separadas por coma",
    )
    parser.add_argument(
        "--confirm-batch",
        action="store_true",
        help="Confirma conscientemente más de una descarga/batch job",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    bands = tuple(item.strip().upper() for item in args.bands.split(",") if item.strip())
    if not bands:
        raise ValueError("Debe seleccionar al menos una banda")

    if args.action == "prepare":
        summary = prepare_repository()
        print(f"Preparación correcta: {summary['scenes']} escenas, bandas {summary['bands']}")
        print(f"Manifiesto: {summary['manifest']}")
        return 0

    prepare_repository()
    if args.action == "validate":
        rows = validate_manifest()
        print(f"Validación correcta: {len(rows)} escenas oficiales")
        return 0

    scenes = select_scenes(args.lago, args.fecha)
    if args.action == "plan":
        _print_plan(scenes, bands)
        return 0
    if args.action == "check-connection":
        metadata = inspect_collection()
        print(f"Conexión correcta: {metadata.get('id', OPENEO_COLLECTION_ID)}")
        return 0
    if args.action == "download":
        paths = download_scenes(scenes, bands=bands, confirm_batch=args.confirm_batch)
        print(f"Descarga completa: {len(paths)} assets")
        return 0
    raise AssertionError(f"Acción no controlada: {args.action}")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, FileExistsError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
