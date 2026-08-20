"""Ejercicio 2 de la Parte 2: variable respuesta binaria de cianobacteria.

Toma el conjunto de datos que construyó el ejercicio 1 (`src/dataset_ml.py`)
y agrega la columna `cyano_alta`. No recalcula ni reabre ningún raster.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Sequence

try:  # Permite `python src/respuesta.py` y `python -m src.respuesta`.
    from .config import (
        DIR_RESULTS_FIGURES,
        DIR_RESULTS_TABLES,
        LAGOS,
        UMBRAL_CIANOBACTERIA_ALTO_UGL,
        VARIABLES_EXCLUIDAS_RESPUESTA,
    )
    from .dataset_ml import DatasetMLError, leer_dataset, verificar_dataset
except ImportError:  # pragma: no cover - ruta usada al ejecutar el archivo
    from config import (  # type: ignore
        DIR_RESULTS_FIGURES,
        DIR_RESULTS_TABLES,
        LAGOS,
        UMBRAL_CIANOBACTERIA_ALTO_UGL,
        VARIABLES_EXCLUIDAS_RESPUESTA,
    )
    from dataset_ml import DatasetMLError, leer_dataset, verificar_dataset  # type: ignore


RUTA_DISTRIBUCION_RESPUESTA = DIR_RESULTS_TABLES / "distribucion_respuesta.csv"
DISTRIBUCION_FIELDS = ("corte", "lago", "fecha", "cyano_alta", "n", "pct")

COLUMNA_RESPUESTA = "cyano_alta"


class RespuestaError(RuntimeError):
    """Falla de contrato de la variable respuesta."""


# --------------------------------------------------------------------------
# Inciso 1: binarización
# --------------------------------------------------------------------------


def binarizar(tabla, *, umbral: float = UMBRAL_CIANOBACTERIA_ALTO_UGL):
    """Agrega `cyano_alta` a una copia de `tabla`.

    1 si `cianobacteria_ugl` es mayor o igual al umbral, 0 en otro caso. El
    umbral por defecto es el mismo que usan los ejercicios 8.1/8.2 de la
    Parte I (`UMBRAL_CIANOBACTERIA_ALTO_UGL`), para que ambas partes queden
    coherentes; se deja como parámetro para poder probarlo con otros cortes.
    """

    return tabla.assign(
        **{COLUMNA_RESPUESTA: (tabla["cianobacteria_ugl"] >= umbral).astype("int8")}
    )


# --------------------------------------------------------------------------
# Inciso 3: distribución de la respuesta
# --------------------------------------------------------------------------


def _conteo_pct(tabla, *, corte: str, lago: str = "", fecha: str = "") -> list[dict[str, object]]:
    total = len(tabla)
    filas = []
    for clase in (0, 1):
        n = int((tabla[COLUMNA_RESPUESTA] == clase).sum())
        filas.append(
            {
                "corte": corte,
                "lago": lago,
                "fecha": fecha,
                "cyano_alta": clase,
                "n": n,
                "pct": round(100.0 * n / total, 4) if total else 0.0,
            }
        )
    return filas


def distribucion_respuesta(tabla) -> list[dict[str, object]]:
    """Distribución de `cyano_alta` global, por lago y por fecha."""

    filas = list(_conteo_pct(tabla, corte="global"))
    for lago, grupo in tabla.groupby("lago", sort=True):
        filas += _conteo_pct(grupo, corte="por_lago", lago=lago)
    for (lago, fecha), grupo in tabla.groupby(["lago", "fecha"], sort=True):
        filas += _conteo_pct(grupo, corte="por_fecha", lago=lago, fecha=fecha)
    return filas


def escribir_distribucion(filas: Sequence[dict[str, object]], path: Path | None = None) -> Path:
    path = RUTA_DISTRIBUCION_RESPUESTA if path is None else path
    path.parent.mkdir(parents=True, exist_ok=True)
    temporal = path.with_suffix(path.suffix + ".tmp")
    with temporal.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=DISTRIBUCION_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(filas)
    temporal.replace(path)
    return path


def leer_distribucion(path: Path | None = None) -> list[dict[str, str]]:
    path = RUTA_DISTRIBUCION_RESPUESTA if path is None else path
    if not path.is_file():
        raise RespuestaError(f"No existe {path}")
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def figura_barras_apiladas_por_fecha(tabla, lago: str, *, out_path: Path | None = None) -> Path:
    """Barras apiladas de cyano_alta (0 vs 1) por fecha, para un lago."""

    import matplotlib.pyplot as plt

    subconjunto = tabla[tabla["lago"] == lago]
    fechas = sorted(subconjunto["fecha"].unique())
    negativos = [int((subconjunto[subconjunto["fecha"] == f][COLUMNA_RESPUESTA] == 0).sum()) for f in fechas]
    positivos = [int((subconjunto[subconjunto["fecha"] == f][COLUMNA_RESPUESTA] == 1).sum()) for f in fechas]

    fig, ax = plt.subplots(figsize=(10, 4.5))
    ax.bar(fechas, negativos, label="cyano_alta = 0", color="#8fb8ae")
    ax.bar(fechas, positivos, bottom=negativos, label="cyano_alta = 1", color="#c0392b")
    ax.set_ylabel("numero de observaciones")
    ax.set_title(f"{LAGOS[lago].nombre}: cyano_alta por fecha")
    ax.tick_params(axis="x", rotation=55)
    ax.legend()
    ax.grid(alpha=0.2, axis="y")
    fig.tight_layout()
    out_path = (DIR_RESULTS_FIGURES / f"eda_cyano_alta_por_fecha_{lago}.png") if out_path is None else out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path


# --------------------------------------------------------------------------
# Inciso 4: desbalance de clases
# --------------------------------------------------------------------------


def resumen_desbalance(tabla) -> dict[str, object]:
    """Ratio y porcentaje de la clase minoritaria, global y por lago.

    La clase minoritaria es siempre 1 (alta presencia) en este problema: es
    la que se espera raro por diseño del umbral de salud pública, no algo
    que haya que verificar caso por caso.
    """

    resultado: dict[str, object] = {}
    total = len(tabla)
    positivos = int(tabla[COLUMNA_RESPUESTA].sum())
    resultado["global"] = {
        "n_total": total,
        "n_positivos": positivos,
        "n_negativos": total - positivos,
        "pct_positivos": round(100.0 * positivos / total, 4) if total else 0.0,
        "ratio_negativos_por_positivo": round((total - positivos) / positivos, 2)
        if positivos
        else float("inf"),
    }
    for lago, grupo in tabla.groupby("lago", sort=True):
        n = len(grupo)
        pos = int(grupo[COLUMNA_RESPUESTA].sum())
        resultado[lago] = {
            "n_total": n,
            "n_positivos": pos,
            "n_negativos": n - pos,
            "pct_positivos": round(100.0 * pos / n, 4) if n else 0.0,
            "ratio_negativos_por_positivo": round((n - pos) / pos, 2) if pos else float("inf"),
        }
    return resultado


# --------------------------------------------------------------------------
# Construcción y verificación
# --------------------------------------------------------------------------


def construir_respuesta(*, umbral: float = UMBRAL_CIANOBACTERIA_ALTO_UGL):
    tabla = leer_dataset()
    return binarizar(tabla, umbral=umbral)


def verificar_respuesta(
    tabla=None, *, filas_distribucion: Sequence[dict[str, str]] | None = None
) -> dict[str, object]:
    """Contrato que debe cumplir la variable respuesta. Gate para el ejercicio 3."""

    tabla = construir_respuesta() if tabla is None else tabla
    filas_distribucion = leer_distribucion() if filas_distribucion is None else filas_distribucion
    problemas: list[str] = []

    if COLUMNA_RESPUESTA not in tabla.columns:
        problemas.append(f"Falta la columna {COLUMNA_RESPUESTA}")
    else:
        valores = set(tabla[COLUMNA_RESPUESTA].dropna().unique().tolist())
        if tabla[COLUMNA_RESPUESTA].isna().any():
            problemas.append(f"La columna {COLUMNA_RESPUESTA} tiene valores faltantes")
        if not valores <= {0, 1}:
            problemas.append(f"La columna {COLUMNA_RESPUESTA} tiene valores fuera de {{0,1}}: {valores}")

        esperado = (tabla["cianobacteria_ugl"] >= UMBRAL_CIANOBACTERIA_ALTO_UGL).astype("int8")
        if not (tabla[COLUMNA_RESPUESTA] == esperado).all():
            problemas.append(
                f"cyano_alta no coincide con (cianobacteria_ugl >= {UMBRAL_CIANOBACTERIA_ALTO_UGL})"
            )

    globales = [f for f in filas_distribucion if f["corte"] == "global"]
    if len(globales) != 2:
        problemas.append("distribucion_respuesta.csv no tiene las 2 filas del corte global")
    else:
        n_csv = sum(int(f["n"]) for f in globales)
        if n_csv != len(tabla):
            problemas.append(
                f"distribucion_respuesta.csv suma {n_csv} observaciones y el conjunto de datos tiene {len(tabla)}"
            )

    requeridas = {"cianobacteria_ugl", "B04", "ndvi"}
    faltantes = requeridas - set(VARIABLES_EXCLUIDAS_RESPUESTA)
    if faltantes:
        problemas.append(
            f"VARIABLES_EXCLUIDAS_RESPUESTA no declara: {sorted(faltantes)}"
        )

    if problemas:
        raise RespuestaError(
            "La variable respuesta no cumple el contrato:\n  - " + "\n  - ".join(problemas)
        )
    return {
        "observaciones": int(len(tabla)),
        "positivos": int(tabla[COLUMNA_RESPUESTA].sum()) if COLUMNA_RESPUESTA in tabla.columns else 0,
    }


# --------------------------------------------------------------------------
# Interfaz de línea de comandos
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("construir", "verificar"), nargs="?", default="verificar")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.action == "construir":
        verificar_dataset()  # gate: no construir sobre un dataset roto
        tabla = construir_respuesta()
        filas = distribucion_respuesta(tabla)
        ruta = escribir_distribucion(filas)
        resumen = resumen_desbalance(tabla)
        print(
            f"cyano_alta: {resumen['global']['n_positivos']} positivos de "
            f"{resumen['global']['n_total']} ({resumen['global']['pct_positivos']}%)"
        )
        print(f"Distribución escrita en {ruta}")
        return 0

    resumen = verificar_respuesta()
    print(
        f"Verificación correcta: {resumen['observaciones']} observaciones, "
        f"{resumen['positivos']} con cyano_alta=1."
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RespuestaError, DatasetMLError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
