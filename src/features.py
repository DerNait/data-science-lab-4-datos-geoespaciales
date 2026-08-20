"""Ejercicio 3 de la Parte 2: seleccion y construccion de variables
predictoras.

Toma el conjunto de datos del ejercicio 1 mas la columna `cyano_alta` del
ejercicio 2 y construye la matriz de predictores. No reabre bandas
crudas; solo usa el contorno real del lago (ya calculado en la Parte I)
para las distancias geograficas.
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import date
from pathlib import Path
from typing import Sequence

import numpy as np

try:  # Permite `python src/features.py` y `python -m src.features`.
    from .analisis_espacial import load_lake_boundary_geometry
    from .comparacion_lagos import assign_season
    from .config import DIR_PROCESSED, DIR_RESULTS_TABLES, LAGOS, VARIABLES_EXCLUIDAS_RESPUESTA
    from .dataset_ml import DatasetMLError
    from .respuesta import COLUMNA_RESPUESTA, RespuestaError, construir_respuesta, verificar_respuesta
except ImportError:  # pragma: no cover - ruta usada al ejecutar el archivo
    from analisis_espacial import load_lake_boundary_geometry  # type: ignore
    from comparacion_lagos import assign_season  # type: ignore
    from config import (  # type: ignore
        DIR_PROCESSED,
        DIR_RESULTS_TABLES,
        LAGOS,
        VARIABLES_EXCLUIDAS_RESPUESTA,
    )
    from dataset_ml import DatasetMLError  # type: ignore
    from respuesta import (  # type: ignore
        COLUMNA_RESPUESTA,
        RespuestaError,
        construir_respuesta,
        verificar_respuesta,
    )


DIR_ML = DIR_PROCESSED / "ml"
RUTA_FEATURES_ML = DIR_ML / "features_ml.parquet"
RUTA_DICCIONARIO_PREDICTORES = DIR_RESULTS_TABLES / "diccionario_predictores.csv"
DICCIONARIO_FIELDS = ("variable", "tipo", "que_representa", "por_que_contribuye", "fuente")

# Lado (en celdas de 50 m, no en metros) de la vecindad usada para
# `ndwi_vecindad_3x3`.
LADO_VECINDAD = 3

# |rho| de Spearman por encima de este valor entre un predictor y
# cianobacteria_ugl se reporta como alarma de posible fuga oculta, pero NO
# se elimina automaticamente la variable: el enunciado pide juicio humano.
UMBRAL_ALARMA_SPEARMAN = 0.95

# Columnas identificadoras/derivadas que nunca deben tratarse como
# predictoras aunque queden en la tabla intermedia.
COLUMNAS_NO_PREDICTORAS = ("lago", "fecha", "x_utm", "y_utm", "lon", "lat", "cianobacteria_ugl", COLUMNA_RESPUESTA)


class FeaturesError(RuntimeError):
    """Falla de contrato de la matriz de predictores."""


# --------------------------------------------------------------------------
# Diccionario de predictores (inciso 2)
# --------------------------------------------------------------------------

DICCIONARIO_PREDICTORES: dict[str, dict[str, str]] = {
    "B03": {
        "tipo": "banda espectral",
        "que_representa": "Reflectancia de superficie en la banda verde (L2A), promedio de la celda de 50 m",
        "por_que_contribuye": "El agua con mas material en suspension/algas refleja distinto en verde que agua clara",
        "fuente": "Sentinel-2 L2A",
    },
    "B08": {
        "tipo": "banda espectral",
        "que_representa": "Reflectancia de superficie en el infrarrojo cercano (L2A), promedio de la celda",
        "por_que_contribuye": "El NIR es muy sensible a materia organica/algas en superficie del agua",
        "fuente": "Sentinel-2 L2A",
    },
    "ndwi": {
        "tipo": "indice",
        "que_representa": "(B03-B08)/(B03+B08); cuanto de agua limpia hay en la celda",
        "por_que_contribuye": "Cianobacteria alta suele bajar el NDWI porque la superficie deja de verse como agua limpia",
        "fuente": "Calculado en el ejercicio 3 de la Parte I",
    },
    "x_utm": {
        "tipo": "caracteristica espacial",
        "que_representa": "Coordenada este del centroide de la celda, EPSG:32615 (metros)",
        "por_que_contribuye": "Permite al modelo capturar patrones espaciales que no explican las bandas por si solas",
        "fuente": "Calculado en el ejercicio 1",
    },
    "y_utm": {
        "tipo": "caracteristica espacial",
        "que_representa": "Coordenada norte del centroide de la celda, EPSG:32615 (metros)",
        "por_que_contribuye": "Igual que x_utm: posicion absoluta dentro del lago",
        "fuente": "Calculado en el ejercicio 1",
    },
    "mes": {
        "tipo": "caracteristica temporal",
        "que_representa": "Mes calendario (1-12) de la fecha de la escena",
        "por_que_contribuye": "Aproxima variacion estacional de temperatura y lluvia que afecta el crecimiento algal",
        "fuente": "Derivado de la fecha oficial",
    },
    "dia_anio_sin": {
        "tipo": "caracteristica temporal",
        "que_representa": "Componente seno de la codificacion ciclica del dia del anio (dia 1-365/366)",
        "por_que_contribuye": "Evita el salto artificial que tendria el dia del anio como numero entero (31-dic lejos de 1-ene)",
        "fuente": "Derivado de la fecha oficial",
    },
    "dia_anio_cos": {
        "tipo": "caracteristica temporal",
        "que_representa": "Componente coseno de la codificacion ciclica del dia del anio",
        "por_que_contribuye": "Junto con dia_anio_sin, da al modelo una nocion continua y ciclica de estacionalidad",
        "fuente": "Derivado de la fecha oficial",
    },
    "frac_valida": {
        "tipo": "caracteristica de calidad",
        "que_representa": "Fraccion de pixeles de 10 m validos dentro de la celda de 50 m (0.52-1.0)",
        "por_que_contribuye": "Una celda con menos pixeles validos promedia un area mas pequena y ruidosa; no deriva de la respuesta",
        "fuente": "Calculado en el ejercicio 1",
    },
    "ratio_B03_B08": {
        "tipo": "derivada",
        "que_representa": "B03/B08: contraste verde/infrarrojo cercano",
        "por_que_contribuye": "Sensible a material particulado y biomasa en superficie, de forma distinta a B03 o B08 por separado",
        "fuente": "Ingenieria de caracteristicas, ejercicio 3.3",
    },
    "dist_orilla_m": {
        "tipo": "derivada espacial",
        "que_representa": "Distancia en metros de la celda al borde del contorno real (OSM) del lago",
        "por_que_contribuye": "Las floraciones tienden a acumularse en orillas y bahias por menor mezcla y mas nutrientes cercanos a la costa",
        "fuente": "Ingenieria de caracteristicas, ejercicio 3.3; contorno de data/raw/geojson/lago_<lago>_boundary.geojson",
    },
    "dist_centroide_m": {
        "tipo": "derivada espacial",
        "que_representa": "Distancia en metros de la celda al centroide del contorno real del lago",
        "por_que_contribuye": "Proxy de zona central (mas profunda, mas mezclada) vs. periferica",
        "fuente": "Ingenieria de caracteristicas, ejercicio 3.3",
    },
    "ndwi_vecindad_3x3": {
        "tipo": "derivada espacial",
        "que_representa": "Promedio de ndwi en la vecindad de 3x3 celdas de 50 m alrededor de esta celda, misma fecha",
        "por_que_contribuye": "Captura textura/contexto local en vez de tratar cada celda como independiente de sus vecinas",
        "fuente": "Ingenieria de caracteristicas, ejercicio 3.3",
    },
}


def _agregar_una_hot(tabla, columna: str, prefijo: str):
    import pandas as pd

    return pd.get_dummies(tabla[columna], prefix=prefijo, dtype="int8")


def _completar_diccionario_categoricas(columnas: Sequence[str]) -> None:
    for columna in columnas:
        if columna in DICCIONARIO_PREDICTORES:
            continue
        if columna.startswith("lago_"):
            DICCIONARIO_PREDICTORES[columna] = {
                "tipo": "categorica (one-hot)",
                "que_representa": f"1 si la observacion pertenece al lago {columna.split('_', 1)[1]}, si no 0",
                "por_que_contribuye": "Los dos lagos difieren en profundidad y presion urbana; permite al modelo separar su comportamiento base",
                "fuente": "One-hot de la columna lago",
            }
        elif columna.startswith("estacion_"):
            DICCIONARIO_PREDICTORES[columna] = {
                "tipo": "categorica (one-hot)",
                "que_representa": f"1 si la fecha cae en estacion {columna.split('_', 1)[1]}, si no 0",
                "por_que_contribuye": "La epoca lluviosa puede arrastrar mas nutrientes hacia el lago",
                "fuente": "One-hot de estacion (config.MESES_ESTACION_SECA/LLUVIOSA)",
            }
        elif columna in ("dia_anio_sin", "dia_anio_cos"):
            DICCIONARIO_PREDICTORES[columna] = {
                "tipo": "caracteristica temporal",
                "que_representa": "Codificacion ciclica del dia del anio (seno/coseno), para que el 31-dic quede cerca del 1-ene",
                "por_que_contribuye": "Evita el salto artificial que tendria el dia del anio como numero entero (365 lejos de 1)",
                "fuente": "Derivado de la fecha oficial",
            }


# --------------------------------------------------------------------------
# Inciso 3: ingenieria de caracteristicas
# --------------------------------------------------------------------------


def agregar_temporales(tabla):
    """mes, estacion (texto) y codificacion ciclica del dia del anio."""

    fechas = tabla["fecha"].map(date.fromisoformat)
    dia_anio = fechas.map(lambda f: f.timetuple().tm_yday).astype(float)
    angulo = 2 * np.pi * dia_anio / 365.25
    return tabla.assign(
        mes=fechas.map(lambda f: f.month).astype("int16"),
        estacion=tabla["fecha"].map(assign_season),
        dia_anio_sin=np.sin(angulo).astype("float32"),
        dia_anio_cos=np.cos(angulo).astype("float32"),
    )


def _geometrias_utm():
    """Contorno real (UTM) y su centroide, uno por lago. Se calcula una sola vez."""

    from rasterio.warp import transform_geom
    from shapely.geometry import shape

    geometrias = {}
    for lago in LAGOS:
        geometria_4326 = load_lake_boundary_geometry(lago)
        geometria_utm = shape(transform_geom("EPSG:4326", "EPSG:32615", geometria_4326))
        geometrias[lago] = {
            "borde": geometria_utm.boundary,
            "centroide": geometria_utm.centroid,
        }
    return geometrias


def agregar_distancias_geograficas(tabla):
    """dist_orilla_m y dist_centroide_m, vectorizado por lago con shapely."""

    import shapely

    geometrias = _geometrias_utm()
    dist_orilla = np.empty(len(tabla), dtype="float32")
    dist_centroide = np.empty(len(tabla), dtype="float32")

    for lago, info in geometrias.items():
        mascara = (tabla["lago"] == lago).to_numpy()
        if not mascara.any():
            continue
        puntos = shapely.points(
            tabla.loc[mascara, "x_utm"].to_numpy(), tabla.loc[mascara, "y_utm"].to_numpy()
        )
        dist_orilla[mascara] = shapely.distance(puntos, info["borde"]).astype("float32")
        dist_centroide[mascara] = shapely.distance(puntos, info["centroide"]).astype("float32")

    return tabla.assign(dist_orilla_m=dist_orilla, dist_centroide_m=dist_centroide)


def agregar_ratio_bandas(tabla):
    with np.errstate(invalid="ignore", divide="ignore"):
        ratio = np.where(tabla["B08"] != 0, tabla["B03"] / tabla["B08"], np.nan)
    return tabla.assign(ratio_B03_B08=ratio.astype("float32"))


def _indices_de_celda(tabla, lago: str, fecha: str):
    """Indices (fila, columna) enteros de cada celda de 50 m de una escena.

    Se derivan redondeando x_utm/y_utm al paso de 50 m dentro de la propia
    escena: como las celdas vienen de una rejilla regular (ejercicio 1), la
    division exacta por 50 recupera una fila y columna enteras sin volver a
    abrir el raster original.
    """

    subconjunto = tabla[(tabla["lago"] == lago) & (tabla["fecha"] == fecha)]
    paso = 50.0
    x0 = subconjunto["x_utm"].min()
    y1 = subconjunto["y_utm"].max()
    columnas = np.round((subconjunto["x_utm"].to_numpy() - x0) / paso).astype(np.int64)
    filas = np.round((y1 - subconjunto["y_utm"].to_numpy()) / paso).astype(np.int64)
    return subconjunto.index, filas, columnas


def agregar_ndwi_vecindad(tabla, *, lado: int = LADO_VECINDAD):
    """Promedio de ndwi en la vecindad de `lado` x `lado` celdas, por escena.

    Solo promedia vecinos que existen en el conjunto de datos (una celda
    descartada en el ejercicio 1 simplemente no aporta al promedio; no se
    inventa un valor para ella).
    """

    resultado = np.full(len(tabla), np.nan, dtype="float32")
    radio = lado // 2

    for (lago, fecha), _grupo in tabla.groupby(["lago", "fecha"], sort=False):
        idx, filas, columnas = _indices_de_celda(tabla, lago, fecha)
        valores = tabla.loc[idx, "ndwi"].to_numpy()
        lookup = {(f, c): v for f, c, v in zip(filas, columnas, valores)}

        promedios = np.empty(len(idx), dtype="float32")
        for pos, (f, c) in enumerate(zip(filas, columnas)):
            vecinos = [
                lookup[(f + df, c + dc)]
                for df in range(-radio, radio + 1)
                for dc in range(-radio, radio + 1)
                if (f + df, c + dc) in lookup
            ]
            promedios[pos] = float(np.mean(vecinos)) if vecinos else np.nan
        resultado[tabla.index.get_indexer(idx)] = promedios

    return tabla.assign(ndwi_vecindad_3x3=resultado)


# --------------------------------------------------------------------------
# Matriz final de predictores (inciso 1)
# --------------------------------------------------------------------------


def construir_matriz_predictores(tabla=None):
    """Construye la matriz de predictores a partir del dataset + cyano_alta.

    Excluye explicitamente todo lo que este en
    `config.VARIABLES_EXCLUIDAS_RESPUESTA` y falla si, pese a eso, alguna
    variable prohibida termina en la matriz final.
    """

    import pandas as pd

    tabla = construir_respuesta() if tabla is None else tabla
    enriquecida = agregar_temporales(tabla)
    enriquecida = agregar_ratio_bandas(enriquecida)
    enriquecida = agregar_distancias_geograficas(enriquecida)
    enriquecida = agregar_ndwi_vecindad(enriquecida)

    numericas = [
        "B03", "B08", "ndwi", "x_utm", "y_utm", "mes", "dia_anio_sin", "dia_anio_cos",
        "frac_valida", "ratio_B03_B08", "dist_orilla_m", "dist_centroide_m", "ndwi_vecindad_3x3",
    ]
    lago_dummies = _agregar_una_hot(enriquecida, "lago", "lago")
    estacion_dummies = _agregar_una_hot(enriquecida, "estacion", "estacion")
    _completar_diccionario_categoricas(list(lago_dummies.columns) + list(estacion_dummies.columns))

    matriz = pd.concat([enriquecida[numericas], lago_dummies, estacion_dummies], axis=1)
    matriz[COLUMNA_RESPUESTA] = enriquecida[COLUMNA_RESPUESTA].to_numpy()

    # `ratio_B03_B08` no esta definido si B08 promedia exactamente 0 en la
    # celda (agua muy profunda y clara, sobre todo en Atitlan: 14 de
    # ~492 mil celdas, 0.003%). No se inventa un valor: se documenta y se
    # descartan esas filas de la matriz final, igual que el resto del
    # laboratorio descarta en vez de rellenar cuando una formula queda
    # indefinida.
    invalidas = matriz[list(numericas)].isna().any(axis=1) | np.isinf(
        matriz[list(numericas)].to_numpy(dtype="float64")
    ).any(axis=1)
    if invalidas.any():
        # No se reindexa: se conserva el indice original para que quien
        # llame pueda alinear cianobacteria_ugl u otras columnas del
        # dataset base contra las mismas filas que sobrevivieron aqui.
        matriz = matriz.loc[~invalidas]

    verificar_anti_fuga(matriz.columns)
    return matriz


def verificar_anti_fuga(columnas: Sequence[str]) -> None:
    prohibidas = set(columnas) & set(VARIABLES_EXCLUIDAS_RESPUESTA)
    if prohibidas:
        raise FeaturesError(
            "Variables prohibidas por fuga se colaron en la matriz de predictores: "
            f"{sorted(prohibidas)}"
        )


def columnas_predictoras(matriz) -> list[str]:
    return [c for c in matriz.columns if c != COLUMNA_RESPUESTA]


# --------------------------------------------------------------------------
# Diccionario de predictores (CSV)
# --------------------------------------------------------------------------


def construir_diccionario(columnas_matriz: Sequence[str]) -> list[dict[str, str]]:
    filas = []
    for variable in columnas_matriz:
        if variable == COLUMNA_RESPUESTA:
            continue
        info = DICCIONARIO_PREDICTORES.get(variable)
        if info is None:
            raise FeaturesError(f"Falta documentar la variable '{variable}' en DICCIONARIO_PREDICTORES")
        filas.append({"variable": variable, **info})
    return filas


def escribir_diccionario(filas: Sequence[dict[str, str]], path: Path | None = None) -> Path:
    path = RUTA_DICCIONARIO_PREDICTORES if path is None else path
    path.parent.mkdir(parents=True, exist_ok=True)
    temporal = path.with_suffix(path.suffix + ".tmp")
    with temporal.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=DICCIONARIO_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(filas)
    temporal.replace(path)
    return path


def leer_diccionario(path: Path | None = None) -> list[dict[str, str]]:
    path = RUTA_DICCIONARIO_PREDICTORES if path is None else path
    if not path.is_file():
        raise FeaturesError(f"No existe {path}")
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


# --------------------------------------------------------------------------
# Chequeo de alarma (no de exclusion automatica)
# --------------------------------------------------------------------------


def alarma_correlacion_spearman(matriz, cianobacteria_ugl, *, umbral: float = UMBRAL_ALARMA_SPEARMAN):
    """Spearman de cada predictor contra cianobacteria_ugl. Solo informa.

    `cianobacteria_ugl` se pasa aparte (no vive en la matriz de
    predictores, precisamente porque es la variable prohibida por fuga).
    """

    from scipy.stats import spearmanr

    alarmas = []
    for columna in columnas_predictoras(matriz):
        valores = matriz[columna]
        if valores.nunique() < 2:
            continue
        rho, _p = spearmanr(valores, cianobacteria_ugl)
        if abs(rho) > umbral:
            alarmas.append({"variable": columna, "rho_spearman": round(float(rho), 4)})
    return alarmas


# --------------------------------------------------------------------------
# Escritura, lectura y verificacion
# --------------------------------------------------------------------------


def escribir_features(matriz, path: Path | None = None) -> Path:
    # Reutiliza el mismo filesystem de pyarrow que dataset_ml.py: crearlo
    # antes de que rasterio abra un archivo evita el choque de registro
    # "Attempted to register factory for scheme 'file'..." con GDAL.
    try:
        from .dataset_ml import _PARQUET_FILESYSTEM
    except ImportError:  # pragma: no cover
        from dataset_ml import _PARQUET_FILESYSTEM  # type: ignore

    path = RUTA_FEATURES_ML if path is None else path
    path.parent.mkdir(parents=True, exist_ok=True)
    temporal = path.with_suffix(path.suffix + ".tmp")
    matriz.to_parquet(temporal, index=False, filesystem=_PARQUET_FILESYSTEM)
    temporal.replace(path)
    return path


def leer_features(path: Path | None = None):
    import pandas as pd

    try:
        from .dataset_ml import _PARQUET_FILESYSTEM
    except ImportError:  # pragma: no cover
        from dataset_ml import _PARQUET_FILESYSTEM  # type: ignore

    path = RUTA_FEATURES_ML if path is None else path
    if not path.is_file():
        raise FeaturesError(f"No existe {path}. Ejecute primero `python src/features.py construir`.")
    return pd.read_parquet(path, filesystem=_PARQUET_FILESYSTEM)


def verificar_features(matriz=None, *, filas_diccionario: Sequence[dict[str, str]] | None = None) -> dict[str, object]:
    tabla_base = construir_respuesta()
    matriz = leer_features() if matriz is None else matriz
    filas_diccionario = leer_diccionario() if filas_diccionario is None else filas_diccionario
    problemas: list[str] = []

    # La matriz nunca puede tener MAS filas que el dataset base. Puede tener
    # unas pocas menos: construir_matriz_predictores descarta las celdas
    # donde una variable derivada queda indefinida (ej. ratio_B03_B08 con
    # B08=0), en vez de inventar un valor. Se exige que esa diferencia sea
    # pequena (menos del 1%) para no dejar pasar en silencio un problema
    # mayor de la ingenieria de caracteristicas.
    diferencia = len(tabla_base) - len(matriz)
    if diferencia < 0:
        problemas.append(
            f"La matriz tiene {len(matriz)} filas, mas que las {len(tabla_base)} del dataset base"
        )
    elif diferencia > 0.01 * len(tabla_base):
        problemas.append(
            f"La matriz tiene {diferencia} filas menos que el dataset base "
            f"({100 * diferencia / len(tabla_base):.2f}%), mas de lo esperado por variables derivadas indefinidas"
        )

    prohibidas = set(matriz.columns) & set(VARIABLES_EXCLUIDAS_RESPUESTA)
    if prohibidas:
        problemas.append(f"Columnas prohibidas presentes: {sorted(prohibidas)}")

    predictoras = columnas_predictoras(matriz)
    for columna in predictoras:
        valores = matriz[columna].to_numpy(dtype="float64", na_value=np.nan)
        if np.isnan(valores).any():
            problemas.append(f"La columna {columna} tiene NaN")
        if np.isinf(valores).any():
            problemas.append(f"La columna {columna} tiene valores infinitos")

    documentadas = {f["variable"] for f in filas_diccionario}
    if documentadas != set(predictoras):
        faltan = set(predictoras) - documentadas
        sobran = documentadas - set(predictoras)
        if faltan:
            problemas.append(f"Faltan en el diccionario: {sorted(faltan)}")
        if sobran:
            problemas.append(f"El diccionario documenta columnas que no estan en la matriz: {sorted(sobran)}")

    if problemas:
        raise FeaturesError(
            "La matriz de predictores no cumple el contrato:\n  - " + "\n  - ".join(problemas)
        )
    return {
        "filas": int(len(matriz)),
        "predictores": len(predictoras),
        "filas_excluidas_por_variable_derivada_indefinida": int(diferencia),
    }


# --------------------------------------------------------------------------
# Interfaz de linea de comandos
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("construir", "verificar"), nargs="?", default="verificar")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.action == "construir":
        verificar_respuesta()  # gate: no construir sobre una respuesta rota
        tabla_resp = construir_respuesta()
        matriz = construir_matriz_predictores(tabla_resp)
        ruta = escribir_features(matriz)
        filas_dic = construir_diccionario(matriz.columns)
        ruta_dic = escribir_diccionario(filas_dic)
        print(f"Matriz de predictores: {len(matriz)} filas, {len(columnas_predictoras(matriz))} predictores en {ruta}")
        print(f"Diccionario escrito en {ruta_dic}")

        alarmas = alarma_correlacion_spearman(matriz, tabla_resp.loc[matriz.index, "cianobacteria_ugl"])
        if alarmas:
            print(f"ALARMA: {len(alarmas)} predictor(es) con |rho Spearman| > {UMBRAL_ALARMA_SPEARMAN} "
                  "contra cianobacteria_ugl (revisar, no se eliminan automaticamente):")
            for a in alarmas:
                print(f"  - {a['variable']}: rho={a['rho_spearman']}")
        else:
            print(f"Sin alarmas de correlacion (umbral |rho| > {UMBRAL_ALARMA_SPEARMAN}).")
        return 0

    resumen = verificar_features()
    print(f"Verificacion correcta: {resumen['filas']} filas, {resumen['predictores']} predictores.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FeaturesError, RespuestaError, DatasetMLError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
