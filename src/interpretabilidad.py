"""Interpretacion global y SHAP del mejor modelo de cianobacteria.

El modulo trabaja sobre el modelo ya seleccionado en ``evaluacion.py`` y usa
una muestra deterministica para que el analisis SHAP sea reproducible.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Sequence

import numpy as np

try:
    from .config import DIR_RESULTS_FIGURES, DIR_RESULTS_TABLES
    from .correlaciones import deterministic_sample
    from .evaluacion import leer_metricas, mejor_modelo
    from .features import leer_features
    from .modelos import cargar_modelo
except ImportError:  # pragma: no cover - permite ``python src/interpretabilidad.py``
    from config import DIR_RESULTS_FIGURES, DIR_RESULTS_TABLES  # type: ignore
    from correlaciones import deterministic_sample  # type: ignore
    from evaluacion import leer_metricas, mejor_modelo  # type: ignore
    from features import leer_features  # type: ignore
    from modelos import cargar_modelo  # type: ignore


RUTA_IMPORTANCIA = DIR_RESULTS_TABLES / "importancia_variables.csv"
RUTA_FIGURA_IMPORTANCIA = DIR_RESULTS_FIGURES / "importancia_variables.png"
RUTA_FIGURA_SHAP = DIR_RESULTS_FIGURES / "shap_summary.png"
TAMANO_MUESTRA_SHAP = 5000

IMPORTANCIA_FIELDS = (
    "modelo",
    "variable",
    "importancia_modelo",
    "importancia_modelo_normalizada",
    "shap_media_absoluta",
    "shap_media_absoluta_normalizada",
    "correlacion_valor_shap",
    "direccion_efecto",
    "n_muestra_shap",
)


class InterpretabilidadError(RuntimeError):
    pass


def seleccionar_mejor_modelo() -> str:
    filas = [
        {**fila, "f2": float(fila["f2"])}
        for fila in leer_metricas()
    ]
    return mejor_modelo(filas)


def muestra_deterministica(tabla, *, max_items: int = TAMANO_MUESTRA_SHAP):
    """Selecciona filas equiespaciadas usando el contrato ya existente."""

    indices, = deterministic_sample(np.arange(len(tabla)), max_items=max_items)
    return tabla.iloc[indices].copy()


def _estimador_y_valores(paquete: dict, muestra):
    modelo = paquete["modelo"]
    columnas = list(paquete["columnas"])
    X = muestra[columnas]

    # El unico Pipeline actual es la regresion logistica. Mantener este caso
    # hace que el modulo siga siendo valido si la metrica principal cambia.
    if hasattr(modelo, "named_steps"):
        pasos = list(modelo.named_steps.items())
        if len(pasos) < 2:
            raise InterpretabilidadError("El Pipeline no tiene un estimador final")
        transformado = X
        for _nombre, paso in pasos[:-1]:
            transformado = paso.transform(transformado)
        return pasos[-1][1], np.asarray(transformado), columnas
    return modelo, X, columnas


def importancias_nativas(estimador, columnas: Sequence[str]) -> np.ndarray:
    if hasattr(estimador, "feature_importances_"):
        valores = np.asarray(estimador.feature_importances_, dtype=float)
    elif hasattr(estimador, "coef_"):
        valores = np.abs(np.asarray(estimador.coef_, dtype=float)).mean(axis=0)
    else:
        raise InterpretabilidadError(
            f"El estimador {type(estimador).__name__} no expone importancia global"
        )
    if valores.shape != (len(columnas),):
        raise InterpretabilidadError("La importancia nativa no coincide con las columnas del modelo")
    return valores


def _direccion_efecto(valores: np.ndarray, shap_values: np.ndarray) -> tuple[float, str]:
    from scipy.stats import spearmanr

    if np.all(valores == valores[0]) or np.all(shap_values == shap_values[0]):
        return 0.0, "sin variacion suficiente"
    correlacion = float(spearmanr(valores, shap_values).statistic)
    if not np.isfinite(correlacion) or abs(correlacion) < 0.10:
        return 0.0 if not np.isfinite(correlacion) else correlacion, "efecto no monotono o debil"
    if correlacion > 0:
        return correlacion, "valores altos aumentan la prediccion"
    return correlacion, "valores altos disminuyen la prediccion"


def calcular_importancias(matriz=None, *, max_items: int = TAMANO_MUESTRA_SHAP):
    """Devuelve tabla de importancias, muestra y matriz SHAP del mejor modelo."""

    import shap

    matriz = leer_features() if matriz is None else matriz
    nombre = seleccionar_mejor_modelo()
    paquete = cargar_modelo(nombre)
    muestra = muestra_deterministica(matriz, max_items=max_items)
    estimador, X_explicacion, columnas = _estimador_y_valores(paquete, muestra)

    # TreeExplainer sin conjunto de fondo conserva la ruta de los arboles y
    # admite las particiones categoricas producidas por XGBoost.
    if hasattr(estimador, "get_booster"):
        explicador = shap.TreeExplainer(
            estimador,
            feature_perturbation="tree_path_dependent",
        )
    else:
        explicador = shap.Explainer(estimador, X_explicacion)
    explicacion = explicador(X_explicacion, check_additivity=False)
    valores_shap = np.asarray(explicacion.values, dtype=float)
    if valores_shap.ndim == 3:
        valores_shap = valores_shap[:, :, -1]
    if valores_shap.shape != (len(muestra), len(columnas)):
        raise InterpretabilidadError(
            f"SHAP devolvio {valores_shap.shape}; se esperaba {(len(muestra), len(columnas))}"
        )

    nativas = importancias_nativas(estimador, columnas)
    shap_abs = np.mean(np.abs(valores_shap), axis=0)
    suma_nativa = float(nativas.sum()) or 1.0
    suma_shap = float(shap_abs.sum()) or 1.0

    if hasattr(X_explicacion, "to_numpy"):
        X_numpy = X_explicacion.to_numpy(dtype=float)
    else:
        X_numpy = np.asarray(X_explicacion, dtype=float)

    filas = []
    for i, variable in enumerate(columnas):
        correlacion, direccion = _direccion_efecto(X_numpy[:, i], valores_shap[:, i])
        filas.append(
            {
                "modelo": nombre,
                "variable": variable,
                "importancia_modelo": round(float(nativas[i]), 8),
                "importancia_modelo_normalizada": round(float(nativas[i] / suma_nativa), 8),
                "shap_media_absoluta": round(float(shap_abs[i]), 8),
                "shap_media_absoluta_normalizada": round(float(shap_abs[i] / suma_shap), 8),
                "correlacion_valor_shap": round(correlacion, 6),
                "direccion_efecto": direccion,
                "n_muestra_shap": int(len(muestra)),
            }
        )
    filas.sort(key=lambda fila: float(fila["shap_media_absoluta"]), reverse=True)
    return filas, muestra[columnas], valores_shap


def escribir_importancias(filas, path: Path | None = None) -> Path:
    path = RUTA_IMPORTANCIA if path is None else path
    path.parent.mkdir(parents=True, exist_ok=True)
    temporal = path.with_suffix(path.suffix + ".tmp")
    with temporal.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=IMPORTANCIA_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(filas)
    temporal.replace(path)
    return path


def figura_importancia(filas, path: Path | None = None) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    path = RUTA_FIGURA_IMPORTANCIA if path is None else path
    orden = sorted(filas, key=lambda fila: float(fila["importancia_modelo_normalizada"]))
    variables = [str(f["variable"]) for f in orden]
    valores = [float(f["importancia_modelo_normalizada"]) for f in orden]
    fig, ax = plt.subplots(figsize=(8, 6.5))
    ax.barh(variables, valores, color="#2878B5")
    ax.set_xlabel("Importancia normalizada del modelo")
    ax.set_title(f"Importancia global - {filas[0]['modelo'].replace('_', ' ').title()}")
    ax.grid(axis="x", alpha=0.25)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=170, bbox_inches="tight")
    plt.close(fig)
    return path


def figura_shap(muestra, valores_shap, path: Path | None = None) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import shap

    path = RUTA_FIGURA_SHAP if path is None else path
    shap.summary_plot(
        valores_shap,
        muestra,
        feature_names=list(muestra.columns),
        max_display=min(15, muestra.shape[1]),
        show=False,
        plot_size=(9, 7),
        rng=np.random.default_rng(42),
    )
    fig = plt.gcf()
    fig.suptitle("Resumen SHAP del mejor modelo", y=1.01, fontsize=14)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=170, bbox_inches="tight")
    plt.close(fig)
    return path


def analizar() -> dict[str, object]:
    filas, muestra, valores_shap = calcular_importancias()
    return {
        "modelo": filas[0]["modelo"],
        "n_muestra": len(muestra),
        "tabla": escribir_importancias(filas),
        "figura_importancia": figura_importancia(filas),
        "figura_shap": figura_shap(muestra, valores_shap),
        "variables_principales": [fila["variable"] for fila in filas[:5]],
    }


def verificar() -> dict[str, object]:
    problemas = []
    if not RUTA_IMPORTANCIA.is_file():
        problemas.append(f"Falta {RUTA_IMPORTANCIA}")
        filas = []
    else:
        with RUTA_IMPORTANCIA.open(newline="", encoding="utf-8") as stream:
            filas = list(csv.DictReader(stream))
        if not filas:
            problemas.append("La tabla de importancia esta vacia")
        elif set(filas[0]) != set(IMPORTANCIA_FIELDS):
            problemas.append("La tabla de importancia no tiene el contrato esperado")
        else:
            esperadas = set(cargar_modelo(seleccionar_mejor_modelo())["columnas"])
            encontradas = {fila["variable"] for fila in filas}
            if esperadas != encontradas:
                problemas.append("La tabla no cubre exactamente las variables del mejor modelo")
            if any(int(fila["n_muestra_shap"]) <= 0 for fila in filas):
                problemas.append("El tamano de muestra SHAP no es valido")

    for ruta in (RUTA_FIGURA_IMPORTANCIA, RUTA_FIGURA_SHAP):
        if not ruta.is_file() or ruta.stat().st_size == 0:
            problemas.append(f"Falta la figura {ruta}")
    if problemas:
        raise InterpretabilidadError("La interpretabilidad no cumple el contrato:\n  - " + "\n  - ".join(problemas))
    return {"modelo": filas[0]["modelo"], "variables": len(filas), "n_muestra": int(filas[0]["n_muestra_shap"])}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("analizar", "verificar"), nargs="?", default="verificar")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.action == "analizar":
        resumen = analizar()
        print(f"Modelo interpretado: {resumen['modelo']} con {resumen['n_muestra']} observaciones SHAP")
        print(f"Variables principales: {', '.join(resumen['variables_principales'])}")
        print(f"Tabla: {resumen['tabla']}")
        return 0
    resumen = verificar()
    print(f"Verificacion correcta: {resumen['variables']} variables, muestra SHAP de {resumen['n_muestra']}.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except InterpretabilidadError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
