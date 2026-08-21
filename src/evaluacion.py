"""Evaluacion comparativa de los tres modelos de clasificacion.

Calcula Accuracy, Precision, Recall, F1, F2, ROC-AUC, PR-AUC y la matriz de
confusion de cada modelo sobre el mismo conjunto de prueba persistido por
`src/modelos.py`, y determina cual tiene mejor desempeno.

La metrica principal de comparacion es F2 y no Accuracy ni F1. La razon es
ambiental y no estadistica: un falso negativo deja sin alerta una zona con
floracion potencialmente toxica, mientras que un falso positivo solo cuesta una
inspeccion de campo innecesaria. Con beta = 2 el Recall pesa cuatro veces mas
que la Precision, que es la asimetria que corresponde a ese costo. Ademas, con
1.29 por ciento de positivos, Accuracy es enganosa: predecir siempre ausencia ya
da 98.7 por ciento.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Sequence

import numpy as np

try:  # Permite `python src/evaluacion.py` y `python -m src.evaluacion`.
    from .config import DIR_RESULTS_FIGURES, DIR_RESULTS_TABLES
    from .features import leer_features
    from .modelos import (
        BETA_F,
        COLUMNAS_IDENTIDAD_LAGO,
        NOMBRES_MODELOS,
        SUFIJO_VARIANTE_SIN_LAGO,
        ModelosError,
        cargar_modelo,
        dividir,
        entrenar_variante,
    )
except ImportError:  # pragma: no cover - ruta usada al ejecutar el archivo
    from config import DIR_RESULTS_FIGURES, DIR_RESULTS_TABLES  # type: ignore
    from features import leer_features  # type: ignore
    from modelos import (  # type: ignore
        BETA_F,
        COLUMNAS_IDENTIDAD_LAGO,
        NOMBRES_MODELOS,
        SUFIJO_VARIANTE_SIN_LAGO,
        ModelosError,
        cargar_modelo,
        dividir,
        entrenar_variante,
    )


RUTA_METRICAS_MODELOS = DIR_RESULTS_TABLES / "metricas_modelos.csv"
RUTA_FIGURA_ROC = DIR_RESULTS_FIGURES / "curvas_roc.png"
RUTA_FIGURA_PR = DIR_RESULTS_FIGURES / "curvas_precision_recall.png"
RUTA_FIGURA_CONFUSION = DIR_RESULTS_FIGURES / "matrices_confusion.png"
RUTA_DIAGNOSTICO_LAGO = DIR_RESULTS_TABLES / "diagnostico_identidad_lago.csv"

METRICAS_FIELDS = (
    "modelo",
    "n_prueba",
    "positivos_prueba",
    "accuracy",
    "precision",
    "recall",
    "f1",
    "f2",
    "roc_auc",
    "pr_auc",
    "verdaderos_negativos",
    "falsos_positivos",
    "falsos_negativos",
    "verdaderos_positivos",
)

# Criterio de comparacion entre modelos, justificado en el docstring del modulo.
METRICA_PRINCIPAL = "f2"

ETIQUETAS_MODELOS = {
    "regresion_logistica": "Regresion Logistica",
    "random_forest": "Random Forest",
    "gradient_boosting": "Gradient Boosting",
}


class EvaluacionError(RuntimeError):
    """Falla de contrato en la evaluacion de los modelos."""


# --------------------------------------------------------------------------
# Prediccion y metricas
# --------------------------------------------------------------------------


def predecir(nombre: str, X) -> tuple[np.ndarray, np.ndarray]:
    """Devuelve la clase predicha y la probabilidad de alta presencia."""

    paquete = cargar_modelo(nombre)
    columnas = list(paquete["columnas"])
    faltantes = [c for c in columnas if c not in X.columns]
    if faltantes:
        raise EvaluacionError(
            f"A la matriz le faltan columnas que el modelo {nombre} espera: {faltantes}"
        )
    entrada = X[columnas]
    modelo = paquete["modelo"]
    return modelo.predict(entrada), modelo.predict_proba(entrada)[:, 1]


def metricas_modelo(nombre: str, y_verdadero, y_predicho, y_probabilidad) -> dict[str, object]:
    """Todas las metricas que pide el inciso 1, mas F2 y PR-AUC.

    PR-AUC se agrega porque bajo un desbalance de 1.29 por ciento resume mejor
    el desempeno sobre la clase positiva que ROC-AUC, que se ve favorecido por
    la enorme cantidad de negativos faciles.
    """

    from sklearn.metrics import (
        accuracy_score,
        average_precision_score,
        confusion_matrix,
        fbeta_score,
        precision_score,
        recall_score,
        roc_auc_score,
    )

    y_verdadero = np.asarray(y_verdadero)
    y_predicho = np.asarray(y_predicho)
    vn, fp, fn, vp = confusion_matrix(y_verdadero, y_predicho, labels=[0, 1]).ravel()

    return {
        "modelo": nombre,
        "n_prueba": int(len(y_verdadero)),
        "positivos_prueba": int(y_verdadero.sum()),
        "accuracy": round(float(accuracy_score(y_verdadero, y_predicho)), 6),
        "precision": round(float(precision_score(y_verdadero, y_predicho, zero_division=0)), 6),
        "recall": round(float(recall_score(y_verdadero, y_predicho, zero_division=0)), 6),
        "f1": round(float(fbeta_score(y_verdadero, y_predicho, beta=1.0, zero_division=0)), 6),
        "f2": round(float(fbeta_score(y_verdadero, y_predicho, beta=BETA_F, zero_division=0)), 6),
        "roc_auc": round(float(roc_auc_score(y_verdadero, y_probabilidad)), 6),
        "pr_auc": round(float(average_precision_score(y_verdadero, y_probabilidad)), 6),
        "verdaderos_negativos": int(vn),
        "falsos_positivos": int(fp),
        "falsos_negativos": int(fn),
        "verdaderos_positivos": int(vp),
    }


def evaluar_todos(matriz=None) -> tuple[list[dict[str, object]], dict[str, np.ndarray]]:
    """Evalua los tres modelos sobre el conjunto de prueba compartido."""

    matriz = leer_features() if matriz is None else matriz
    datos = dividir(matriz)
    X = datos["X_prueba"]
    y = datos["y_prueba"]

    filas: list[dict[str, object]] = []
    probabilidades: dict[str, np.ndarray] = {}
    for nombre in NOMBRES_MODELOS:
        predicho, probabilidad = predecir(nombre, X)
        probabilidades[nombre] = probabilidad
        filas.append(metricas_modelo(nombre, y, predicho, probabilidad))
    return filas, {"y_prueba": np.asarray(y), **probabilidades}


def mejor_modelo(filas: Sequence[dict[str, object]], *, criterio: str = METRICA_PRINCIPAL) -> str:
    """Modelo con mejor desempeno segun el criterio elegido."""

    if not filas:
        raise EvaluacionError("No hay filas de metricas para comparar")
    if criterio not in METRICAS_FIELDS:
        raise EvaluacionError(f"Criterio desconocido: {criterio}")
    return max(filas, key=lambda fila: fila[criterio])["modelo"]


def comparar_criterios(filas: Sequence[dict[str, object]]) -> dict[str, str]:
    """Que modelo gana segun cada metrica.

    Sirve para mostrar de forma explicita que la eleccion del ganador depende de
    la metrica, que es justo lo que discute el inciso 3.
    """

    return {
        criterio: mejor_modelo(filas, criterio=criterio)
        for criterio in ("accuracy", "precision", "recall", "f1", "f2", "roc_auc", "pr_auc")
    }


def costo_errores(filas: Sequence[dict[str, object]]) -> list[dict[str, object]]:
    """Resume los dos tipos de error en terminos de su lectura ambiental."""

    resumen = []
    for fila in filas:
        fn = int(fila["falsos_negativos"])
        fp = int(fila["falsos_positivos"])
        positivos = int(fila["positivos_prueba"])
        resumen.append(
            {
                "modelo": fila["modelo"],
                "falsos_negativos": fn,
                "pct_positivos_no_detectados": round(100.0 * fn / max(positivos, 1), 4),
                "falsos_positivos": fp,
                "inspecciones_innecesarias_por_zona_detectada": round(
                    fp / max(int(fila["verdaderos_positivos"]), 1), 4
                ),
            }
        )
    return resumen


def diagnostico_identidad_lago(matriz=None) -> list[dict[str, object]]:
    """Cuanto del desempeno viene de la firma espectral y cuanto de saber el lago.

    Reentrena cada modelo sin las cuatro columnas de `COLUMNAS_IDENTIDAD_LAGO`,
    conservando sus hiperparametros, y compara las metricas contra el modelo
    completo sobre el mismo conjunto de prueba. Una caida grande significa que el
    modelo se apoyaba en saber en que lago esta la celda, que bajo este
    desbalance es casi una respuesta directa, en lugar de aprender de las bandas.

    Hay que quitar las cuatro a la vez. Retirar solo los one-hot no mide nada,
    porque el modelo se pasa a `x_utm`, que separa los dos lagos igual de bien.
    """

    matriz = leer_features() if matriz is None else matriz
    datos = dividir(matriz)
    X = datos["X_prueba"]
    y = datos["y_prueba"]

    filas: list[dict[str, object]] = []
    for nombre in NOMBRES_MODELOS:
        completo = metricas_modelo(nombre, y, *predecir(nombre, X))

        entrenar_variante(nombre, matriz=matriz)
        variante = f"{nombre}__{SUFIJO_VARIANTE_SIN_LAGO}"
        reducido = metricas_modelo(variante, y, *predecir(variante, X))

        for criterio in ("recall", "precision", "f2", "roc_auc", "pr_auc"):
            filas.append(
                {
                    "modelo": nombre,
                    "metrica": criterio,
                    "con_ubicacion": completo[criterio],
                    "sin_ubicacion": reducido[criterio],
                    "diferencia": round(
                        float(completo[criterio]) - float(reducido[criterio]), 6
                    ),
                }
            )
    return filas


DIAGNOSTICO_FIELDS = (
    "modelo",
    "metrica",
    "con_ubicacion",
    "sin_ubicacion",
    "diferencia",
)


def escribir_diagnostico_lago(filas: Sequence[dict[str, object]], path: Path | None = None) -> Path:
    path = RUTA_DIAGNOSTICO_LAGO if path is None else path
    path.parent.mkdir(parents=True, exist_ok=True)
    temporal = path.with_suffix(path.suffix + ".tmp")
    with temporal.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=DIAGNOSTICO_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(filas)
    temporal.replace(path)
    return path


# --------------------------------------------------------------------------
# Escritura y figuras
# --------------------------------------------------------------------------


def escribir_metricas(filas: Sequence[dict[str, object]], path: Path | None = None) -> Path:
    path = RUTA_METRICAS_MODELOS if path is None else path
    path.parent.mkdir(parents=True, exist_ok=True)
    temporal = path.with_suffix(path.suffix + ".tmp")
    with temporal.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=METRICAS_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(filas)
    temporal.replace(path)
    return path


def leer_metricas(path: Path | None = None) -> list[dict[str, str]]:
    path = RUTA_METRICAS_MODELOS if path is None else path
    if not path.is_file():
        raise EvaluacionError(
            f"No existe {path}. Ejecute primero `python src/evaluacion.py evaluar`."
        )
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def _matplotlib():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    return plt


def figura_curvas_roc(salidas: dict[str, np.ndarray], path: Path | None = None) -> Path:
    from sklearn.metrics import roc_auc_score, roc_curve

    plt = _matplotlib()
    path = RUTA_FIGURA_ROC if path is None else path
    y = salidas["y_prueba"]

    figura, eje = plt.subplots(figsize=(6.5, 6))
    for nombre in NOMBRES_MODELOS:
        fpr, tpr, _ = roc_curve(y, salidas[nombre])
        eje.plot(fpr, tpr, label=f"{ETIQUETAS_MODELOS[nombre]} (AUC {roc_auc_score(y, salidas[nombre]):.3f})")
    eje.plot([0, 1], [0, 1], "--", color="gray", linewidth=1, label="Azar")
    eje.set_xlabel("Tasa de falsos positivos")
    eje.set_ylabel("Tasa de verdaderos positivos")
    eje.set_title("Curvas ROC sobre el conjunto de prueba")
    eje.legend(loc="lower right")
    eje.grid(alpha=0.3)
    path.parent.mkdir(parents=True, exist_ok=True)
    figura.tight_layout()
    figura.savefig(path, dpi=150)
    plt.close(figura)
    return path


def figura_curvas_precision_recall(salidas: dict[str, np.ndarray], path: Path | None = None) -> Path:
    from sklearn.metrics import average_precision_score, precision_recall_curve

    plt = _matplotlib()
    path = RUTA_FIGURA_PR if path is None else path
    y = salidas["y_prueba"]
    base = float(np.mean(y))

    figura, eje = plt.subplots(figsize=(6.5, 6))
    for nombre in NOMBRES_MODELOS:
        precision, recall, _ = precision_recall_curve(y, salidas[nombre])
        eje.plot(
            recall,
            precision,
            label=f"{ETIQUETAS_MODELOS[nombre]} (AP {average_precision_score(y, salidas[nombre]):.3f})",
        )
    eje.axhline(base, linestyle="--", color="gray", linewidth=1, label=f"Prevalencia {base:.4f}")
    eje.set_xlabel("Recall")
    eje.set_ylabel("Precision")
    eje.set_title("Curvas Precision-Recall sobre el conjunto de prueba")
    eje.legend(loc="best")
    eje.grid(alpha=0.3)
    path.parent.mkdir(parents=True, exist_ok=True)
    figura.tight_layout()
    figura.savefig(path, dpi=150)
    plt.close(figura)
    return path


def figura_matrices_confusion(filas: Sequence[dict[str, object]], path: Path | None = None) -> Path:
    plt = _matplotlib()
    path = RUTA_FIGURA_CONFUSION if path is None else path

    figura, ejes = plt.subplots(1, len(filas), figsize=(4.6 * len(filas), 4.2))
    if len(filas) == 1:
        ejes = [ejes]
    for eje, fila in zip(ejes, filas):
        matriz = np.array(
            [
                [int(fila["verdaderos_negativos"]), int(fila["falsos_positivos"])],
                [int(fila["falsos_negativos"]), int(fila["verdaderos_positivos"])],
            ]
        )
        # Normaliza por fila para que la clase positiva, que es el 1.29 por
        # ciento, se lea igual de bien que la negativa.
        normalizada = matriz / matriz.sum(axis=1, keepdims=True)
        eje.imshow(normalizada, cmap="Blues", vmin=0, vmax=1)
        for i in range(2):
            for j in range(2):
                eje.text(
                    j,
                    i,
                    f"{matriz[i, j]:,}\n{100 * normalizada[i, j]:.1f} %",
                    ha="center",
                    va="center",
                    color="white" if normalizada[i, j] > 0.5 else "black",
                    fontsize=10,
                )
        eje.set_xticks([0, 1], ["Predicho 0", "Predicho 1"])
        eje.set_yticks([0, 1], ["Real 0", "Real 1"])
        eje.set_title(f"{ETIQUETAS_MODELOS[str(fila['modelo'])]}\nF2 {float(fila['f2']):.3f}")
    figura.suptitle("Matrices de confusion, normalizadas por clase real")
    path.parent.mkdir(parents=True, exist_ok=True)
    figura.tight_layout()
    figura.savefig(path, dpi=150)
    plt.close(figura)
    return path


# --------------------------------------------------------------------------
# Orquestacion y verificacion
# --------------------------------------------------------------------------


def evaluar_y_exportar() -> dict[str, object]:
    filas, salidas = evaluar_todos()
    escribir_metricas(filas)
    figura_curvas_roc(salidas)
    figura_curvas_precision_recall(salidas)
    figura_matrices_confusion(filas)
    diagnostico = diagnostico_identidad_lago()
    escribir_diagnostico_lago(diagnostico)
    return {
        "filas": filas,
        "mejor": mejor_modelo(filas),
        "por_criterio": comparar_criterios(filas),
        "costos": costo_errores(filas),
        "diagnostico_lago": diagnostico,
    }


def verificar_evaluacion(filas: Sequence[dict[str, str]] | None = None) -> dict[str, object]:
    """Contrato de la evaluacion ya calculada."""

    filas = leer_metricas() if filas is None else filas
    problemas: list[str] = []

    nombres = {fila["modelo"] for fila in filas}
    if nombres != set(NOMBRES_MODELOS):
        problemas.append(
            f"La tabla de metricas cubre {sorted(nombres)} y deberia cubrir {sorted(NOMBRES_MODELOS)}"
        )

    for fila in filas:
        for campo in ("accuracy", "precision", "recall", "f1", "f2", "roc_auc", "pr_auc"):
            valor = float(fila[campo])
            if not 0.0 <= valor <= 1.0:
                problemas.append(f"{fila['modelo']} tiene {campo} fuera de 0 a 1: {valor}")
        celdas = sum(
            int(fila[c])
            for c in (
                "verdaderos_negativos",
                "falsos_positivos",
                "falsos_negativos",
                "verdaderos_positivos",
            )
        )
        if celdas != int(fila["n_prueba"]):
            problemas.append(
                f"La matriz de confusion de {fila['modelo']} suma {celdas} y el conjunto de "
                f"prueba tiene {fila['n_prueba']} observaciones"
            )
        reales = int(fila["falsos_negativos"]) + int(fila["verdaderos_positivos"])
        if reales != int(fila["positivos_prueba"]):
            problemas.append(
                f"Los positivos reales de {fila['modelo']} no cuadran con la matriz de confusion"
            )

    n_prueba = {fila["n_prueba"] for fila in filas}
    if len(n_prueba) > 1:
        problemas.append(
            "Los modelos no se evaluaron sobre el mismo conjunto de prueba: "
            f"tamanos {sorted(n_prueba)}"
        )

    for ruta in (RUTA_FIGURA_ROC, RUTA_FIGURA_PR, RUTA_FIGURA_CONFUSION):
        if not ruta.is_file():
            problemas.append(f"Falta la figura {ruta}")

    if not RUTA_DIAGNOSTICO_LAGO.is_file():
        problemas.append(f"Falta el diagnostico de identidad de lago {RUTA_DIAGNOSTICO_LAGO}")

    if problemas:
        raise EvaluacionError(
            "La evaluacion no cumple el contrato:\n  - " + "\n  - ".join(problemas)
        )

    return {"modelos": len(filas), "mejor": mejor_modelo(filas)}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("evaluar", "verificar"), nargs="?", default="verificar")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.action == "evaluar":
        resultado = evaluar_y_exportar()
        for fila in resultado["filas"]:
            print(
                f"- {fila['modelo']:22s} F2 {fila['f2']:.4f}  Recall {fila['recall']:.4f}  "
                f"Precision {fila['precision']:.4f}  ROC-AUC {fila['roc_auc']:.4f}  "
                f"PR-AUC {fila['pr_auc']:.4f}"
            )
        print(f"Mejor modelo segun {METRICA_PRINCIPAL.upper()}: {resultado['mejor']}")
        print(f"Metricas: {RUTA_METRICAS_MODELOS}")
        return 0

    resumen = verificar_evaluacion()
    print(
        f"Verificacion correcta: {resumen['modelos']} modelos evaluados, "
        f"mejor segun {METRICA_PRINCIPAL.upper()}: {resumen['mejor']}."
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (EvaluacionError, ModelosError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
