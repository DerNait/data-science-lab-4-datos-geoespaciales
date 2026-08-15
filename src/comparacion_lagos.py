from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Sequence

try:
    from .analisis_temporal import CALIDAD_COMPLETA, read_resumen_temporal
    from .config import (
        COMPARACION_LAGOS_FIELDS,
        LAGOS,
        MESES_ESTACION_LLUVIOSA,
        MESES_ESTACION_SECA,
        PATRON_ESTACIONAL_FIELDS,
        RESUMEN_PERSISTENCIA,
        RUTA_COMPARACION_LAGOS,
        RUTA_CORRELACIONES_LAGO,
        RUTA_EXTENSION_FLORACION,
        RUTA_PATRON_ESTACIONAL,
        UMBRAL_CIANOBACTERIA_ALTO_UGL,
    )
    from .indices import InputDataError
except ImportError:  # pragma: no cover - permite ejecutar el archivo directamente
    from analisis_temporal import CALIDAD_COMPLETA, read_resumen_temporal  # type: ignore
    from config import (  # type: ignore
        COMPARACION_LAGOS_FIELDS,
        LAGOS,
        MESES_ESTACION_LLUVIOSA,
        MESES_ESTACION_SECA,
        PATRON_ESTACIONAL_FIELDS,
        RESUMEN_PERSISTENCIA,
        RUTA_COMPARACION_LAGOS,
        RUTA_CORRELACIONES_LAGO,
        RUTA_EXTENSION_FLORACION,
        RUTA_PATRON_ESTACIONAL,
        UMBRAL_CIANOBACTERIA_ALTO_UGL,
    )
    from indices import InputDataError  # type: ignore


