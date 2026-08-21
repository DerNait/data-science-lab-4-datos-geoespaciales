"""Construccion de modelos de clasificacion de alta presencia de cianobacteria.

Entrena Regresion Logistica, Random Forest y Gradient Boosting sobre la matriz
de predictores del ejercicio 3, con una division estratificada 70/30 de semilla
fija que queda persistida en disco.

Esa particion es un contrato: el enunciado exige mantener el mismo conjunto de
prueba para comparar los modelos de forma justa, y los ejercicios posteriores de
validacion, generalizacion e interpretabilidad deben reutilizarla en lugar de
volver a dividir los datos.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Sequence

import numpy as np

try:  # Permite `python src/modelos.py` y `python -m src.modelos`.
    from .config import DIR_PROCESSED, DIR_RESULTS_TABLES
    from .dataset_ml import leer_dataset
    from .features import COLUMNA_RESPUESTA, columnas_predictoras, leer_features
except ImportError:  # pragma: no cover - ruta usada al ejecutar el archivo
    from config import DIR_PROCESSED, DIR_RESULTS_TABLES  # type: ignore
    from dataset_ml import leer_dataset  # type: ignore
    from features import COLUMNA_RESPUESTA, columnas_predictoras, leer_features  # type: ignore


# --------------------------------------------------------------------------
# Contrato de la particion y de los modelos
# --------------------------------------------------------------------------

DIR_ML = DIR_PROCESSED / "ml"
DIR_MODELOS = DIR_ML / "modelos"
RUTA_PARTICION = DIR_ML / "particion_70_30.parquet"
RUTA_HIPERPARAMETROS = DIR_RESULTS_TABLES / "hiperparametros_modelos.csv"

# Semilla unica de todo el laboratorio. Cambiarla invalida la particion ya
# persistida y obliga a reentrenar los tres modelos.
SEMILLA = 42

FRACCION_PRUEBA = 0.30

ETIQUETA_ENTRENAMIENTO = "entrenamiento"
ETIQUETA_PRUEBA = "prueba"

PARTICION_FIELDS = ("indice", "lago", "fecha", "particion")

NOMBRES_MODELOS = ("regresion_logistica", "random_forest", "gradient_boosting")

# `lago_amatitlan` con `lago_atitlan`, y `estacion_lluviosa` con `estacion_seca`,
# suman exactamente 1 en cada fila. Para un modelo lineal con intercepto eso es
# colinealidad perfecta, asi que se elimina una columna de cada par. Los modelos
# de arboles no la sufren y conservan las cuatro.
COLUMNAS_REDUNDANTES_LINEAL = ("lago_atitlan", "estacion_seca")

# Cuatro columnas revelan de que lago viene cada observacion. Las dos obvias son
# los one-hot, pero `x_utm` e `y_utm` hacen lo mismo de forma implicita: los dos
# lagos ocupan rangos de UTM disjuntos, asi que un solo corte en `x_utm` separa
# Atitlan de Amatitlan sin mirar una sola banda. Como Atitlan aporta 7 celdas
# positivas de 432,035 y Amatitlan el 10.48 por ciento, saber el lago casi
# determina la respuesta.
#
# Se conservan en el modelo principal, porque el enunciado no las prohibe y la
# posicion es informacion geografica legitima, pero existe una variante de
# diagnostico sin las cuatro para medir cuanto del desempeno es firma espectral
# y cuanto es simplemente saber en que lago esta la celda. Quitar solo los
# one-hot no sirve de nada: el modelo se pasa a `x_utm` y el desempeno no cambia.
#
# Este mismo conjunto reducido es el que necesita el ejercicio de generalizacion
# entre lagos, donde dejar estas columnas convierte al modelo en un detector de
# lago en vez de un detector de cianobacteria.
COLUMNAS_IDENTIDAD_LAGO = ("lago_amatitlan", "lago_atitlan", "x_utm", "y_utm")

SUFIJO_VARIANTE_SIN_LAGO = "sin_identidad_lago"

# Beta del F-score usado para elegir hiperparametros. Con beta = 2 el Recall
# pesa cuatro veces mas que la Precision, que es lo que corresponde cuando el
# error costoso es no detectar una floracion. La justificacion ambiental
# completa vive en el modulo de evaluacion.
BETA_F = 2.0

HIPERPARAMETROS_FIELDS = (
    "modelo",
    "hiperparametro",
    "valores_evaluados",
    "valor_elegido",
)


class ModelosError(RuntimeError):
    """Falla de contrato en la particion o en los modelos entrenados."""


# --------------------------------------------------------------------------
# Particion estratificada 70/30
# --------------------------------------------------------------------------


def metadatos_observaciones(matriz=None):
    """Recupera `lago` y `fecha` de cada fila de la matriz de predictores.

    La matriz no arrastra esas dos columnas porque no son predictoras, pero
    conserva el indice original del dataset. Alinear por ese indice permite
    devolverlas sin recalcular nada, y son las que necesitan la validacion
    espacial y la temporal para agrupar.
    """

    matriz = leer_features() if matriz is None else matriz
    dataset = leer_dataset()
    faltantes = matriz.index.difference(dataset.index)
    if len(faltantes):
        raise ModelosError(
            f"{len(faltantes)} filas de la matriz de predictores no existen en el dataset base; "
            "reconstruya ambos artefactos desde cero."
        )
    return dataset.loc[matriz.index, ["lago", "fecha"]]


def construir_particion(
    matriz=None,
    *,
    semilla: int = SEMILLA,
    fraccion_prueba: float = FRACCION_PRUEBA,
    metadatos=None,
):
    """Divide la matriz en 70 por ciento entrenamiento y 30 por ciento prueba.

    La division es estratificada por la variable respuesta porque solo el 1.29
    por ciento de las observaciones es positivo: una division simple podria
    dejar el conjunto de prueba practicamente sin casos de alta presencia.
    """

    import pandas as pd
    from sklearn.model_selection import train_test_split

    matriz = leer_features() if matriz is None else matriz
    metadatos = metadatos_observaciones(matriz) if metadatos is None else metadatos

    indices_entrenamiento, indices_prueba = train_test_split(
        matriz.index.to_numpy(),
        test_size=fraccion_prueba,
        random_state=semilla,
        stratify=matriz[COLUMNA_RESPUESTA].to_numpy(),
        shuffle=True,
    )

    particion = pd.DataFrame(
        {
            "indice": matriz.index.to_numpy(),
            "lago": metadatos["lago"].to_numpy(),
            "fecha": metadatos["fecha"].to_numpy(),
            "particion": ETIQUETA_ENTRENAMIENTO,
        }
    )
    particion.loc[particion["indice"].isin(indices_prueba), "particion"] = ETIQUETA_PRUEBA
    return particion[list(PARTICION_FIELDS)]


def escribir_particion(particion, path: Path | None = None) -> Path:
    path = RUTA_PARTICION if path is None else path
    path.parent.mkdir(parents=True, exist_ok=True)
    temporal = path.with_suffix(path.suffix + ".tmp")
    particion.to_parquet(temporal, index=False)
    temporal.replace(path)
    return path


def cargar_particion(path: Path | None = None):
    """Lee la particion persistida. Es el punto de entrada de los otros modulos."""

    import pandas as pd

    path = RUTA_PARTICION if path is None else path
    if not path.is_file():
        raise ModelosError(
            f"No existe {path}. Ejecute primero `python src/modelos.py entrenar`."
        )
    return pd.read_parquet(path)


def dividir(matriz=None, particion=None):
    """Devuelve X e y de entrenamiento y de prueba segun la particion persistida."""

    matriz = leer_features() if matriz is None else matriz
    particion = cargar_particion() if particion is None else particion

    entrenamiento = particion.loc[particion["particion"] == ETIQUETA_ENTRENAMIENTO, "indice"]
    prueba = particion.loc[particion["particion"] == ETIQUETA_PRUEBA, "indice"]

    columnas = columnas_predictoras(matriz)
    return {
        "X_entrenamiento": matriz.loc[entrenamiento, columnas],
        "y_entrenamiento": matriz.loc[entrenamiento, COLUMNA_RESPUESTA],
        "X_prueba": matriz.loc[prueba, columnas],
        "y_prueba": matriz.loc[prueba, COLUMNA_RESPUESTA],
    }


# --------------------------------------------------------------------------
# Definicion de los tres modelos y su espacio de busqueda
# --------------------------------------------------------------------------


def columnas_para(nombre: str, columnas: Sequence[str]) -> list[str]:
    """Columnas que recibe cada modelo.

    Solo el modelo lineal descarta los one-hot redundantes; los de arboles
    trabajan con el conjunto completo.
    """

    if nombre == "regresion_logistica":
        return [c for c in columnas if c not in COLUMNAS_REDUNDANTES_LINEAL]
    return list(columnas)


def peso_clase_positiva(y) -> float:
    """Razon entre negativos y positivos, para `scale_pos_weight` del boosting."""

    positivos = int(np.sum(np.asarray(y) == 1))
    negativos = int(np.sum(np.asarray(y) == 0))
    if positivos == 0:
        raise ModelosError("No hay observaciones positivas en el conjunto de entrenamiento")
    return negativos / positivos


def definir_modelos(y_entrenamiento) -> dict[str, dict]:
    """Estimadores base y espacio de hiperparametros de cada modelo.

    Los tres compensan el desbalance de clases de forma explicita: los dos
    primeros reponderando la clase positiva y el tercero con `scale_pos_weight`.
    Sin eso, con 1.29 por ciento de positivos, los tres aprenderian a predecir
    siempre ausencia.
    """

    from sklearn.ensemble import RandomForestClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from xgboost import XGBClassifier

    escala_positiva = peso_clase_positiva(y_entrenamiento)

    return {
        "regresion_logistica": {
            # Las variables van en unidades muy distintas, de reflectancia entre
            # 0 y 1 a metros en decenas de miles, asi que el escalado es
            # necesario. Va dentro de un Pipeline para que se ajuste solo con el
            # pliegue de entrenamiento de cada validacion cruzada.
            "estimador": Pipeline(
                [
                    ("escalado", StandardScaler()),
                    (
                        "modelo",
                        LogisticRegression(
                            class_weight="balanced",
                            max_iter=1000,
                            random_state=SEMILLA,
                        ),
                    ),
                ]
            ),
            # `penalty` quedo deprecado en scikit-learn 1.8, asi que se deja la
            # regularizacion L2 por defecto y solo se busca su intensidad.
            "espacio": {
                "modelo__C": [0.01, 0.1, 1.0, 10.0],
                "modelo__solver": ["lbfgs", "liblinear"],
            },
        },
        "random_forest": {
            "estimador": RandomForestClassifier(
                class_weight="balanced_subsample",
                random_state=SEMILLA,
                n_jobs=-1,
            ),
            "espacio": {
                "n_estimators": [200, 400],
                "max_depth": [None, 12, 20],
                "min_samples_leaf": [1, 5, 20],
                "max_features": ["sqrt", 0.5],
            },
        },
        "gradient_boosting": {
            "estimador": XGBClassifier(
                objective="binary:logistic",
                tree_method="hist",
                eval_metric="aucpr",
                scale_pos_weight=escala_positiva,
                random_state=SEMILLA,
                n_jobs=-1,
            ),
            "espacio": {
                "n_estimators": [200, 400, 600],
                "max_depth": [3, 6, 9],
                "learning_rate": [0.03, 0.1, 0.3],
                "subsample": [0.8, 1.0],
                "colsample_bytree": [0.8, 1.0],
            },
        },
    }


def puntuador_f_beta():
    """Scorer de F-beta con beta = 2, usado para elegir hiperparametros."""

    from sklearn.metrics import fbeta_score, make_scorer

    return make_scorer(fbeta_score, beta=BETA_F, zero_division=0)


# --------------------------------------------------------------------------
# Ajuste de hiperparametros y entrenamiento
# --------------------------------------------------------------------------


def ajustar_hiperparametros(
    nombre: str,
    definicion: dict,
    X,
    y,
    *,
    n_iteraciones: int = 8,
    pliegues: int = 3,
):
    """Busqueda aleatoria de hiperparametros con validacion cruzada estratificada.

    Se busca sobre el conjunto de entrenamiento y nunca sobre el de prueba, que
    queda intacto para la comparacion final entre modelos. El criterio de
    seleccion es F-beta con beta = 2 porque el error que importa reducir es el
    falso negativo.
    """

    from sklearn.model_selection import RandomizedSearchCV, StratifiedKFold

    busqueda = RandomizedSearchCV(
        estimator=definicion["estimador"],
        param_distributions=definicion["espacio"],
        n_iter=n_iteraciones,
        scoring=puntuador_f_beta(),
        cv=StratifiedKFold(n_splits=pliegues, shuffle=True, random_state=SEMILLA),
        random_state=SEMILLA,
        n_jobs=1 if nombre != "regresion_logistica" else -1,
        refit=True,
        error_score="raise",
    )
    busqueda.fit(X, y)
    return busqueda


def filas_hiperparametros(nombre: str, definicion: dict, busqueda) -> list[dict[str, str]]:
    """Deja por escrito que se evaluo y que se eligio, como pide el inciso 3."""

    filas = []
    for hiperparametro, valores in sorted(definicion["espacio"].items()):
        filas.append(
            {
                "modelo": nombre,
                "hiperparametro": hiperparametro,
                "valores_evaluados": json.dumps(list(valores), ensure_ascii=False),
                "valor_elegido": json.dumps(
                    busqueda.best_params_.get(hiperparametro), ensure_ascii=False
                ),
            }
        )
    filas.append(
        {
            "modelo": nombre,
            "hiperparametro": f"f{BETA_F:.0f}_validacion_cruzada",
            "valores_evaluados": "",
            "valor_elegido": f"{busqueda.best_score_:.6f}",
        }
    )
    return filas


def ruta_modelo(nombre: str) -> Path:
    return DIR_MODELOS / f"{nombre}.joblib"


def guardar_modelo(nombre: str, modelo, columnas: Sequence[str]) -> Path:
    import joblib

    DIR_MODELOS.mkdir(parents=True, exist_ok=True)
    destino = ruta_modelo(nombre)
    joblib.dump({"modelo": modelo, "columnas": list(columnas)}, destino)
    return destino


def cargar_modelo(nombre: str) -> dict:
    """Carga un modelo entrenado junto con la lista de columnas que espera."""

    import joblib

    origen = ruta_modelo(nombre)
    if not origen.is_file():
        raise ModelosError(
            f"No existe el modelo {nombre} en {origen}. "
            "Ejecute primero `python src/modelos.py entrenar`."
        )
    return joblib.load(origen)


def entrenar_variante(
    nombre: str,
    *,
    columnas_excluidas: Sequence[str] = COLUMNAS_IDENTIDAD_LAGO,
    sufijo: str = SUFIJO_VARIANTE_SIN_LAGO,
    matriz=None,
):
    """Reentrena un modelo ya ajustado quitandole algunas columnas.

    Conserva los hiperparametros que eligio la busqueda original y solo cambia
    el conjunto de entrada, de modo que la diferencia de desempeno se pueda
    atribuir a las columnas retiradas y no a otro ajuste.
    """

    from sklearn.base import clone

    matriz = leer_features() if matriz is None else matriz
    datos = dividir(matriz)
    base = cargar_modelo(nombre)
    columnas = [c for c in base["columnas"] if c not in set(columnas_excluidas)]

    modelo = clone(base["modelo"])
    modelo.fit(datos["X_entrenamiento"][columnas], datos["y_entrenamiento"])
    guardar_modelo(f"{nombre}__{sufijo}", modelo, columnas)
    return {"modelo": modelo, "columnas": columnas}


def escribir_hiperparametros(filas: Sequence[dict[str, str]], path: Path | None = None) -> Path:
    path = RUTA_HIPERPARAMETROS if path is None else path
    path.parent.mkdir(parents=True, exist_ok=True)
    temporal = path.with_suffix(path.suffix + ".tmp")
    with temporal.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=HIPERPARAMETROS_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(filas)
    temporal.replace(path)
    return path


def entrenar_todos(*, n_iteraciones: int = 8, pliegues: int = 3) -> dict[str, object]:
    """Construye la particion, ajusta hiperparametros y entrena los tres modelos."""

    matriz = leer_features()
    particion = construir_particion(matriz)
    escribir_particion(particion)

    datos = dividir(matriz, particion)
    X = datos["X_entrenamiento"]
    y = datos["y_entrenamiento"]
    print(
        f"Entrenamiento: {len(X)} observaciones, {int(y.sum())} positivas "
        f"({100 * y.mean():.4f} %)"
    )
    print(
        f"Prueba:        {len(datos['X_prueba'])} observaciones, "
        f"{int(datos['y_prueba'].sum())} positivas "
        f"({100 * datos['y_prueba'].mean():.4f} %)"
    )

    definiciones = definir_modelos(y)
    filas: list[dict[str, str]] = []
    for nombre in NOMBRES_MODELOS:
        columnas = columnas_para(nombre, list(X.columns))
        busqueda = ajustar_hiperparametros(
            nombre,
            definiciones[nombre],
            X[columnas],
            y,
            n_iteraciones=n_iteraciones,
            pliegues=pliegues,
        )
        guardar_modelo(nombre, busqueda.best_estimator_, columnas)
        filas.extend(filas_hiperparametros(nombre, definiciones[nombre], busqueda))
        print(
            f"- {nombre}: F{BETA_F:.0f} de validacion cruzada {busqueda.best_score_:.4f} "
            f"con {busqueda.best_params_}"
        )

    escribir_hiperparametros(filas)
    return {
        "particion": RUTA_PARTICION,
        "modelos": [str(ruta_modelo(n)) for n in NOMBRES_MODELOS],
        "hiperparametros": RUTA_HIPERPARAMETROS,
    }


# --------------------------------------------------------------------------
# Verificacion del contrato
# --------------------------------------------------------------------------


def verificar_particion(
    matriz=None, particion=None, *, semilla: int = SEMILLA, metadatos=None
) -> dict[str, object]:
    """Comprueba que la particion persistida sigue siendo la declarada.

    Es lo que garantiza que los ejercicios posteriores evaluen sobre exactamente
    el mismo conjunto de prueba.
    """

    matriz = leer_features() if matriz is None else matriz
    particion = cargar_particion() if particion is None else particion
    problemas: list[str] = []

    if tuple(particion.columns) != PARTICION_FIELDS:
        problemas.append(
            f"Columnas de la particion inesperadas: {tuple(particion.columns)}"
        )

    entrenamiento = set(particion.loc[particion["particion"] == ETIQUETA_ENTRENAMIENTO, "indice"])
    prueba = set(particion.loc[particion["particion"] == ETIQUETA_PRUEBA, "indice"])

    if entrenamiento & prueba:
        problemas.append(
            f"{len(entrenamiento & prueba)} observaciones aparecen en entrenamiento y en prueba"
        )
    if entrenamiento | prueba != set(matriz.index):
        problemas.append(
            "La particion no cubre exactamente las filas de la matriz de predictores"
        )

    total = len(entrenamiento) + len(prueba)
    if total:
        proporcion = len(prueba) / total
        if abs(proporcion - FRACCION_PRUEBA) > 0.005:
            problemas.append(
                f"El conjunto de prueba es el {100 * proporcion:.2f} % y deberia ser el "
                f"{100 * FRACCION_PRUEBA:.0f} %"
            )

    # Estratificacion: la tasa de positivos debe ser casi la misma en ambos.
    respuesta = matriz[COLUMNA_RESPUESTA]
    if entrenamiento and prueba:
        tasa_entrenamiento = float(respuesta.loc[sorted(entrenamiento)].mean())
        tasa_prueba = float(respuesta.loc[sorted(prueba)].mean())
        if abs(tasa_entrenamiento - tasa_prueba) > 0.002:
            problemas.append(
                f"La particion no quedo estratificada: {100 * tasa_entrenamiento:.4f} % de "
                f"positivos en entrenamiento contra {100 * tasa_prueba:.4f} % en prueba"
            )

    # `lago` y `fecha` son metadatos que la particion arrastra para que la
    # validacion espacial y la temporal puedan agrupar sin releer el dataset.
    # Se comprueban contra la fuente antes de usarlos como referencia.
    metadatos = metadatos_observaciones(matriz) if metadatos is None else metadatos
    declarados = particion.set_index("indice")[["lago", "fecha"]]
    comunes = declarados.index.intersection(metadatos.index)
    if not declarados.loc[comunes].equals(metadatos.loc[comunes]):
        problemas.append(
            "El lago o la fecha declarados en la particion no coinciden con el dataset base"
        )

    # Reproducibilidad: rehacer la division con la misma semilla debe dar lo
    # mismo. Se pasan los metadatos ya validados para que la comparacion mida
    # solo la asignacion a entrenamiento o prueba.
    esperada = construir_particion(matriz, semilla=semilla, metadatos=metadatos)
    if not esperada.sort_values("indice").reset_index(drop=True).equals(
        particion.sort_values("indice").reset_index(drop=True)
    ):
        problemas.append(
            f"La particion persistida no se reproduce con la semilla {semilla}; "
            "fue generada con otra semilla o con otra matriz de predictores."
        )

    if problemas:
        raise ModelosError("La particion no cumple el contrato:\n  - " + "\n  - ".join(problemas))

    return {
        "entrenamiento": len(entrenamiento),
        "prueba": len(prueba),
        "positivos_prueba": int(respuesta.loc[sorted(prueba)].sum()),
    }


def verificar_modelos() -> dict[str, object]:
    """Contrato completo: particion reproducible y tres modelos cargables."""

    matriz = leer_features()
    resumen = verificar_particion(matriz)
    problemas: list[str] = []

    columnas = columnas_predictoras(matriz)
    for nombre in NOMBRES_MODELOS:
        try:
            paquete = cargar_modelo(nombre)
        except ModelosError as error:
            problemas.append(str(error))
            continue
        esperadas = columnas_para(nombre, columnas)
        if list(paquete["columnas"]) != esperadas:
            problemas.append(
                f"El modelo {nombre} espera columnas distintas de las de la matriz actual"
            )
            continue
        if not hasattr(paquete["modelo"], "predict_proba"):
            problemas.append(f"El modelo {nombre} no expone predict_proba")

    if not RUTA_HIPERPARAMETROS.is_file():
        problemas.append(f"No existe la tabla de hiperparametros {RUTA_HIPERPARAMETROS}")

    if problemas:
        raise ModelosError("Los modelos no cumplen el contrato:\n  - " + "\n  - ".join(problemas))

    resumen["modelos"] = list(NOMBRES_MODELOS)
    return resumen


# --------------------------------------------------------------------------
# Interfaz de linea de comandos
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("entrenar", "verificar"), nargs="?", default="verificar")
    parser.add_argument(
        "--iteraciones",
        type=int,
        default=8,
        help="Candidatos de hiperparametros evaluados por modelo",
    )
    parser.add_argument(
        "--pliegues",
        type=int,
        default=3,
        help="Pliegues de la validacion cruzada estratificada del ajuste",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.action == "entrenar":
        resumen = entrenar_todos(n_iteraciones=args.iteraciones, pliegues=args.pliegues)
        print(f"Particion: {resumen['particion']}")
        print(f"Hiperparametros: {resumen['hiperparametros']}")
        return 0

    resumen = verificar_modelos()
    print(
        f"Verificacion correcta: {resumen['entrenamiento']} observaciones de entrenamiento y "
        f"{resumen['prueba']} de prueba, {resumen['positivos_prueba']} positivas en prueba."
    )
    print(f"Modelos disponibles: {', '.join(resumen['modelos'])}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ModelosError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
