"""Validacion espacial y temporal, y generalizacion entre lagos.

Parte 2 del Laboratorio 4. Reentrena los tres modelos que ya eligio
`src/modelos.py`, con exactamente los mismos hiperparametros, bajo tres
esquemas de evaluacion distintos de la particion aleatoria 70/30: agrupando
por bloque espacial, encadenando por fecha, y cruzando entre lagos. Ninguno
de los tres vuelve a ajustar hiperparametros: el objetivo es medir cuanto
cambia el desempeno del modelo ya elegido bajo un esquema de evaluacion mas
honesto, no buscar un modelo nuevo.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Sequence

import numpy as np

try:  # Permite `python src/validacion.py` y `python -m src.validacion`.
    from .analisis_espacial import load_lake_boundary_geometry
    from .config import DIR_RESULTS_MAPS, DIR_RESULTS_TABLES, LAGOS
    from .features import COLUMNA_RESPUESTA, columnas_predictoras, leer_features
    from .modelos import (
        BETA_F,
        COLUMNAS_IDENTIDAD_LAGO,
        NOMBRES_MODELOS,
        ModelosError,
        cargar_modelo,
        columnas_para,
        metadatos_observaciones,
    )
except ImportError:  # pragma: no cover - ruta usada al ejecutar el archivo
    from analisis_espacial import load_lake_boundary_geometry  # type: ignore
    from config import DIR_RESULTS_MAPS, DIR_RESULTS_TABLES, LAGOS  # type: ignore
    from features import COLUMNA_RESPUESTA, columnas_predictoras, leer_features  # type: ignore
    from modelos import (  # type: ignore
        BETA_F,
        COLUMNAS_IDENTIDAD_LAGO,
        NOMBRES_MODELOS,
        ModelosError,
        cargar_modelo,
        columnas_para,
        metadatos_observaciones,
    )


class ValidacionError(RuntimeError):
    """Falla de contrato en la validacion espacial, temporal o de generalizacion."""


# --------------------------------------------------------------------------
# Contrato de salidas
# --------------------------------------------------------------------------

RUTA_BLOQUES = DIR_RESULTS_TABLES / "bloques_espaciales.csv"
RUTA_METRICAS_ESPACIAL = DIR_RESULTS_TABLES / "metricas_validacion_espacial.csv"
RUTA_METRICAS_TEMPORAL = DIR_RESULTS_TABLES / "metricas_validacion_temporal.csv"
RUTA_METRICAS_GENERALIZACION = DIR_RESULTS_TABLES / "metricas_generalizacion_lagos.csv"

BLOQUES_FIELDS = (
    "lago",
    "tamano_bloque_m",
    "n_bloques",
    "n_bloques_con_positivo",
    "obs_por_bloque_min",
    "obs_por_bloque_mediana",
    "obs_por_bloque_max",
)

CAMPOS_METRICA = (
    "accuracy",
    "precision",
    "recall",
    "f1",
    "f2",
    "roc_auc",
    "pr_auc",
)

CAMPOS_BASE_METRICAS = (
    "modelo",
    "n_prueba",
    "positivos_prueba",
    *CAMPOS_METRICA,
    "verdaderos_negativos",
    "falsos_positivos",
    "falsos_negativos",
    "verdaderos_positivos",
)

METRICAS_ESPACIAL_FIELDS = ("pliegue", "n_bloques_prueba", *CAMPOS_BASE_METRICAS)
METRICAS_TEMPORAL_FIELDS = ("estrategia", "fecha_prueba", "n_fechas_entrenamiento", *CAMPOS_BASE_METRICAS)
METRICAS_GENERALIZACION_FIELDS = (
    "experimento",
    "lago_entrenamiento",
    "lago_prueba",
    "positivos_entrenamiento",
    *CAMPOS_BASE_METRICAS,
)

# Numero de pliegues objetivo de GroupKFold. Con los bloques pooled de los
# dos lagos (~300 en total, ver TAMANO_BLOQUE_M abajo) hay grupos de sobra;
# el minimo con `n_grupos` es solo defensivo.
N_PLIEGUES_ESPACIAL = 5

# Decision tomada evaluando ambos tamanos con `evaluar_tamanos_bloque`
# (ver notebook 14 y results/tables/bloques_espaciales.csv): a 1 km,
# Amatitlan da 35 bloques, un margen estrecho para repartir en varios
# pliegues de GroupKFold aunque los 35 ya tengan algun positivo cada uno.
# A 500 m da del orden de 140, sin perder cobertura de positivos. Atitlan
# se deja en 1 km: su problema no es el tamano del bloque, es que solo 3 de
# sus 164 bloques concentran sus 7 positivos totales, algo que refinar la
# cuadricula no arregla porque la escasez es absoluta, no de resolucion.
TAMANO_BLOQUE_M = {"amatitlan": 500.0, "atitlan": 1000.0}

# Conjunto reducido de predictores para los experimentos de generalizacion
# entre lagos (TAREA 3). Son exactamente las cuatro columnas que ya
# documenta `modelos.COLUMNAS_IDENTIDAD_LAGO`: los dos one-hot de lago y
# las dos coordenadas absolutas, porque los dos lagos ocupan rangos de UTM
# disjuntos y un solo corte en x_utm los separa sin mirar una banda. Sin
# quitarlas, el experimento no mide nada: el conjunto de prueba completo
# cae fuera del rango de coordenadas que el modelo vio en entrenamiento y
# las columnas lago_* del otro lago ni siquiera varian.
COLUMNAS_EXCLUIDAS_GENERALIZACION = COLUMNAS_IDENTIDAD_LAGO


# --------------------------------------------------------------------------
# TAREA 1, inciso 1: cuadricula de bloques espaciales
# --------------------------------------------------------------------------


def _fila_columna_bloque(tabla_lago_xy, tamano: float) -> tuple[np.ndarray, np.ndarray]:
    """Indices (fila, columna) de bloque de `tamano` metros para un lago.

    El origen de la cuadricula es el minimo de x_utm/y_utm del propio lago,
    para que los bloques queden compactos sin depender de que los dos lagos
    ocupen rangos de UTM disjuntos.
    """

    x0 = tabla_lago_xy["x_utm"].min()
    y0 = tabla_lago_xy["y_utm"].min()
    fila = np.floor((tabla_lago_xy["y_utm"].to_numpy() - y0) / tamano).astype(np.int64)
    columna = np.floor((tabla_lago_xy["x_utm"].to_numpy() - x0) / tamano).astype(np.int64)
    return fila, columna


def evaluar_tamanos_bloque(tabla, lago: str, tamanos: Sequence[float] = (1000.0, 500.0)) -> list[dict[str, object]]:
    """Compara, para un lago, cuantos bloques y cuantos con positivo da cada tamano.

    Es el inciso 1: antes de fijar un tamano de bloque hay que comprobar que
    alcanza. Con muy pocos bloques, GroupKFold tiene poco margen para
    repartir el desbalance entre pliegues.
    """

    import pandas as pd

    subconjunto = tabla[tabla["lago"] == lago]
    filas = []
    for tamano in tamanos:
        fila, columna = _fila_columna_bloque(subconjunto, tamano)
        bloque = pd.Series(
            [f"{lago}_{f}_{c}" for f, c in zip(fila, columna)], index=subconjunto.index
        )
        conteos = bloque.value_counts()
        positivos_por_bloque = subconjunto[COLUMNA_RESPUESTA].groupby(bloque).sum()
        filas.append(
            {
                "lago": lago,
                "tamano_bloque_m": tamano,
                "n_bloques": int(bloque.nunique()),
                "n_bloques_con_positivo": int((positivos_por_bloque > 0).sum()),
                "obs_por_bloque_min": int(conteos.min()),
                "obs_por_bloque_mediana": float(conteos.median()),
                "obs_por_bloque_max": int(conteos.max()),
            }
        )
    return filas


def asignar_bloques(tabla, *, tamano_por_lago: dict[str, float] = None):
    """Agrega `bloque`, `bloque_fila` y `bloque_columna` a `tabla`.

    `tabla` debe traer `lago`, `x_utm` e `y_utm`. Cada observacion cae en
    exactamente un bloque cuadrado de `tamano_por_lago[lago]` metros.
    """

    import pandas as pd

    tamano_por_lago = TAMANO_BLOQUE_M if tamano_por_lago is None else tamano_por_lago
    partes = []
    for lago, grupo in tabla.groupby("lago", sort=False):
        tamano = tamano_por_lago[lago]
        fila, columna = _fila_columna_bloque(grupo, tamano)
        bloque = [f"{lago}_{f}_{c}" for f, c in zip(fila, columna)]
        partes.append(grupo.assign(bloque_fila=fila, bloque_columna=columna, bloque=bloque))
    return pd.concat(partes).loc[tabla.index]


def tabla_bloques(matriz=None, metadatos=None, *, tamano_por_lago: dict[str, float] = None):
    """Tabla minima (x_utm, y_utm, lago, fecha, cyano_alta, bloque) para validar y graficar."""

    matriz = leer_features() if matriz is None else matriz
    metadatos = metadatos_observaciones(matriz) if metadatos is None else metadatos
    base = matriz[["x_utm", "y_utm", COLUMNA_RESPUESTA]].join(metadatos)
    return asignar_bloques(base, tamano_por_lago=tamano_por_lago)


def resumen_bloques(tabla_bloq, *, tamano_por_lago: dict[str, float] = None) -> list[dict[str, object]]:
    """Numero de bloques y observaciones por bloque, por lago. Inciso 1."""

    tamano_por_lago = TAMANO_BLOQUE_M if tamano_por_lago is None else tamano_por_lago
    filas = []
    for lago, grupo in tabla_bloq.groupby("lago", sort=True):
        conteos = grupo.groupby("bloque").size()
        positivos_por_bloque = grupo.groupby("bloque")[COLUMNA_RESPUESTA].sum()
        filas.append(
            {
                "lago": lago,
                "tamano_bloque_m": tamano_por_lago[lago],
                "n_bloques": int(conteos.shape[0]),
                "n_bloques_con_positivo": int((positivos_por_bloque > 0).sum()),
                "obs_por_bloque_min": int(conteos.min()),
                "obs_por_bloque_mediana": float(conteos.median()),
                "obs_por_bloque_max": int(conteos.max()),
            }
        )
    return filas


def escribir_bloques(filas: Sequence[dict[str, object]], path: Path | None = None) -> Path:
    path = RUTA_BLOQUES if path is None else path
    path.parent.mkdir(parents=True, exist_ok=True)
    temporal = path.with_suffix(path.suffix + ".tmp")
    with temporal.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=BLOQUES_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(filas)
    temporal.replace(path)
    return path


def leer_bloques(path: Path | None = None) -> list[dict[str, str]]:
    path = RUTA_BLOQUES if path is None else path
    if not path.is_file():
        raise ValidacionError(f"No existe {path}. Ejecute primero `python src/validacion.py bloques`.")
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


# --------------------------------------------------------------------------
# TAREA 1, inciso 2: mapa de bloques
# --------------------------------------------------------------------------


def _geometria_utm(lago: str):
    from rasterio.warp import transform_geom
    from shapely.geometry import shape

    geometria_4326 = load_lake_boundary_geometry(lago)
    return shape(transform_geom("EPSG:4326", "EPSG:32615", geometria_4326))


def _dibujar_borde(ax, geometria_utm) -> None:
    borde = geometria_utm.boundary
    piezas = list(borde.geoms) if hasattr(borde, "geoms") else [borde]
    for pieza in piezas:
        x, y = pieza.xy
        ax.plot(x, y, color="black", linewidth=1, zorder=3)


def figura_bloques(tabla_bloq, lago: str, *, tamano_por_lago: dict[str, float] = None, out_path: Path | None = None) -> Path:
    """Mapa de los bloques espaciales de un lago, con el contorno real. Inciso 2."""

    import matplotlib.pyplot as plt

    tamano_por_lago = TAMANO_BLOQUE_M if tamano_por_lago is None else tamano_por_lago
    subconjunto = tabla_bloq[tabla_bloq["lago"] == lago]
    tamano = tamano_por_lago[lago]
    x0 = subconjunto["x_utm"].min()
    y0 = subconjunto["y_utm"].min()

    fig, ax = plt.subplots(figsize=(7, 6))
    _dibujar_borde(ax, _geometria_utm(lago))

    con_positivo = subconjunto.groupby("bloque")[COLUMNA_RESPUESTA].transform("max") > 0
    ax.scatter(
        subconjunto.loc[~con_positivo, "x_utm"], subconjunto.loc[~con_positivo, "y_utm"],
        s=3, alpha=0.5, color="#8fb8ae", label="bloque sin cyano_alta", zorder=1,
    )
    ax.scatter(
        subconjunto.loc[con_positivo, "x_utm"], subconjunto.loc[con_positivo, "y_utm"],
        s=3, alpha=0.6, color="#c0392b", label="bloque con algun cyano_alta", zorder=2,
    )

    fila_max = int(subconjunto["bloque_fila"].max())
    columna_max = int(subconjunto["bloque_columna"].max())
    for f in range(fila_max + 2):
        ax.axhline(y0 + f * tamano, color="gray", linewidth=0.4, alpha=0.5, zorder=0)
    for c in range(columna_max + 2):
        ax.axvline(x0 + c * tamano, color="gray", linewidth=0.4, alpha=0.5, zorder=0)

    ax.set_title(f"{LAGOS[lago].nombre}: bloques espaciales de {tamano:.0f} m")
    ax.set_xlabel("Este (m, UTM)")
    ax.set_ylabel("Norte (m, UTM)")
    ax.set_aspect("equal")
    ax.legend(loc="best", fontsize=8, markerscale=3)
    fig.tight_layout()

    out_path = (DIR_RESULTS_MAPS / f"{lago}_bloques_espaciales.png") if out_path is None else out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path


# --------------------------------------------------------------------------
# Metricas con manejo explicito de indefinidos
# --------------------------------------------------------------------------


def metricas_con_indefinidos(nombre: str, y_verdadero, y_predicho, y_probabilidad=None) -> dict[str, object]:
    """Como `evaluacion.metricas_modelo`, pero sin forzar a cero lo que no se
    puede calcular.

    Con el desbalance extremo de este dataset, un pliegue de validacion
    espacial o temporal puede quedar sin ninguna observacion positiva (o,
    mas raro, sin ninguna negativa). En ese caso Precision, Recall, F1, F2,
    ROC-AUC y PR-AUC no tienen definicion matematica: dependen de comparar
    contra las dos clases. Se marcan como el texto "indefinido" en vez de
    forzarlas a 0.0, que se leeria como "el modelo fallo" cuando en realidad
    el pliegue no tenia con que medirlo. Accuracy y la matriz de confusion
    siempre estan definidas, incluso en ese caso.
    """

    from sklearn.metrics import confusion_matrix

    y_verdadero = np.asarray(y_verdadero)
    y_predicho = np.asarray(y_predicho)
    vn, fp, fn, vp = confusion_matrix(y_verdadero, y_predicho, labels=[0, 1]).ravel()
    positivos = int(vp + fn)
    negativos = int(vn + fp)

    base: dict[str, object] = {
        "modelo": nombre,
        "n_prueba": int(len(y_verdadero)),
        "positivos_prueba": positivos,
        "accuracy": round(float((y_predicho == y_verdadero).mean()), 6),
        "verdaderos_negativos": int(vn),
        "falsos_positivos": int(fp),
        "falsos_negativos": int(fn),
        "verdaderos_positivos": int(vp),
    }

    if positivos == 0 or negativos == 0:
        for campo in ("precision", "recall", "f1", "f2", "roc_auc", "pr_auc"):
            base[campo] = "indefinido"
        return base

    from sklearn.metrics import average_precision_score, fbeta_score, precision_score, recall_score, roc_auc_score

    base.update(
        {
            "precision": round(float(precision_score(y_verdadero, y_predicho, zero_division=0)), 6),
            "recall": round(float(recall_score(y_verdadero, y_predicho, zero_division=0)), 6),
            "f1": round(float(fbeta_score(y_verdadero, y_predicho, beta=1.0, zero_division=0)), 6),
            "f2": round(float(fbeta_score(y_verdadero, y_predicho, beta=BETA_F, zero_division=0)), 6),
            "roc_auc": round(float(roc_auc_score(y_verdadero, y_probabilidad)), 6),
            "pr_auc": round(float(average_precision_score(y_verdadero, y_probabilidad)), 6),
        }
    )
    return base


def promedio_por_modelo(filas: Sequence[dict[str, object]]) -> dict[str, dict[str, object]]:
    """Promedia las metricas numericas de todos los pliegues, por modelo.

    Los pliegues marcados "indefinido" en una metrica no cuentan en su
    promedio: promediarlos como cero les daria un peso que no les
    corresponde, como si el modelo hubiera fallado en vez de no haber
    tenido con que medirse.
    """

    resultado: dict[str, dict[str, object]] = {}
    for nombre in NOMBRES_MODELOS:
        filas_modelo = [f for f in filas if f["modelo"] == nombre]
        resumen: dict[str, object] = {"n_pliegues": len(filas_modelo)}
        for campo in CAMPOS_METRICA:
            valores = [float(f[campo]) for f in filas_modelo if f[campo] != "indefinido"]
            resumen[f"{campo}_pliegues_definidos"] = len(valores)
            resumen[campo] = round(float(np.mean(valores)), 6) if valores else "indefinido"
        resultado[nombre] = resumen
    return resultado


def _ajustar_si_es_posible(estimador_base, X_entrenamiento, y_entrenamiento):
    """Clona y ajusta `estimador_base`, o devuelve `None` si no se puede.

    Con el desbalance de este dataset, un conjunto de entrenamiento chico (las
    primeras fechas del encadenamiento, un lago con pocos positivos) puede
    quedar con una sola clase. Ningun clasificador binario se puede ajustar
    en ese caso (`LogisticRegression` lo rechaza con un error), asi que no es
    un caso a fallar sino a reportar como tal.
    """

    from sklearn.base import clone

    if y_entrenamiento.nunique() < 2:
        return None
    modelo = clone(estimador_base)
    modelo.fit(X_entrenamiento, y_entrenamiento)
    return modelo


def _fila_sin_entrenar(nombre: str, y_prueba) -> dict[str, object]:
    """Fila de metricas cuando el entrenamiento no tuvo las dos clases.

    Se deja constancia explicita del pliegue, con su conteo real de
    positivos de prueba, en vez de omitirlo en silencio.
    """

    y_prueba = np.asarray(y_prueba)
    fila: dict[str, object] = {
        "modelo": nombre,
        "n_prueba": int(len(y_prueba)),
        "positivos_prueba": int(y_prueba.sum()),
        "accuracy": "indefinido",
        "verdaderos_negativos": "indefinido",
        "falsos_positivos": "indefinido",
        "falsos_negativos": "indefinido",
        "verdaderos_positivos": "indefinido",
    }
    for campo in ("precision", "recall", "f1", "f2", "roc_auc", "pr_auc"):
        fila[campo] = "indefinido"
    return fila


# --------------------------------------------------------------------------
# TAREA 1, incisos 3 y 4: validacion espacial con GroupKFold
# --------------------------------------------------------------------------


def _grupos_bloque(matriz, metadatos=None):
    """Serie de bloques alineada al indice de `matriz`, para usar como `groups`."""

    metadatos = metadatos_observaciones(matriz) if metadatos is None else metadatos
    base = matriz[["x_utm", "y_utm"]].join(metadatos)
    base = asignar_bloques(base)
    return base.loc[matriz.index, "bloque"]


def validar_espacial(matriz=None, *, n_pliegues: int = N_PLIEGUES_ESPACIAL) -> list[dict[str, object]]:
    """Reentrena cada modelo con GroupKFold agrupando por bloque espacial.

    Usa los mismos hiperparametros que ya eligio `modelos.py` (clona el
    estimador persistido): el punto es medir el efecto del esquema de
    validacion, no ajustar un modelo nuevo.
    """

    from sklearn.model_selection import GroupKFold

    matriz = leer_features() if matriz is None else matriz
    grupos = _grupos_bloque(matriz)
    columnas_todas = columnas_predictoras(matriz)

    filas: list[dict[str, object]] = []
    for nombre in NOMBRES_MODELOS:
        paquete = cargar_modelo(nombre)
        columnas = columnas_para(nombre, columnas_todas)
        X = matriz[columnas]
        y = matriz[COLUMNA_RESPUESTA]

        pliegues_efectivos = min(n_pliegues, grupos.nunique())
        divisor = GroupKFold(n_splits=pliegues_efectivos)
        for i, (idx_entrenamiento, idx_prueba) in enumerate(divisor.split(X, y, groups=grupos)):
            y_prueba = y.iloc[idx_prueba]
            modelo = _ajustar_si_es_posible(paquete["modelo"], X.iloc[idx_entrenamiento], y.iloc[idx_entrenamiento])
            if modelo is None:
                metricas = _fila_sin_entrenar(nombre, y_prueba)
            else:
                predicho = modelo.predict(X.iloc[idx_prueba])
                probabilidad = modelo.predict_proba(X.iloc[idx_prueba])[:, 1]
                metricas = metricas_con_indefinidos(nombre, y_prueba, predicho, probabilidad)
            metricas["pliegue"] = i
            metricas["n_bloques_prueba"] = int(grupos.iloc[idx_prueba].nunique())
            filas.append(metricas)
    return filas


def verificar_grupos_no_se_reparten(
    matriz=None, *, metadatos=None, n_pliegues: int = N_PLIEGUES_ESPACIAL
) -> None:
    """Confirma que ningun bloque cae a la vez en entrenamiento y en prueba del mismo pliegue."""

    from sklearn.model_selection import GroupKFold

    matriz = leer_features() if matriz is None else matriz
    grupos = _grupos_bloque(matriz, metadatos=metadatos)
    pliegues_efectivos = min(n_pliegues, grupos.nunique())
    divisor = GroupKFold(n_splits=pliegues_efectivos)

    for i, (idx_entrenamiento, idx_prueba) in enumerate(divisor.split(matriz, groups=grupos)):
        interseccion = set(grupos.iloc[idx_entrenamiento]) & set(grupos.iloc[idx_prueba])
        if interseccion:
            raise ValidacionError(
                f"Pliegue {i}: {len(interseccion)} bloques aparecen en entrenamiento y en prueba"
            )


# --------------------------------------------------------------------------
# TAREA 2: validacion temporal
# --------------------------------------------------------------------------


def validar_temporal_encadenado(matriz=None) -> list[dict[str, object]]:
    """Encadenamiento hacia adelante: entrena con fechas anteriores, evalua con la siguiente.

    Las primeras fechas del calendario pueden no traer todavia ningun
    positivo: ese pliegue queda marcado como sin entrenamiento posible, no
    se descarta en silencio ni se fuerza un modelo sin sentido.
    """

    matriz = leer_features() if matriz is None else matriz
    metadatos = metadatos_observaciones(matriz)
    fechas = sorted(metadatos["fecha"].unique())
    columnas_todas = columnas_predictoras(matriz)

    filas: list[dict[str, object]] = []
    for nombre in NOMBRES_MODELOS:
        paquete = cargar_modelo(nombre)
        columnas = columnas_para(nombre, columnas_todas)
        X = matriz[columnas]
        y = matriz[COLUMNA_RESPUESTA]
        for i, fecha_prueba in enumerate(fechas[1:], start=1):
            entrenamiento = metadatos["fecha"] < fecha_prueba
            prueba = metadatos["fecha"] == fecha_prueba

            y_prueba = y.loc[prueba]
            modelo = _ajustar_si_es_posible(paquete["modelo"], X.loc[entrenamiento], y.loc[entrenamiento])
            if modelo is None:
                metricas = _fila_sin_entrenar(nombre, y_prueba)
            else:
                predicho = modelo.predict(X.loc[prueba])
                probabilidad = modelo.predict_proba(X.loc[prueba])[:, 1]
                metricas = metricas_con_indefinidos(nombre, y_prueba, predicho, probabilidad)
            metricas["estrategia"] = "encadenado"
            metricas["fecha_prueba"] = fecha_prueba
            metricas["n_fechas_entrenamiento"] = i
            filas.append(metricas)
    return filas


def validar_temporal_leave_one_out(matriz=None) -> list[dict[str, object]]:
    """Deja una fecha fuera, entrena con el resto, evalua sobre esa fecha."""

    matriz = leer_features() if matriz is None else matriz
    metadatos = metadatos_observaciones(matriz)
    fechas = sorted(metadatos["fecha"].unique())
    columnas_todas = columnas_predictoras(matriz)

    filas: list[dict[str, object]] = []
    for nombre in NOMBRES_MODELOS:
        paquete = cargar_modelo(nombre)
        columnas = columnas_para(nombre, columnas_todas)
        X = matriz[columnas]
        y = matriz[COLUMNA_RESPUESTA]
        for fecha_prueba in fechas:
            entrenamiento = metadatos["fecha"] != fecha_prueba
            prueba = metadatos["fecha"] == fecha_prueba

            y_prueba = y.loc[prueba]
            modelo = _ajustar_si_es_posible(paquete["modelo"], X.loc[entrenamiento], y.loc[entrenamiento])
            if modelo is None:
                metricas = _fila_sin_entrenar(nombre, y_prueba)
            else:
                predicho = modelo.predict(X.loc[prueba])
                probabilidad = modelo.predict_proba(X.loc[prueba])[:, 1]
                metricas = metricas_con_indefinidos(nombre, y_prueba, predicho, probabilidad)
            metricas["estrategia"] = "leave_one_date_out"
            metricas["fecha_prueba"] = fecha_prueba
            metricas["n_fechas_entrenamiento"] = len(fechas) - 1
            filas.append(metricas)
    return filas


def validar_temporal(matriz=None) -> list[dict[str, object]]:
    matriz = leer_features() if matriz is None else matriz
    return validar_temporal_encadenado(matriz) + validar_temporal_leave_one_out(matriz)


# --------------------------------------------------------------------------
# TAREA 3: generalizacion entre lagos
# --------------------------------------------------------------------------


def columnas_generalizacion(columnas: Sequence[str]) -> list[str]:
    """Columnas de `columnas` que quedan tras quitar `COLUMNAS_EXCLUIDAS_GENERALIZACION`."""

    return [c for c in columnas if c not in set(COLUMNAS_EXCLUIDAS_GENERALIZACION)]


def experimento_generalizacion(nombre_modelo: str, lago_entrenamiento: str, lago_prueba: str, matriz=None) -> dict[str, object]:
    """Entrena en un lago, evalua en el otro, con el conjunto reducido de predictores.

    El modelo clonado conserva los hiperparametros ya elegidos, incluido
    `scale_pos_weight` del Gradient Boosting, calculado sobre la razon de
    desbalance del dataset completo (76.4), no la del lago de entrenamiento.
    Es deliberado: no se retunea nada para maquillar el resultado, igual que
    el resto del laboratorio. `class_weight="balanced"` (Regresion Logistica
    y Random Forest) si se recalcula solo, porque scikit-learn lo hace en
    cada llamada a `fit`.
    """

    matriz = leer_features() if matriz is None else matriz
    metadatos = metadatos_observaciones(matriz)
    columnas = columnas_generalizacion(columnas_para(nombre_modelo, columnas_predictoras(matriz)))

    entrenamiento = metadatos["lago"] == lago_entrenamiento
    prueba = metadatos["lago"] == lago_prueba

    paquete = cargar_modelo(nombre_modelo)
    y_prueba = matriz.loc[prueba, COLUMNA_RESPUESTA]
    modelo = _ajustar_si_es_posible(
        paquete["modelo"], matriz.loc[entrenamiento, columnas], matriz.loc[entrenamiento, COLUMNA_RESPUESTA]
    )
    if modelo is None:
        metricas = _fila_sin_entrenar(nombre_modelo, y_prueba)
    else:
        predicho = modelo.predict(matriz.loc[prueba, columnas])
        probabilidad = modelo.predict_proba(matriz.loc[prueba, columnas])[:, 1]
        metricas = metricas_con_indefinidos(nombre_modelo, y_prueba, predicho, probabilidad)
    metricas["experimento"] = f"{lago_entrenamiento}_a_{lago_prueba}"
    metricas["lago_entrenamiento"] = lago_entrenamiento
    metricas["lago_prueba"] = lago_prueba
    metricas["positivos_entrenamiento"] = int(matriz.loc[entrenamiento, COLUMNA_RESPUESTA].sum())
    return metricas


def validar_generalizacion(matriz=None) -> list[dict[str, object]]:
    """Experimento A (Atitlan -> Amatitlan) y Experimento B (Amatitlan -> Atitlan), los tres modelos."""

    matriz = leer_features() if matriz is None else matriz
    filas = []
    for nombre in NOMBRES_MODELOS:
        filas.append(experimento_generalizacion(nombre, "atitlan", "amatitlan", matriz))
        filas.append(experimento_generalizacion(nombre, "amatitlan", "atitlan", matriz))
    return filas


# --------------------------------------------------------------------------
# Escritura y lectura de las tablas de metricas
# --------------------------------------------------------------------------


def _escribir_csv(filas: Sequence[dict[str, object]], path: Path, fieldnames: Sequence[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporal = path.with_suffix(path.suffix + ".tmp")
    with temporal.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(filas)
    temporal.replace(path)
    return path


def _leer_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise ValidacionError(f"No existe {path}. Ejecute primero `python src/validacion.py`.")
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def escribir_metricas_espacial(filas, path: Path | None = None) -> Path:
    return _escribir_csv(filas, RUTA_METRICAS_ESPACIAL if path is None else path, METRICAS_ESPACIAL_FIELDS)


def leer_metricas_espacial(path: Path | None = None) -> list[dict[str, str]]:
    return _leer_csv(RUTA_METRICAS_ESPACIAL if path is None else path)


def escribir_metricas_temporal(filas, path: Path | None = None) -> Path:
    return _escribir_csv(filas, RUTA_METRICAS_TEMPORAL if path is None else path, METRICAS_TEMPORAL_FIELDS)


def leer_metricas_temporal(path: Path | None = None) -> list[dict[str, str]]:
    return _leer_csv(RUTA_METRICAS_TEMPORAL if path is None else path)


def escribir_metricas_generalizacion(filas, path: Path | None = None) -> Path:
    return _escribir_csv(filas, RUTA_METRICAS_GENERALIZACION if path is None else path, METRICAS_GENERALIZACION_FIELDS)


def leer_metricas_generalizacion(path: Path | None = None) -> list[dict[str, str]]:
    return _leer_csv(RUTA_METRICAS_GENERALIZACION if path is None else path)


# --------------------------------------------------------------------------
# Verificacion del contrato
# --------------------------------------------------------------------------


def verificar_asignacion_bloques(tabla_bloq=None) -> dict[str, object]:
    tabla_bloq = tabla_bloques() if tabla_bloq is None else tabla_bloq
    if tabla_bloq["bloque"].isna().any():
        raise ValidacionError("Hay observaciones sin bloque asignado")
    return {"observaciones": int(len(tabla_bloq)), "bloques_totales": int(tabla_bloq["bloque"].nunique())}


def verificar_validacion() -> dict[str, object]:
    """Contrato completo de `validacion.py`: bloques, pliegues y las cuatro tablas."""

    problemas: list[str] = []

    try:
        resumen_bloques_ok = verificar_asignacion_bloques()
    except ValidacionError as error:
        problemas.append(str(error))
        resumen_bloques_ok = {}

    try:
        verificar_grupos_no_se_reparten()
    except ValidacionError as error:
        problemas.append(str(error))

    matriz = leer_features()
    columnas_reducidas = set(columnas_generalizacion(columnas_predictoras(matriz)))
    prohibidas = columnas_reducidas & set(COLUMNAS_EXCLUIDAS_GENERALIZACION)
    if prohibidas:
        problemas.append(
            f"El conjunto reducido de generalizacion todavia contiene: {sorted(prohibidas)}"
        )

    for ruta, campo in (
        (RUTA_BLOQUES, "n_bloques"),
        (RUTA_METRICAS_ESPACIAL, "positivos_prueba"),
        (RUTA_METRICAS_TEMPORAL, "positivos_prueba"),
        (RUTA_METRICAS_GENERALIZACION, "positivos_prueba"),
    ):
        if not ruta.is_file():
            problemas.append(f"Falta la tabla {ruta}")
            continue
        filas = _leer_csv(ruta)
        if not filas:
            problemas.append(f"La tabla {ruta} esta vacia")
        elif campo not in filas[0]:
            problemas.append(f"La tabla {ruta} no trae la columna {campo}")

    for lago in LAGOS:
        mapa = DIR_RESULTS_MAPS / f"{lago}_bloques_espaciales.png"
        if not mapa.is_file():
            problemas.append(f"Falta el mapa de bloques {mapa}")

    if problemas:
        raise ValidacionError(
            "La validacion no cumple el contrato:\n  - " + "\n  - ".join(problemas)
        )

    return {
        "bloques": resumen_bloques_ok,
        "tablas": [
            str(RUTA_BLOQUES),
            str(RUTA_METRICAS_ESPACIAL),
            str(RUTA_METRICAS_TEMPORAL),
            str(RUTA_METRICAS_GENERALIZACION),
        ],
    }


# --------------------------------------------------------------------------
# Interfaz de linea de comandos
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=("bloques", "espacial", "temporal", "generalizacion", "verificar"),
        nargs="?",
        default="verificar",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.action == "bloques":
        tabla_bloq = tabla_bloques()
        filas = resumen_bloques(tabla_bloq)
        escribir_bloques(filas)
        for fila in filas:
            print(
                f"- {fila['lago']}: {fila['n_bloques']} bloques de {fila['tamano_bloque_m']:.0f} m "
                f"({fila['n_bloques_con_positivo']} con algun positivo), "
                f"{fila['obs_por_bloque_mediana']:.1f} obs/bloque en la mediana"
            )
        for lago in sorted(LAGOS):
            ruta_mapa = figura_bloques(tabla_bloq, lago)
            print(f"Mapa de {lago}: {ruta_mapa}")
        print(f"Tabla: {RUTA_BLOQUES}")
        return 0

    if args.action == "espacial":
        filas = validar_espacial()
        escribir_metricas_espacial(filas)
        for nombre, resumen in promedio_por_modelo(filas).items():
            print(f"- {nombre}: F2 promedio {resumen['f2']} en {resumen['n_pliegues']} pliegues")
        print(f"Tabla: {RUTA_METRICAS_ESPACIAL}")
        return 0

    if args.action == "temporal":
        filas = validar_temporal()
        escribir_metricas_temporal(filas)
        indefinidos = sum(1 for f in filas if f["f2"] == "indefinido")
        print(f"{len(filas)} pliegues temporales, {indefinidos} con F2 indefinido")
        print(f"Tabla: {RUTA_METRICAS_TEMPORAL}")
        return 0

    if args.action == "generalizacion":
        filas = validar_generalizacion()
        escribir_metricas_generalizacion(filas)
        for fila in filas:
            print(
                f"- {fila['experimento']}: recall {fila['recall']}  precision {fila['precision']}  "
                f"f2 {fila['f2']}  ({fila['positivos_prueba']} positivos de prueba)"
            )
        print(f"Tabla: {RUTA_METRICAS_GENERALIZACION}")
        return 0

    resumen = verificar_validacion()
    print(f"Verificacion correcta: {resumen['bloques']['bloques_totales']} bloques en total.")
    for ruta in resumen["tablas"]:
        print(f"  {ruta}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValidacionError, ModelosError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
