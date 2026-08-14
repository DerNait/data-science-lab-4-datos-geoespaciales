from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Sequence

try:  # Permite `python src/analisis_temporal.py` y `python -m src.analisis_temporal`.
    from .config import (
        ESCENAS_OFICIALES,
        PICO_DESVIACIONES,
        RAIZ,
        RESUMEN_TEMPORAL_FIELDS,
        RUTA_RESUMEN_TEMPORAL,
    )
    from .indices import (
        InputDataError,
        summarize_array,
        validate_manifest_indices,
    )
except ImportError:  # pragma: no cover - ruta usada al ejecutar el archivo
    from config import (  # type: ignore
        ESCENAS_OFICIALES,
        PICO_DESVIACIONES,
        RAIZ,
        RESUMEN_TEMPORAL_FIELDS,
        RUTA_RESUMEN_TEMPORAL,
    )
    from indices import (  # type: ignore
        InputDataError,
        summarize_array,
        validate_manifest_indices,
    )

# quality_flag de manifest_indices.csv que indica que ese producto todavía
# no se calculó (ver src/indices.py). Nunca se inventa un valor para estas
# filas: se reportan como pendientes.
CALIDAD_PENDIENTE = "pendiente_calculo"
CALIDAD_COMPLETA = "calculado"
CALIDAD_PARCIAL = "cobertura_parcial_oficial"


# --------------------------------------------------------------------------
# Validación del manifiesto de índices antes de resumir
# --------------------------------------------------------------------------


def cianobacteria_rows(rows: Sequence[dict[str, str]] | None = None) -> list[dict[str, str]]:
    """Filtra `manifest_indices.csv` a solo las filas de cianobacteria."""

    rows = validate_manifest_indices() if rows is None else rows
    return [row for row in rows if row["indice"] == "cianobacteria"]


