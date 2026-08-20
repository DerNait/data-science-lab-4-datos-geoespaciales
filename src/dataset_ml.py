"""Ejercicio 1 de la Parte 2: conjunto de datos tabular para Machine Learning.

Convierte los raster de índices ya exportados por el ejercicio 3 de la Parte I
en una tabla donde cada fila es una observación geográfica válida dentro de
alguno de los dos lagos. Reutiliza la máscara y la rejilla que esos raster ya
traen; no vuelve a descargar ni a recalcular índices.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np

try:  # Permite `python src/dataset_ml.py` y `python -m src.dataset_ml`.
    from .analisis_espacial import lake_geometry_mask
    from .config import (
        CYANO_SCRIPT,
        DIR_PROCESSED,
        DIR_RESULTS_TABLES,
        ESCENAS_OFICIALES,
        LAGOS,
        RESOLUCION_OBJETIVO_M,
        EscenaOficial,
    )
    from .correlaciones import load_scene_indices
    from .indices import (
        InputDataError,
        load_scene_bands,
        reflectance_valid_mask,
        scl_valid_mask,
        scl_water_mask,
        select_scenes,
    )
    from .indices import validate_manifest_indices
except ImportError:  # pragma: no cover - ruta usada al ejecutar el archivo
    from analisis_espacial import lake_geometry_mask  # type: ignore
    from config import (  # type: ignore
        CYANO_SCRIPT,
        DIR_PROCESSED,
        DIR_RESULTS_TABLES,
        ESCENAS_OFICIALES,
        LAGOS,
        RESOLUCION_OBJETIVO_M,
        EscenaOficial,
    )
    from correlaciones import load_scene_indices  # type: ignore
    from indices import (  # type: ignore
        InputDataError,
        load_scene_bands,
        reflectance_valid_mask,
        scl_valid_mask,
        scl_water_mask,
        select_scenes,
        validate_manifest_indices,
    )


# --------------------------------------------------------------------------
# Contrato del conjunto de datos
# --------------------------------------------------------------------------

DIR_ML = DIR_PROCESSED / "ml"
RUTA_DATASET_ML = DIR_ML / "dataset_ml.parquet"
RUTA_INVENTARIO_DATASET = DIR_RESULTS_TABLES / "inventario_dataset_ml.csv"

# Bandas L2A que quedan en la tabla. B04 se conserva porque el enunciado pide
# registrar las bandas espectrales utilizadas, aunque después no pueda usarse
# como predictora por su relación con la variable respuesta.
BANDAS_DATASET = ("B03", "B04", "B08")
BANDAS_REQUERIDAS = BANDAS_DATASET + ("SCL",)

# Los productos L2A de openEO llegan como enteros escalados. Dividir entre este
# factor devuelve reflectancia de superficie en el rango 0 a 1.
ESCALA_REFLECTANCIA = 10_000.0

# Lado del bloque de agregación medido en píxeles de 10 m. Con factor 5 cada
# fila del conjunto de datos representa una celda de 50 m por 50 m.
FACTOR_AGREGACION = 5
RESOLUCION_DATASET_M = RESOLUCION_OBJETIVO_M * FACTOR_AGREGACION
PIXELES_POR_CELDA = FACTOR_AGREGACION**2

# Una celda se conserva solo si más de la mitad de sus píxeles son válidos.
# Con 25 píxeles por celda el mínimo es 13, es decir mayoría estricta.
MIN_PIXELES_VALIDOS_CELDA = PIXELES_POR_CELDA // 2 + 1

# NDVI y NDWI son cocientes normalizados, asi que por construccion viven en
# el intervalo cerrado de -1 a 1. Sobre agua profunda la reflectancia de las
# tres bandas cae casi a cero y el denominador se vuelve inestable, lo que
# produce valores que rompen esa cota y que no describen ninguna condicion
# fisica. Se descartan a nivel de pixel antes de promediar.
RANGO_INDICE_NORMALIZADO = (-1.0, 1.0)

# Rango en el que el script de cianobacteria declara valores interpretables.
# Una concentracion de clorofila-a negativa no existe.
RANGO_CIANOBACTERIA = CYANO_SCRIPT["rango_valido"]

COLUMNAS_DATASET: tuple[tuple[str, str], ...] = (
    ("lago", "object"),
    ("fecha", "object"),
    ("x_utm", "float64"),
    ("y_utm", "float64"),
    ("lon", "float64"),
    ("lat", "float64"),
    ("B03", "float32"),
    ("B04", "float32"),
    ("B08", "float32"),
    ("ndvi", "float32"),
    ("ndwi", "float32"),
    ("cianobacteria_ugl", "float32"),
    ("n_pixeles_validos", "int16"),
    ("frac_valida", "float32"),
)

NOMBRES_COLUMNAS = tuple(nombre for nombre, _ in COLUMNAS_DATASET)

# Columnas que identifican la observación o que alimentan directamente el
# modelado. Ninguna puede quedar vacía después de la limpieza.
COLUMNAS_SIN_FALTANTES = (
    "lago",
    "fecha",
    "x_utm",
    "y_utm",
    "lon",
    "lat",
    "ndwi",
    "cianobacteria_ugl",
)

INVENTARIO_FIELDS = (
    "seccion",
    "lago",
    "fecha",
    "variable",
    "tipo",
    "n_observaciones",
    "pct_faltantes",
)

CRS_DATASET = "EPSG:32615"
CRS_GEOGRAFICO = "EPSG:4326"


class DatasetMLError(RuntimeError):
    """Falla de contrato del conjunto de datos de Machine Learning."""


# --------------------------------------------------------------------------
# Agregación espacial de 10 m a 50 m
# --------------------------------------------------------------------------


def contar_validos_por_celda(valida: np.ndarray, factor: int = FACTOR_AGREGACION) -> np.ndarray:
    """Cuenta píxeles válidos dentro de cada bloque de lado `factor`."""

    alto = valida.shape[0] // factor * factor
    ancho = valida.shape[1] // factor * factor
    recorte = valida[:alto, :ancho].astype(np.int32)
    return recorte.reshape(alto // factor, factor, ancho // factor, factor).sum(axis=(1, 3))


def promediar_por_celda(
    valores: np.ndarray, valida: np.ndarray, factor: int = FACTOR_AGREGACION
) -> np.ndarray:
    """Promedia cada bloque usando únicamente sus píxeles válidos.

    Un bloque sin ningún píxel válido queda como NaN. Los bloques incompletos
    del borde derecho e inferior se descartan porque nunca podrían alcanzar el
    mínimo de píxeles válidos exigido.
    """

    if valores.shape != valida.shape:
        raise ValueError("El array de valores y la máscara deben tener la misma forma")

    alto = valores.shape[0] // factor * factor
    ancho = valores.shape[1] // factor * factor
    recorte_valores = np.where(valida, valores, 0.0)[:alto, :ancho].astype(np.float64)
    sumas = recorte_valores.reshape(alto // factor, factor, ancho // factor, factor).sum(axis=(1, 3))
    conteos = contar_validos_por_celda(valida, factor)
    with np.errstate(invalid="ignore", divide="ignore"):
        promedio = np.where(conteos > 0, sumas / np.maximum(conteos, 1), np.nan)
    return promedio.astype(np.float32)


def centroides_de_celdas(
    profile: dict, forma_celdas: tuple[int, int], factor: int = FACTOR_AGREGACION
) -> tuple[np.ndarray, np.ndarray]:
    """Coordenadas del centro de cada celda agregada en el CRS del raster."""

    transform = profile["transform"]
    filas, columnas = np.indices(forma_celdas)
    columna_central = columnas * factor + factor / 2.0
    fila_central = filas * factor + factor / 2.0
    x = transform.c + columna_central * transform.a + fila_central * transform.b
    y = transform.f + columna_central * transform.d + fila_central * transform.e
    return x, y


def a_coordenadas_geograficas(
    x: np.ndarray, y: np.ndarray, crs_origen: str
) -> tuple[np.ndarray, np.ndarray]:
    """Reproyecta coordenadas métricas a longitud y latitud en WGS 84."""

    from rasterio.warp import transform as warp_transform

    lon, lat = warp_transform(crs_origen, CRS_GEOGRAFICO, list(x), list(y))
    return np.asarray(lon, dtype=np.float64), np.asarray(lat, dtype=np.float64)


# --------------------------------------------------------------------------
# Construcción por escena
# --------------------------------------------------------------------------


def _mismo_grid(primero: dict, segundo: dict) -> bool:
    return (
        primero["crs"] == segundo["crs"]
        and primero["transform"] == segundo["transform"]
        and primero["width"] == segundo["width"]
        and primero["height"] == segundo["height"]
    )


def en_rango(array: np.ndarray, rango: tuple[float, float]) -> np.ndarray:
    """True donde el valor cae dentro del intervalo cerrado indicado.

    Un NaN queda fuera, que es el comportamiento deseado para una máscara.
    """

    bajo, alto = rango
    with np.errstate(invalid="ignore"):
        return (array >= bajo) & (array <= alto)


def mascara_observaciones_validas(
    arrays_indices: dict, bandas: dict, profile: dict, lago: str
) -> np.ndarray:
    """Máscara de píxeles de 10 m que pueden entrar al conjunto de datos.

    Combina cinco criterios que el enunciado pide aplicar: pertenecer al
    contorno real del lago, tener valor numérico en los tres índices, no estar
    marcado como nube, sombra, nieve o saturación en SCL, no traer el valor
    nodata en ninguna banda de reflectancia, y que los tres índices caigan
    dentro del rango en que son interpretables.
    """

    scl = bandas["SCL"]
    valida = lake_geometry_mask(lago, profile)
    for nombre in ("cianobacteria", "ndvi", "ndwi"):
        valida &= np.isfinite(arrays_indices[nombre])
    valida &= scl_valid_mask(scl)
    valida &= scl_water_mask(scl)
    valida &= reflectance_valid_mask(
        *(bandas[nombre] for nombre in BANDAS_DATASET), nodata=-32768
    )
    valida &= en_rango(arrays_indices["ndvi"], RANGO_INDICE_NORMALIZADO)
    valida &= en_rango(arrays_indices["ndwi"], RANGO_INDICE_NORMALIZADO)
    valida &= en_rango(arrays_indices["cianobacteria"], RANGO_CIANOBACTERIA)
    return valida


def construir_escena(
    scene: EscenaOficial, *, rows: Sequence[dict] | None = None
) -> "object":
    """Construye la porción del conjunto de datos correspondiente a una escena."""

    import pandas as pd

    escena = load_scene_indices(scene.lago, scene.fecha, rows=rows)
    profile = escena["profile"]

    crudos = load_scene_bands(scene, BANDAS_REQUERIDAS)
    if not _mismo_grid(crudos["profile"], profile):
        raise DatasetMLError(
            f"Las bandas crudas de {scene.lago} {scene.fecha} no comparten rejilla con "
            "los raster de índices. Vuelva a ejecutar el cálculo de índices para esa escena."
        )
    bandas = crudos["arrays"]

    valida = mascara_observaciones_validas(escena["arrays"], bandas, profile, scene.lago)
    n_validos = contar_validos_por_celda(valida)
    conservar = n_validos >= MIN_PIXELES_VALIDOS_CELDA
    if not conservar.any():
        raise DatasetMLError(
            f"Ninguna celda de {RESOLUCION_DATASET_M} m de {scene.lago} {scene.fecha} alcanza "
            f"{MIN_PIXELES_VALIDOS_CELDA} píxeles válidos"
        )

    columnas: dict[str, np.ndarray] = {}
    for nombre in BANDAS_DATASET:
        reflectancia = bandas[nombre].astype(np.float32) / ESCALA_REFLECTANCIA
        columnas[nombre] = promediar_por_celda(reflectancia, valida)[conservar]
    columnas["ndvi"] = promediar_por_celda(escena["arrays"]["ndvi"], valida)[conservar]
    columnas["ndwi"] = promediar_por_celda(escena["arrays"]["ndwi"], valida)[conservar]
    columnas["cianobacteria_ugl"] = promediar_por_celda(
        escena["arrays"]["cianobacteria"], valida
    )[conservar]

    x, y = centroides_de_celdas(profile, n_validos.shape)
    x = x[conservar]
    y = y[conservar]
    lon, lat = a_coordenadas_geograficas(x, y, str(profile["crs"]))

    conteo = n_validos[conservar].astype(np.int16)
    tabla = pd.DataFrame(
        {
            "lago": scene.lago,
            "fecha": scene.fecha,
            "x_utm": x.astype(np.float64),
            "y_utm": y.astype(np.float64),
            "lon": lon,
            "lat": lat,
            **{nombre: columnas[nombre] for nombre in BANDAS_DATASET},
            "ndvi": columnas["ndvi"],
            "ndwi": columnas["ndwi"],
            "cianobacteria_ugl": columnas["cianobacteria_ugl"],
            "n_pixeles_validos": conteo,
            "frac_valida": (conteo / PIXELES_POR_CELDA).astype(np.float32),
        }
    )
    return tabla[list(NOMBRES_COLUMNAS)]


def construir_dataset(
    scenes: Sequence[EscenaOficial] | None = None, *, rows: Sequence[dict] | None = None
) -> "object":
    """Concatena todas las escenas pedidas en un solo conjunto de datos."""

    import pandas as pd

    scenes = list(ESCENAS_OFICIALES) if scenes is None else list(scenes)
    rows = validate_manifest_indices() if rows is None else rows
    partes = []
    for scene in scenes:
        parte = construir_escena(scene, rows=rows)
        print(f"- {scene.lago} {scene.fecha}: {len(parte)} observaciones de {RESOLUCION_DATASET_M} m")
        partes.append(parte)
    tabla = pd.concat(partes, ignore_index=True)
    return tabla.astype({nombre: tipo for nombre, tipo in COLUMNAS_DATASET})


def diagnostico_rango_por_escena(
    scenes: Sequence[EscenaOficial] | None = None, *, rows: Sequence[dict] | None = None
) -> list[dict[str, object]]:
    """Cuánto pierde cada escena por el filtro de rango físico de los índices.

    Separa el efecto del filtro de rango del resto de la limpieza, para poder
    señalar qué fechas traen muchos valores degenerados en lugar de dejar la
    pérdida escondida dentro del conteo final de observaciones.
    """

    scenes = list(ESCENAS_OFICIALES) if scenes is None else list(scenes)
    rows = validate_manifest_indices() if rows is None else rows
    reporte: list[dict[str, object]] = []
    for scene in scenes:
        escena = load_scene_indices(scene.lago, scene.fecha, rows=rows)
        profile = escena["profile"]
        bandas = load_scene_bands(scene, BANDAS_REQUERIDAS)["arrays"]

        previa = lake_geometry_mask(scene.lago, profile)
        for nombre in ("cianobacteria", "ndvi", "ndwi"):
            previa &= np.isfinite(escena["arrays"][nombre])
        previa &= scl_valid_mask(bandas["SCL"])
        previa &= scl_water_mask(bandas["SCL"])
        previa &= reflectance_valid_mask(
            *(bandas[nombre] for nombre in BANDAS_DATASET), nodata=-32768
        )

        posterior = previa & en_rango(escena["arrays"]["ndvi"], RANGO_INDICE_NORMALIZADO)
        posterior &= en_rango(escena["arrays"]["ndwi"], RANGO_INDICE_NORMALIZADO)
        posterior &= en_rango(escena["arrays"]["cianobacteria"], RANGO_CIANOBACTERIA)

        antes = int(previa.sum())
        despues = int(posterior.sum())
        reporte.append(
            {
                "lago": scene.lago,
                "fecha": scene.fecha,
                "pixeles_antes_del_rango": antes,
                "pixeles_despues_del_rango": despues,
                "pct_descartado_por_rango": round(100.0 * (antes - despues) / max(antes, 1), 2),
            }
        )
    return reporte


# --------------------------------------------------------------------------
# Escritura, inventario y lectura
# --------------------------------------------------------------------------


def escribir_dataset(tabla, path: Path | None = None) -> Path:
    path = RUTA_DATASET_ML if path is None else path
    path.parent.mkdir(parents=True, exist_ok=True)
    temporal = path.with_suffix(path.suffix + ".tmp")
    tabla.to_parquet(temporal, index=False)
    temporal.replace(path)
    return path


def leer_dataset(path: Path | None = None):
    import pandas as pd

    path = RUTA_DATASET_ML if path is None else path
    if not path.is_file():
        raise DatasetMLError(
            f"No existe {path}. Ejecute primero `python src/dataset_ml.py construir`."
        )
    return pd.read_parquet(path)


def construir_inventario(tabla) -> list[dict[str, object]]:
    """Resumen que responde el inciso 4 del ejercicio 1.

    Reporta el total de observaciones, el desglose por lago y por fecha, y para
    cada variable su tipo y su porcentaje de valores faltantes.
    """

    filas: list[dict[str, object]] = [
        {
            "seccion": "total",
            "lago": "",
            "fecha": "",
            "variable": "",
            "tipo": "",
            "n_observaciones": int(len(tabla)),
            "pct_faltantes": "",
        }
    ]
    for lago, cuenta in tabla.groupby("lago", sort=True).size().items():
        filas.append(
            {
                "seccion": "por_lago",
                "lago": lago,
                "fecha": "",
                "variable": "",
                "tipo": "",
                "n_observaciones": int(cuenta),
                "pct_faltantes": "",
            }
        )
    agrupado = tabla.groupby(["lago", "fecha"], sort=True).size()
    for (lago, fecha), cuenta in agrupado.items():
        filas.append(
            {
                "seccion": "por_fecha",
                "lago": lago,
                "fecha": fecha,
                "variable": "",
                "tipo": "",
                "n_observaciones": int(cuenta),
                "pct_faltantes": "",
            }
        )
    total = max(len(tabla), 1)
    # Recorre las columnas presentes y no el contrato, para que el inventario
    # de una tabla incompleta se pueda construir y la verificación sea la que
    # reporte cuál columna falta.
    for variable in [c for c in NOMBRES_COLUMNAS if c in tabla.columns]:
        faltantes = int(tabla[variable].isna().sum())
        filas.append(
            {
                "seccion": "variable",
                "lago": "",
                "fecha": "",
                "variable": variable,
                "tipo": str(tabla[variable].dtype),
                "n_observaciones": int(total - faltantes),
                "pct_faltantes": round(100.0 * faltantes / total, 4),
            }
        )
    return filas


def escribir_inventario(filas: Sequence[dict[str, object]], path: Path | None = None) -> Path:
    path = RUTA_INVENTARIO_DATASET if path is None else path
    path.parent.mkdir(parents=True, exist_ok=True)
    temporal = path.with_suffix(path.suffix + ".tmp")
    with temporal.open("w", newline="", encoding="utf-8") as stream:
        # lineterminator explícito para que el archivo quede en LF como el
        # resto de tablas versionadas del repositorio.
        writer = csv.DictWriter(stream, fieldnames=INVENTARIO_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(filas)
    temporal.replace(path)
    return path


def leer_inventario(path: Path | None = None) -> list[dict[str, str]]:
    path = RUTA_INVENTARIO_DATASET if path is None else path
    if not path.is_file():
        raise DatasetMLError(f"No existe el inventario {path}")
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


# --------------------------------------------------------------------------
# Verificaciones
# --------------------------------------------------------------------------


def verificar_entradas(*, rows: Sequence[dict] | None = None) -> dict[str, object]:
    """Comprueba que existan y sean coherentes los insumos de la Parte I.

    Falla si el manifiesto no cuadra, si algún GeoTIFF declarado no está en
    disco, si alguno no viene en EPSG:32615 a 10 m, o si faltan las bandas
    crudas de alguna escena.
    """

    import rasterio

    rows = validate_manifest_indices() if rows is None else rows
    problemas: list[str] = []

    pendientes = [r for r in rows if r["quality_flag"] == "pendiente_calculo"]
    if pendientes:
        problemas.append(
            f"{len(pendientes)} filas del manifiesto siguen en pendiente_calculo"
        )

    for row in rows:
        ruta = Path(row["ruta_raster"])
        if not ruta.is_absolute():
            ruta = Path(__file__).resolve().parent.parent / ruta
        if not ruta.is_file():
            problemas.append(f"Falta el raster {row['lago']} {row['fecha']} {row['indice']}: {ruta}")
            continue
        with rasterio.open(ruta) as dataset:
            if str(dataset.crs) != CRS_DATASET:
                problemas.append(f"{ruta.name} de {row['lago']} {row['fecha']} está en {dataset.crs}")
            if round(dataset.res[0], 3) != float(RESOLUCION_OBJETIVO_M):
                problemas.append(
                    f"{ruta.name} de {row['lago']} {row['fecha']} tiene resolución {dataset.res[0]}"
                )
            if dataset.count != 1:
                problemas.append(
                    f"{ruta.name} de {row['lago']} {row['fecha']} tiene {dataset.count} bandas"
                )

    for scene in ESCENAS_OFICIALES:
        try:
            crudos = load_scene_bands(scene, BANDAS_REQUERIDAS)
        except (InputDataError, RuntimeError) as exc:
            problemas.append(f"Bandas crudas de {scene.lago} {scene.fecha}: {exc}")
            continue
        faltantes = [b for b in BANDAS_REQUERIDAS if b not in crudos["arrays"]]
        if faltantes:
            problemas.append(f"Faltan bandas {faltantes} en {scene.lago} {scene.fecha}")

    if problemas:
        raise DatasetMLError(
            "Entradas incompletas para construir el conjunto de datos:\n  - "
            + "\n  - ".join(problemas)
        )
    return {"filas_manifiesto": len(rows), "escenas": len(ESCENAS_OFICIALES)}


def verificar_dataset(
    tabla=None, *, filas_inventario: Sequence[dict[str, str]] | None = None
) -> dict[str, object]:
    """Contrato que debe cumplir el conjunto de datos ya construido."""

    tabla = leer_dataset() if tabla is None else tabla
    filas_inventario = leer_inventario() if filas_inventario is None else filas_inventario
    problemas: list[str] = []

    if tuple(tabla.columns) != NOMBRES_COLUMNAS:
        problemas.append(
            f"Columnas inesperadas. Se esperaba {NOMBRES_COLUMNAS} y llegó {tuple(tabla.columns)}"
        )
    else:
        for nombre, tipo in COLUMNAS_DATASET:
            if str(tabla[nombre].dtype) != tipo:
                problemas.append(f"La columna {nombre} es {tabla[nombre].dtype} y debería ser {tipo}")

    combinaciones = set(map(tuple, tabla[["lago", "fecha"]].drop_duplicates().to_numpy()))
    esperadas = {(scene.lago, scene.fecha) for scene in ESCENAS_OFICIALES}
    if combinaciones != esperadas:
        problemas.append(
            f"El conjunto de datos cubre {len(combinaciones)} combinaciones lago-fecha "
            f"y se esperaban {len(esperadas)}"
        )

    for columna in COLUMNAS_SIN_FALTANTES:
        if columna in tabla.columns and tabla[columna].isna().any():
            problemas.append(f"La columna {columna} trae valores faltantes")

    for lago, config_lago in LAGOS.items():
        subconjunto = tabla[tabla["lago"] == lago]
        if subconjunto.empty:
            continue
        fuera = (
            (subconjunto["lon"] < config_lago.west)
            | (subconjunto["lon"] > config_lago.east)
            | (subconjunto["lat"] < config_lago.south)
            | (subconjunto["lat"] > config_lago.north)
        )
        if fuera.any():
            problemas.append(f"{int(fuera.sum())} observaciones de {lago} caen fuera de su caja")

    minimo = MIN_PIXELES_VALIDOS_CELDA / PIXELES_POR_CELDA
    if (tabla["frac_valida"] < minimo - 1e-6).any():
        problemas.append(f"Hay celdas con frac_valida por debajo de {minimo:.2f}")

    totales = [f for f in filas_inventario if f["seccion"] == "total"]
    if not totales:
        problemas.append("El inventario no declara la sección total")
    elif int(totales[0]["n_observaciones"]) != len(tabla):
        problemas.append(
            f"El inventario declara {totales[0]['n_observaciones']} observaciones y la tabla "
            f"tiene {len(tabla)}"
        )

    if problemas:
        raise DatasetMLError(
            "El conjunto de datos no cumple el contrato:\n  - " + "\n  - ".join(problemas)
        )
    return {
        "observaciones": int(len(tabla)),
        "combinaciones": len(combinaciones),
        "resolucion_m": RESOLUCION_DATASET_M,
    }


# --------------------------------------------------------------------------
# Interfaz de línea de comandos
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=("verificar-entradas", "construir", "verificar"),
        nargs="?",
        default="verificar-entradas",
    )
    parser.add_argument("--lago", choices=tuple(LAGOS))
    parser.add_argument("--fecha", help="Fecha oficial YYYY-MM-DD")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.action == "verificar-entradas":
        resumen = verificar_entradas()
        print(
            f"Entradas completas: {resumen['filas_manifiesto']} filas de manifiesto y "
            f"{resumen['escenas']} escenas con bandas crudas."
        )
        return 0

    if args.action == "construir":
        scenes = select_scenes(args.lago, args.fecha)
        tabla = construir_dataset(scenes)
        ruta = escribir_dataset(tabla)
        inventario = escribir_inventario(construir_inventario(tabla))
        print(f"Conjunto de datos: {len(tabla)} observaciones en {ruta}")
        print(f"Inventario: {inventario}")
        return 0

    resumen = verificar_dataset()
    print(
        f"Verificación correcta: {resumen['observaciones']} observaciones de "
        f"{resumen['resolucion_m']} m en {resumen['combinaciones']} combinaciones lago-fecha."
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (DatasetMLError, InputDataError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