def _write_csv_atomic(path: Path, rows: Sequence[dict], fields: Sequence[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)
    return path


def _read_csv(path: Path) -> list[dict[str, str]]:
    with Path(path).open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


# --------------------------------------------------------------------------
# Ejercicio 7: tabla comparativa Atitlán vs. Amatitlán
# --------------------------------------------------------------------------


def _validate_lago(lago: str) -> None:
    if lago not in LAGOS:
        raise ValueError(f"Lago inválido: {lago}. Opciones: {', '.join(LAGOS)}")


# Se reportan dos promedios a propósito: uno con las 11 fechas (base
# comparable entre lagos) y otro solo con fechas "calculado" (n_fechas_
# calculado), porque un lago puede tener muchas más fechas con advertencia
# que el otro. Esa diferencia de confiabilidad es en sí misma un hallazgo
# que 7.3 debe discutir, no algo para esconder promediando solo lo "limpio".
def lake_summary_row(
    lago: str,
    *,
    temporal_rows: Sequence[dict],
    extension_rows: Sequence[dict],
    correlation_rows: Sequence[dict],
    umbral: float = UMBRAL_CIANOBACTERIA_ALTO_UGL,
) -> dict:
    _validate_lago(lago)
    temporal = sorted(
        (r for r in temporal_rows if r["lago"] == lago), key=lambda r: r["fecha"]
    )
    if not temporal:
        raise InputDataError(f"No hay filas de resumen_temporal.csv para {lago}")
    extension = {r["fecha"]: r for r in extension_rows if r["lago"] == lago}

    valores = [float(r["cyano_promedio"]) for r in temporal]
    calculado = [r for r in temporal if r["quality_flag"] == CALIDAD_COMPLETA]
    sobre_umbral = [r for r in temporal if float(r["cyano_promedio"]) >= umbral]

    porcentajes_altos = [
        float(extension[r["fecha"]]["porcentaje_alto"]) for r in temporal if r["fecha"] in extension
    ]
    fila_maxima = max(
        (r for r in temporal if r["fecha"] in extension),
        key=lambda r: float(extension[r["fecha"]]["porcentaje_alto"]),
    )

    correlaciones = {
        (r["indice"], r["metodo"]): r
        for r in correlation_rows
        if r["lago"] == lago
    }
    ndvi_pearson = correlaciones.get(("ndvi", "pearson"))
    ndwi_pearson = correlaciones.get(("ndwi", "pearson"))

    primera_mitad = valores[: len(valores) // 2] or valores[:1]
    segunda_mitad = valores[len(valores) // 2 :] or valores[-1:]
    delta = (sum(segunda_mitad) / len(segunda_mitad)) - (sum(primera_mitad) / len(primera_mitad))
    if abs(delta) < 0.5:
        tendencia = "estable"
    else:
        tendencia = "creciente" if delta > 0 else "decreciente"

    persistencia = RESUMEN_PERSISTENCIA[lago]

    return {
        "lago": lago,
        "n_fechas_calculado": len(calculado),
        "n_fechas_total": len(temporal),
        "cyano_promedio_general": round(sum(valores) / len(valores), 4),
        "cyano_mediana_general": round(sorted(valores)[len(valores) // 2], 4),
        "frecuencia_fechas_sobre_umbral": len(sobre_umbral),
        "pct_fechas_sobre_umbral": round(100 * len(sobre_umbral) / len(temporal), 2),
        "porcentaje_alto_promedio": round(
            sum(porcentajes_altos) / len(porcentajes_altos), 4
        ) if porcentajes_altos else "",
        "porcentaje_alto_maximo": extension[fila_maxima["fecha"]]["porcentaje_alto"],
        "fecha_porcentaje_alto_maximo": fila_maxima["fecha"],
        "pct_area_alguna_vez_alta": persistencia["pct_area_alguna_vez_alta"],
        "pct_area_persistente": persistencia["pct_area_persistente"],
        "correlacion_ndvi_pearson_mediana": ndvi_pearson["coeficiente_mediano_fechas"] if ndvi_pearson else "",
        "correlacion_ndwi_pearson_mediana": ndwi_pearson["coeficiente_mediano_fechas"] if ndwi_pearson else "",
        "tendencia_temporal": tendencia,
    }


def build_comparison_table(
    *,
    temporal_rows: Sequence[dict] | None = None,
    extension_rows: Sequence[dict] | None = None,
    correlation_rows: Sequence[dict] | None = None,
) -> list[dict]:
    temporal_rows = read_resumen_temporal() if temporal_rows is None else temporal_rows
    extension_rows = _read_csv(RUTA_EXTENSION_FLORACION) if extension_rows is None else extension_rows
    correlation_rows = (
        _read_csv(RUTA_CORRELACIONES_LAGO) if correlation_rows is None else correlation_rows
    )
    return [
        lake_summary_row(
            lago,
            temporal_rows=temporal_rows,
            extension_rows=extension_rows,
            correlation_rows=correlation_rows,
        )
        for lago in sorted(LAGOS)
    ]


def write_comparison_table(rows: Sequence[dict], path: Path | None = None) -> Path:
    path = RUTA_COMPARACION_LAGOS if path is None else path
    return _write_csv_atomic(path, rows, COMPARACION_LAGOS_FIELDS)


def read_comparison_table(path: Path | None = None) -> list[dict]:
    return _read_csv(RUTA_COMPARACION_LAGOS if path is None else path)


# --------------------------------------------------------------------------
# Ejercicio 8.4: patrón estacional (exploratorio, no un modelo de series)
# --------------------------------------------------------------------------


def assign_season(fecha: str) -> str:
    mes = date.fromisoformat(fecha).month
    if mes in MESES_ESTACION_SECA:
        return "seca"
    if mes in MESES_ESTACION_LLUVIOSA:
        return "lluviosa"
    raise AssertionError(f"Mes sin estación asignada: {mes}")  # pragma: no cover


def build_seasonal_summary(temporal_rows: Sequence[dict] | None = None) -> list[dict]:
    temporal_rows = read_resumen_temporal() if temporal_rows is None else temporal_rows
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in temporal_rows:
        grouped[(row["lago"], assign_season(row["fecha"]))].append(row)

    result: list[dict] = []
    for lago in sorted(LAGOS):
        for estacion in ("seca", "lluviosa"):
            filas = sorted(grouped.get((lago, estacion), []), key=lambda r: r["fecha"])
            if not filas:
                continue
            valores = [float(r["cyano_promedio"]) for r in filas]
            media = sum(valores) / len(valores)
            varianza = sum((v - media) ** 2 for v in valores) / len(valores)
            result.append(
                {
                    "lago": lago,
                    "estacion": estacion,
                    "n_fechas": len(filas),
                    "cyano_promedio": round(media, 4),
                    "cyano_mediana": round(sorted(valores)[len(valores) // 2], 4),
                    "cyano_std": round(varianza**0.5, 4),
                    "fechas": ";".join(r["fecha"] for r in filas),
                }
            )
    return result


def write_seasonal_summary(rows: Sequence[dict], path: Path | None = None) -> Path:
    path = RUTA_PATRON_ESTACIONAL if path is None else path
    return _write_csv_atomic(path, rows, PATRON_ESTACIONAL_FIELDS)


def read_seasonal_summary(path: Path | None = None) -> list[dict]:
    return _read_csv(RUTA_PATRON_ESTACIONAL if path is None else path)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("compare", "seasonal", "all"), nargs="?", default="all")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.action in ("compare", "all"):
        table = build_comparison_table()
        path = write_comparison_table(table)
        print(f"comparacion_lagos.csv escrito con {len(table)} filas en {path}")

    if args.action in ("seasonal", "all"):
        seasonal = build_seasonal_summary()
        path = write_seasonal_summary(seasonal)
        print(f"patron_estacional.csv escrito con {len(seasonal)} filas en {path}")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, InputDataError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