def split_ready_pending(
    rows: Sequence[dict[str, str]] | None = None,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Separa filas de cianobacteria ya calculadas de las todavía pendientes."""

    cyano = cianobacteria_rows(rows)
    ready = [
        row for row in cyano if row["quality_flag"] != CALIDAD_PENDIENTE and row["ruta_raster"]
    ]
    pending = [row for row in cyano if row not in ready]
    return ready, pending


def pending_report(rows: Sequence[dict[str, str]] | None = None) -> dict[str, object]:
    """Resumen legible de cuántas escenas de cianobacteria faltan por calcular."""

    ready, pending = split_ready_pending(rows)
    return {
        "total_escenas": len(ESCENAS_OFICIALES),
        "listas": len(ready),
        "pendientes": len(pending),
        "fechas_pendientes": sorted((row["lago"], row["fecha"]) for row in pending),
    }


def validate_indices_manifest_ready(
    rows: Sequence[dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    """Valida el manifiesto de índices antes de calcular el resumen temporal.

    Reutiliza `indices.validate_manifest_indices` (estructura, 66 filas, sin
    duplicados) y exige además que las filas de cianobacteria ya marcadas
    como listas declaren unidad, dtype, píxeles válidos y cobertura. No
    corrige ninguna fila: si algo falta, se lanza `InputDataError` en vez de
    parchar el dato manualmente aquí.
    """

    rows = validate_manifest_indices() if rows is None else rows
    ready, _pending = split_ready_pending(rows)
    for row in ready:
        for campo in ("unidad", "dtype", "cobertura_valida_pct", "pixeles_validos"):
            if not row.get(campo):
                raise InputDataError(
                    f"Fila de cianobacteria {row['lago']} {row['fecha']} tiene "
                    f"quality_flag='{row['quality_flag']}' pero le falta '{campo}'. "
                    "Corríjase en el cálculo de índices, no aquí."
                )
    return rows


# --------------------------------------------------------------------------
# Estadísticas por escena y resumen temporal
# --------------------------------------------------------------------------


def compute_row_stats(row: dict[str, str], *, raiz: Path | None = None) -> dict[str, float]:
    """Lee el GeoTIFF de cianobacteria de una fila y calcula sus estadísticas.

    Usa únicamente los píxeles numéricamente válidos (no `nodata`) del
    raster ya exportado; no aplica ninguna máscara adicional.
    """

    raiz = RAIZ if raiz is None else raiz
    if not row["ruta_raster"]:
        raise InputDataError(
            f"La fila {row['lago']} {row['fecha']} no declara 'ruta_raster' en el "
            "manifiesto de índices; no puede leerse todavía."
        )
    ruta = raiz / row["ruta_raster"]
    if not ruta.is_file():
        raise InputDataError(
            f"No existe el raster de cianobacteria declarado para {row['lago']} "
            f"{row['fecha']}: {ruta}"
        )

    try:
        import rasterio
    except ImportError as exc:  # pragma: no cover - depende del entorno local
        raise RuntimeError(
            "Para leer los raster de índices instale las dependencias de requirements.txt"
        ) from exc

    with rasterio.open(ruta) as dataset:
        array = dataset.read(1)
    return summarize_array(array)


def _temporal_sort_key(row: dict[str, object]) -> tuple[str, str]:
    return (str(row["lago"]), str(row["fecha"]))


def build_resumen_temporal(
    rows: Sequence[dict[str, str]] | None = None, *, raiz: Path | None = None
) -> list[dict[str, object]]:
    """Construye las filas de `resumen_temporal.csv` para escenas ya listas.

    Las escenas de cianobacteria que siguen `pendiente_calculo` en el
    manifiesto de índices se omiten (no se inventan valores); las fechas
    faltantes quedan disponibles en `pending_report`.
    """

    ready, _pending = split_ready_pending(rows)
    resumen: list[dict[str, object]] = []
    for row in ready:
        stats = compute_row_stats(row, raiz=raiz)
        resumen.append(
            {
                "lago": row["lago"],
                "fecha": row["fecha"],
                "cyano_promedio": stats["mean"],
                "cyano_mediana": stats["median"],
                "cyano_std": stats["std"],
                "pixeles_validos": stats["valid_pixels"],
                "cobertura_valida_pct": stats["coverage_pct"],
                "quality_flag": row["quality_flag"],
            }
        )
    resumen.sort(key=_temporal_sort_key)
    return resumen


def _write_csv_atomic(path: Path, rows: Sequence[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=RESUMEN_TEMPORAL_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def write_resumen_temporal(
    rows: Sequence[dict[str, object]], path: Path | None = None
) -> Path:
    path = RUTA_RESUMEN_TEMPORAL if path is None else path
    _write_csv_atomic(path, rows)
    return path


def read_resumen_temporal(path: Path | None = None) -> list[dict[str, str]]:
    path = RUTA_RESUMEN_TEMPORAL if path is None else path
    with Path(path).open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


# --------------------------------------------------------------------------
# Criterio explícito de "pico"
# --------------------------------------------------------------------------


def flag_peaks(
    resumen: Sequence[dict[str, object]], *, desviaciones: float = PICO_DESVIACIONES
) -> list[dict[str, object]]:
    """Marca picos por lago con un criterio explícito y repetible.

    Una fecha es "pico" si su `cyano_promedio` supera en `desviaciones`
    desviaciones estándar el promedio de la propia serie del lago. La media
    y desviación de referencia se calculan solo con fechas de cobertura
    completa (`quality_flag == "calculado"`); las fechas de cobertura
    parcial (`cobertura_parcial_oficial`, ej. Amatitlán 2026-02-07) se
    evalúan contra ese mismo umbral pero no participan en calcularlo, para
    no distorsionar la referencia con una escena menos confiable.

    Si un lago tiene menos de dos fechas completas todavía no hay
    suficiente información para un umbral significativo: `es_pico` queda en
    `False` y `umbral_pico` vacío en vez de una estadística poco confiable.
    """

    resumen = [dict(row) for row in resumen]
    por_lago: dict[str, list[dict[str, object]]] = {}
    for row in resumen:
        por_lago.setdefault(str(row["lago"]), []).append(row)

    for filas in por_lago.values():
        completas = [f for f in filas if f["quality_flag"] == CALIDAD_COMPLETA]
        valores = [float(f["cyano_promedio"]) for f in completas]
        if len(valores) < 2:
            for f in filas:
                f["es_pico"] = False
                f["umbral_pico"] = ""
            continue
        media = sum(valores) / len(valores)
        varianza = sum((v - media) ** 2 for v in valores) / len(valores)
        std = varianza**0.5
        umbral = media + desviaciones * std
        for f in filas:
            f["es_pico"] = float(f["cyano_promedio"]) > umbral
            f["umbral_pico"] = round(umbral, 4)
    return resumen


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action", choices=("report", "validate", "build"), nargs="?", default="report"
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.action == "report":
        report = pending_report()
        print(
            f"Cianobacteria lista: {report['listas']}/{report['total_escenas']} escenas "
            f"(pendientes: {report['pendientes']})"
        )
        for lago, fecha in report["fechas_pendientes"]:
            print(f"  - pendiente: {lago} {fecha}")
        return 0

    validate_indices_manifest_ready()
    if args.action == "validate":
        print("Manifiesto de índices válido para las filas ya calculadas.")
        return 0

    if args.action == "build":
        resumen = build_resumen_temporal()
        if not resumen:
            print("No hay ninguna escena de cianobacteria calculada todavía; nada que escribir.")
            return 0
        path = write_resumen_temporal(resumen)
        print(f"resumen_temporal.csv escrito con {len(resumen)} filas en {path}")
        return 0
    raise AssertionError(f"Acción no controlada: {args.action}")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, FileExistsError, RuntimeError, InputDataError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
