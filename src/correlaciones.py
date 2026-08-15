from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path
from typing import Sequence

import numpy as np

try:
    from .analisis_espacial import combined_valid_mask, open_index_raster
    from .config import (
        DIR_RESULTS_FIGURES,
        DIR_RESULTS_MAPS,
        FECHA_COMUN_LAGOS,
        LAGOS,
        MAX_PARES_POR_FECHA_AGRUPADA,
        MAX_PARES_POR_FECHA_FIGURA,
        RAIZ,
        RUTA_CORRELACIONES_FECHA,
        RUTA_CORRELACIONES_LAGO,
        RUTA_DISTRIBUCIONES,
        RUTA_EXTENSION_FLORACION,
        RUTA_RESUMEN_TEMPORAL,
    )
    from .indices import InputDataError, read_manifest_indices, validate_manifest_indices
except ImportError:  # pragma: no cover - permite ejecutar el archivo directamente
    from analisis_espacial import combined_valid_mask, open_index_raster  # type: ignore
    from config import (  # type: ignore
        DIR_RESULTS_FIGURES,
        DIR_RESULTS_MAPS,
        FECHA_COMUN_LAGOS,
        LAGOS,
        MAX_PARES_POR_FECHA_AGRUPADA,
        MAX_PARES_POR_FECHA_FIGURA,
        RAIZ,
        RUTA_CORRELACIONES_FECHA,
        RUTA_CORRELACIONES_LAGO,
        RUTA_DISTRIBUCIONES,
        RUTA_EXTENSION_FLORACION,
        RUTA_RESUMEN_TEMPORAL,
    )
    from indices import InputDataError, read_manifest_indices, validate_manifest_indices  # type: ignore


INDICES_CORRELACION = ("ndvi", "ndwi")
METODOS_CORRELACION = ("pearson", "spearman")

CORRELACIONES_FECHA_FIELDS = (
    "lago",
    "fecha",
    "indice",
    "metodo",
    "coeficiente",
    "p_value",
    "n_pares",
    "direccion",
    "magnitud",
    "quality_flag_cianobacteria",
    "quality_flag_indice",
    "nota_inferencia",
)

CORRELACIONES_LAGO_FIELDS = (
    "lago",
    "indice",
    "metodo",
    "n_fechas",
    "n_pares_total",
    "coeficiente_medio_fechas",
    "coeficiente_mediano_fechas",
    "coeficiente_minimo_fecha",
    "coeficiente_maximo_fecha",
    "fraccion_fechas_positivas",
    "coeficiente_agrupado_estratificado",
    "p_value_agrupado",
    "n_pares_agrupado",
    "magnitud_agrupada",
    "nota_inferencia",
)

DISTRIBUCIONES_FIELDS = (
    "lago",
    "fecha",
    "n_pixeles",
    "min",
    "p01",
    "p05",
    "q25",
    "mediana",
    "media",
    "q75",
    "p95",
    "p99",
    "max",
    "desviacion_std",
    "quality_flag",
    "criterio_seleccion",
)


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


def _same_grid(first: dict, second: dict) -> bool:
    return (
        first["crs"] == second["crs"]
        and first["transform"] == second["transform"]
        and first["width"] == second["width"]
        and first["height"] == second["height"]
    )


def _scene_rows(
    lago: str, fecha: str, rows: Sequence[dict] | None = None
) -> dict[str, dict]:
    rows = validate_manifest_indices() if rows is None else list(rows)
    selected = {
        row["indice"]: row
        for row in rows
        if row["lago"] == lago and row["fecha"] == fecha
    }
    missing = {"cianobacteria", "ndvi", "ndwi"} - set(selected)
    if missing:
        raise InputDataError(
            f"Faltan índices en el manifiesto para {lago} {fecha}: {sorted(missing)}"
        )
    for indice, row in selected.items():
        if not row.get("ruta_raster"):
            raise InputDataError(f"Ruta vacía para {lago} {fecha} {indice}")
    return selected


def load_scene_indices(
    lago: str,
    fecha: str,
    *,
    rows: Sequence[dict] | None = None,
    raiz: Path | None = None,
) -> dict:
    """Carga los tres índices y exige una rejilla exactamente común."""

    selected = _scene_rows(lago, fecha, rows=rows)
    arrays: dict[str, np.ndarray] = {}
    profiles: dict[str, dict] = {}
    for indice in ("cianobacteria", "ndvi", "ndwi"):
        arrays[indice], profiles[indice] = open_index_raster(selected[indice], raiz=raiz)

    reference = profiles["cianobacteria"]
    mismatched = [
        indice for indice in ("ndvi", "ndwi") if not _same_grid(reference, profiles[indice])
    ]
    if mismatched:
        raise InputDataError(
            f"Rejilla incompatible en {lago} {fecha}: {', '.join(mismatched)}"
        )
    return {
        "lago": lago,
        "fecha": fecha,
        "arrays": arrays,
        "profile": reference,
        "rows": selected,
    }


def paired_values(scene: dict, indice: str) -> tuple[np.ndarray, np.ndarray]:
    if indice not in INDICES_CORRELACION:
        raise ValueError(f"Índice no correlacionable: {indice}")
    cyano = scene["arrays"]["cianobacteria"]
    other = scene["arrays"][indice]
    mask = combined_valid_mask(cyano, scene["lago"], scene["profile"])
    mask &= np.isfinite(other)
    return cyano[mask].astype(np.float64), other[mask].astype(np.float64)


def deterministic_sample(*arrays: np.ndarray, max_items: int) -> tuple[np.ndarray, ...]:
    if not arrays:
        return tuple()
    length = len(arrays[0])
    if any(len(array) != length for array in arrays):
        raise ValueError("Las matrices a muestrear deben tener la misma longitud")
    if length <= max_items:
        return tuple(np.asarray(array) for array in arrays)
    indices = np.linspace(0, length - 1, max_items, dtype=np.int64)
    return tuple(np.asarray(array)[indices] for array in arrays)


def correlation_result(x: np.ndarray, y: np.ndarray, metodo: str) -> tuple[float, float]:
    from scipy.stats import pearsonr, spearmanr

    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    valid = np.isfinite(x) & np.isfinite(y)
    x = x[valid]
    y = y[valid]
    if x.size < 3 or np.ptp(x) == 0 or np.ptp(y) == 0:
        return float("nan"), float("nan")
    if metodo == "pearson":
        result = pearsonr(x, y)
    elif metodo == "spearman":
        result = spearmanr(x, y)
    else:
        raise ValueError(f"Método desconocido: {metodo}")
    return float(result.statistic), float(result.pvalue)


def correlation_label(coeficiente: float) -> tuple[str, str]:
    if not np.isfinite(coeficiente):
        return "indeterminada", "indeterminada"
    direccion = "positiva" if coeficiente > 0 else "negativa" if coeficiente < 0 else "nula"
    absolute = abs(coeficiente)
    if absolute < 0.10:
        magnitud = "muy_debil"
    elif absolute < 0.30:
        magnitud = "debil"
    elif absolute < 0.50:
        magnitud = "moderada"
    elif absolute < 0.70:
        magnitud = "fuerte"
    else:
        magnitud = "muy_fuerte"
    return direccion, magnitud


def _format_p_value(value: float) -> str:
    if not np.isfinite(value):
        return ""
    if value == 0 or value < 1e-300:
        return "<1e-300"
    return f"{value:.8g}"


def build_correlations_by_date(rows: Sequence[dict] | None = None) -> list[dict]:
    rows = validate_manifest_indices() if rows is None else list(rows)
    keys = sorted({(row["lago"], row["fecha"]) for row in rows})
    result: list[dict] = []
    for lago, fecha in keys:
        scene = load_scene_indices(lago, fecha, rows=rows)
        for indice in INDICES_CORRELACION:
            x, y = paired_values(scene, indice)
            for metodo in METODOS_CORRELACION:
                coeficiente, p_value = correlation_result(x, y, metodo)
                direccion, magnitud = correlation_label(coeficiente)
                result.append(
                    {
                        "lago": lago,
                        "fecha": fecha,
                        "indice": indice,
                        "metodo": metodo,
                        "coeficiente": round(coeficiente, 8) if np.isfinite(coeficiente) else "",
                        "p_value": _format_p_value(p_value),
                        "n_pares": len(x),
                        "direccion": direccion,
                        "magnitud": magnitud,
                        "quality_flag_cianobacteria": scene["rows"]["cianobacteria"].get(
                            "quality_flag", ""
                        ),
                        "quality_flag_indice": scene["rows"][indice].get("quality_flag", ""),
                        "nota_inferencia": "p_value_exploratorio_por_autocorrelacion_espacial",
                    }
                )
    return result


def _all_pairs_by_group(rows: Sequence[dict]) -> dict[tuple[str, str], tuple[np.ndarray, np.ndarray]]:
    keys = sorted({(row["lago"], row["fecha"]) for row in rows})
    grouped_x: dict[tuple[str, str], list[np.ndarray]] = defaultdict(list)
    grouped_y: dict[tuple[str, str], list[np.ndarray]] = defaultdict(list)
    for lago, fecha in keys:
        scene = load_scene_indices(lago, fecha, rows=rows)
        for indice in INDICES_CORRELACION:
            x, y = paired_values(scene, indice)
            x, y = deterministic_sample(x, y, max_items=MAX_PARES_POR_FECHA_AGRUPADA)
            grouped_x[(lago, indice)].append(x)
            grouped_y[(lago, indice)].append(y)
    return {
        key: (np.concatenate(grouped_x[key]), np.concatenate(grouped_y[key]))
        for key in grouped_x
    }


def build_correlations_by_lake(
    by_date: Sequence[dict], manifest_rows: Sequence[dict] | None = None
) -> list[dict]:
    manifest_rows = validate_manifest_indices() if manifest_rows is None else list(manifest_rows)
    pooled = _all_pairs_by_group(manifest_rows)
    grouped: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for row in by_date:
        grouped[(row["lago"], row["indice"], row["metodo"])].append(row)

    result: list[dict] = []
    for key in sorted(grouped):
        lago, indice, metodo = key
        date_rows = grouped[key]
        coefs = np.array(
            [float(row["coeficiente"]) for row in date_rows if row["coeficiente"] != ""],
            dtype=np.float64,
        )
        x, y = pooled[(lago, indice)]
        pooled_coef, pooled_p = correlation_result(x, y, metodo)
        _direction, magnitude = correlation_label(pooled_coef)
        result.append(
            {
                "lago": lago,
                "indice": indice,
                "metodo": metodo,
                "n_fechas": len(coefs),
                "n_pares_total": sum(int(row["n_pares"]) for row in date_rows),
                "coeficiente_medio_fechas": round(float(np.mean(coefs)), 8),
                "coeficiente_mediano_fechas": round(float(np.median(coefs)), 8),
                "coeficiente_minimo_fecha": round(float(np.min(coefs)), 8),
                "coeficiente_maximo_fecha": round(float(np.max(coefs)), 8),
                "fraccion_fechas_positivas": round(float((coefs > 0).mean()), 4),
                "coeficiente_agrupado_estratificado": round(pooled_coef, 8),
                "p_value_agrupado": _format_p_value(pooled_p),
                "n_pares_agrupado": len(x),
                "magnitud_agrupada": magnitude,
                "nota_inferencia": (
                    "muestra_equilibrada_por_fecha; p_value_exploratorio_por_"
                    "autocorrelacion_espacial"
                ),
            }
        )
    return result


def save_coefficients_figure(rows: Sequence[dict], path: Path | None = None) -> Path:
    import matplotlib.pyplot as plt

    path = DIR_RESULTS_FIGURES / "correlaciones_por_fecha.png" if path is None else path
    path.parent.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(2, 2, figsize=(15, 9), sharey=True)
    colors = {"pearson": "#1261a0", "spearman": "#d1495b"}
    for row_index, indice in enumerate(INDICES_CORRELACION):
        for col_index, lago in enumerate(("amatitlan", "atitlan")):
            ax = axes[row_index, col_index]
            for metodo in METODOS_CORRELACION:
                selected = sorted(
                    (
                        row
                        for row in rows
                        if row["indice"] == indice
                        and row["lago"] == lago
                        and row["metodo"] == metodo
                    ),
                    key=lambda row: row["fecha"],
                )
                ax.plot(
                    [row["fecha"] for row in selected],
                    [float(row["coeficiente"]) for row in selected],
                    marker="o",
                    linewidth=1.7,
                    label=metodo.title(),
                    color=colors[metodo],
                )
                if metodo == "pearson":
                    flagged = [
                        row
                        for row in selected
                        if row["quality_flag_cianobacteria"] != "calculado"
                        or row["quality_flag_indice"] != "calculado"
                    ]
                    if flagged:
                        ax.scatter(
                            [row["fecha"] for row in flagged],
                            [float(row["coeficiente"]) for row in flagged],
                            marker="x",
                            s=65,
                            linewidths=1.8,
                            color="black",
                            label="fecha con advertencia",
                            zorder=5,
                        )
            ax.axhline(0, color="black", linewidth=0.8)
            ax.set_ylim(-1, 1)
            ax.grid(alpha=0.25)
            ax.tick_params(axis="x", rotation=55)
            ax.set_title(f"{LAGOS[lago].nombre}: cianobacteria vs. {indice.upper()}")
            ax.set_ylabel("Coeficiente")
            ax.legend()
    fig.suptitle("Correlaciones por fecha (pares válidos dentro del lago)", fontsize=15)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(path, dpi=170, bbox_inches="tight")
    plt.close(fig)
    return path


def save_hexbin_figures(manifest_rows: Sequence[dict] | None = None) -> list[Path]:
    import matplotlib.pyplot as plt

    manifest_rows = validate_manifest_indices() if manifest_rows is None else list(manifest_rows)
    keys = sorted({(row["lago"], row["fecha"]) for row in manifest_rows})
    output: list[Path] = []
    for lago in ("amatitlan", "atitlan"):
        for indice in INDICES_CORRELACION:
            xs: list[np.ndarray] = []
            ys: list[np.ndarray] = []
            for key_lago, fecha in keys:
                if key_lago != lago:
                    continue
                scene = load_scene_indices(lago, fecha, rows=manifest_rows)
                x, y = paired_values(scene, indice)
                x, y = deterministic_sample(x, y, max_items=MAX_PARES_POR_FECHA_FIGURA)
                xs.append(x)
                ys.append(y)
            x = np.concatenate(xs)
            y = np.concatenate(ys)
            xmin, xmax = np.percentile(x, [1, 99])
            ymin, ymax = np.percentile(y, [1, 99])
            visible = (x >= xmin) & (x <= xmax) & (y >= ymin) & (y <= ymax)
            pearson, _ = correlation_result(x, y, "pearson")
            spearman, _ = correlation_result(x, y, "spearman")

            fig, ax = plt.subplots(figsize=(8.5, 6.5))
            image = ax.hexbin(
                x[visible],
                y[visible],
                gridsize=55,
                mincnt=1,
                bins="log",
                cmap="viridis",
            )
            fig.colorbar(image, ax=ax, label="log10(conteo de pares + 1)")
            ax.set_xlabel("Cianobacteria (µg/L, proxy)")
            ax.set_ylabel(indice.upper())
            ax.set_title(f"{LAGOS[lago].nombre}: cianobacteria vs. {indice.upper()}")
            ax.text(
                0.02,
                0.98,
                f"muestra estratificada n={len(x):,}\nPearson={pearson:.3f}\nSpearman={spearman:.3f}\n"
                "vista: percentiles 1–99",
                transform=ax.transAxes,
                va="top",
                bbox={"facecolor": "white", "alpha": 0.85, "edgecolor": "0.3"},
            )
            ax.grid(alpha=0.15)
            path = DIR_RESULTS_FIGURES / f"{lago}_cianobacteria_{indice}_hexbin.png"
            fig.tight_layout()
            fig.savefig(path, dpi=170, bbox_inches="tight")
            plt.close(fig)
            output.append(path)
    return output


def distribution_stats(values: np.ndarray) -> dict[str, float | int]:
    values = np.asarray(values, dtype=np.float64)
    values = values[np.isfinite(values)]
    if values.size == 0:
        raise InputDataError("No hay valores finitos para resumir la distribución")
    percentiles = np.percentile(values, [1, 5, 25, 50, 75, 95, 99])
    return {
        "n_pixeles": int(values.size),
        "min": float(values.min()),
        "p01": float(percentiles[0]),
        "p05": float(percentiles[1]),
        "q25": float(percentiles[2]),
        "mediana": float(percentiles[3]),
        "media": float(values.mean()),
        "q75": float(percentiles[4]),
        "p95": float(percentiles[5]),
        "p99": float(percentiles[6]),
        "max": float(values.max()),
        "desviacion_std": float(values.std()),
    }


def scene_distribution_values(scene: dict) -> np.ndarray:
    """Cianobacteria válida bajo geometría real y la máscara SCL común."""

    arrays = scene["arrays"]
    mask = combined_valid_mask(arrays["cianobacteria"], scene["lago"], scene["profile"])
    mask &= np.isfinite(arrays["ndvi"]) & np.isfinite(arrays["ndwi"])
    return arrays["cianobacteria"][mask]


def select_distribution_dates(
    temporal_rows: Sequence[dict], extension_rows: Sequence[dict]
) -> dict[str, dict[str, str]]:
    selected: dict[str, dict[str, set[str]]] = {
        lago: defaultdict(set) for lago in LAGOS
    }
    for lago in LAGOS:
        temporal = sorted(
            [row for row in temporal_rows if row["lago"] == lago], key=lambda row: row["fecha"]
        )
        extension = [row for row in extension_rows if row["lago"] == lago]
        complete = [row for row in temporal if row.get("quality_flag") == "calculado"] or temporal
        selected[lago][complete[0]["fecha"]].add("referencia_primera_fecha_completa")
        peak = max(temporal, key=lambda row: float(row["cyano_promedio"]))
        selected[lago][peak["fecha"]].add("pico_promedio_temporal")
        largest = max(extension, key=lambda row: float(row["porcentaje_alto"]))
        selected[lago][largest["fecha"]].add("mayor_extension")
        selected[lago][FECHA_COMUN_LAGOS].add("fecha_comun_entre_lagos")
    return {
        lago: {fecha: ";".join(sorted(reasons)) for fecha, reasons in sorted(dates.items())}
        for lago, dates in selected.items()
    }


def build_distribution_table(
    manifest_rows: Sequence[dict] | None = None,
    temporal_rows: Sequence[dict] | None = None,
    extension_rows: Sequence[dict] | None = None,
) -> tuple[list[dict], dict[str, dict[str, str]]]:
    manifest_rows = validate_manifest_indices() if manifest_rows is None else list(manifest_rows)
    temporal_rows = _read_csv(RUTA_RESUMEN_TEMPORAL) if temporal_rows is None else list(temporal_rows)
    extension_rows = _read_csv(RUTA_EXTENSION_FLORACION) if extension_rows is None else list(extension_rows)
    selections = select_distribution_dates(temporal_rows, extension_rows)
    keys = sorted({(row["lago"], row["fecha"]) for row in manifest_rows})
    result: list[dict] = []
    for lago, fecha in keys:
        scene = load_scene_indices(lago, fecha, rows=manifest_rows)
        row = scene["rows"]["cianobacteria"]
        stats = distribution_stats(scene_distribution_values(scene))
        result.append(
            {
                "lago": lago,
                "fecha": fecha,
                **{key: round(value, 8) if isinstance(value, float) else value for key, value in stats.items()},
                "quality_flag": row.get("quality_flag", ""),
                "criterio_seleccion": selections[lago].get(fecha, ""),
            }
        )
    return result, selections


def save_distribution_figures(
    selections: dict[str, dict[str, str]], manifest_rows: Sequence[dict] | None = None
) -> list[Path]:
    import matplotlib.pyplot as plt

    manifest_rows = validate_manifest_indices() if manifest_rows is None else list(manifest_rows)
    values: dict[tuple[str, str], np.ndarray] = {}
    all_selected: list[np.ndarray] = []
    for lago, dates in selections.items():
        for fecha in dates:
            scene = load_scene_indices(lago, fecha, rows=manifest_rows)
            sample, = deterministic_sample(
                scene_distribution_values(scene), max_items=25_000
            )
            values[(lago, fecha)] = sample
            all_selected.append(sample)
    global_values = np.concatenate(all_selected)
    xmin, xmax = np.percentile(global_values, [1, 99])

    output: list[Path] = []
    for lago, dates in selections.items():
        fig, (ax_hist, ax_box) = plt.subplots(
            2, 1, figsize=(11, 8), gridspec_kw={"height_ratios": [3, 2]}
        )
        labels: list[str] = []
        box_values: list[np.ndarray] = []
        bins = np.linspace(xmin, xmax, 45)
        for fecha, reason in dates.items():
            sample = values[(lago, fecha)]
            visible = sample[(sample >= xmin) & (sample <= xmax)]
            label = f"{fecha} ({reason.replace('_', ' ')})"
            quality = next(
                row["quality_flag"]
                for row in manifest_rows
                if row["lago"] == lago
                and row["fecha"] == fecha
                and row["indice"] == "cianobacteria"
            )
            if quality != "calculado":
                label += f" [advertencia: {quality.replace('_', ' ')}]"
            ax_hist.hist(visible, bins=bins, histtype="step", linewidth=1.8, density=True, label=label)
            labels.append(fecha)
            box_values.append(np.clip(sample, xmin, xmax))
        ax_hist.set_title(f"{LAGOS[lago].nombre}: distribuciones de cianobacteria")
        ax_hist.set_ylabel("Densidad")
        ax_hist.legend(fontsize=8)
        ax_hist.grid(alpha=0.2)
        ax_box.boxplot(
            box_values,
            tick_labels=labels,
            orientation="horizontal",
            showfliers=False,
        )
        ax_box.set_xlabel("Cianobacteria (µg/L, proxy); vista común percentiles globales 1–99")
        ax_box.grid(alpha=0.2)
        fig.tight_layout()
        path = DIR_RESULTS_FIGURES / f"{lago}_distribuciones_cianobacteria.png"
        fig.savefig(path, dpi=170, bbox_inches="tight")
        plt.close(fig)
        output.append(path)
    return output


def difference_raster(
    lago: str,
    fecha_inicial: str,
    fecha_final: str,
    *,
    rows: Sequence[dict] | None = None,
) -> dict:
    initial = load_scene_indices(lago, fecha_inicial, rows=rows)
    final = load_scene_indices(lago, fecha_final, rows=rows)
    if not _same_grid(initial["profile"], final["profile"]):
        raise InputDataError(
            f"No se puede restar {lago}: rejillas distintas entre {fecha_inicial} y {fecha_final}"
        )
    first = initial["arrays"]["cianobacteria"]
    last = final["arrays"]["cianobacteria"]
    valid = combined_valid_mask(first, lago, initial["profile"])
    valid &= np.isfinite(initial["arrays"]["ndvi"])
    valid &= np.isfinite(initial["arrays"]["ndwi"])
    valid &= combined_valid_mask(last, lago, final["profile"])
    valid &= np.isfinite(final["arrays"]["ndvi"])
    valid &= np.isfinite(final["arrays"]["ndwi"])
    difference = np.where(valid, last - first, np.nan).astype(np.float32)
    return {
        "lago": lago,
        "fecha_inicial": fecha_inicial,
        "fecha_final": fecha_final,
        "difference": difference,
        "profile": initial["profile"],
        "n_pares": int(valid.sum()),
        "quality_flag_inicial": initial.get("rows", {})
        .get("cianobacteria", {})
        .get("quality_flag", ""),
        "quality_flag_final": final.get("rows", {})
        .get("cianobacteria", {})
        .get("quality_flag", ""),
    }


def save_difference_maps(
    selections: dict[str, dict[str, str]], manifest_rows: Sequence[dict] | None = None
) -> list[Path]:
    import matplotlib.pyplot as plt
    from rasterio.plot import plotting_extent

    manifest_rows = validate_manifest_indices() if manifest_rows is None else list(manifest_rows)
    differences: list[dict] = []
    for lago, dates in selections.items():
        initial = next(
            fecha for fecha, reason in dates.items() if "referencia_primera_fecha_completa" in reason
        )
        final = next(fecha for fecha, reason in dates.items() if "mayor_extension" in reason)
        differences.append(difference_raster(lago, initial, final, rows=manifest_rows))
    finite_abs = np.concatenate(
        [np.abs(item["difference"][np.isfinite(item["difference"])]) for item in differences]
    )
    vmax = max(1.0, float(np.percentile(finite_abs, 98)))
    output: list[Path] = []
    for item in differences:
        fig, ax = plt.subplots(figsize=(9.5, 6.5))
        image = ax.imshow(
            item["difference"],
            extent=plotting_extent(item["difference"], item["profile"]["transform"]),
            cmap="RdBu_r",
            vmin=-vmax,
            vmax=vmax,
            origin="upper",
        )
        fig.colorbar(image, ax=ax, label="Cambio de cianobacteria (µg/L, proxy)")
        ax.set_title(
            f"{LAGOS[item['lago']].nombre}: {item['fecha_final']} - {item['fecha_inicial']}"
        )
        ax.set_xlabel("Este (m, UTM)")
        ax.set_ylabel("Norte (m, UTM)")
        ax.text(
            0.02,
            0.02,
            f"pares válidos: {item['n_pares']:,}\nescala común centrada en 0\n"
            f"calidad inicial: {item['quality_flag_inicial'] or 'sin dato'}\n"
            f"calidad final: {item['quality_flag_final'] or 'sin dato'}",
            transform=ax.transAxes,
            bbox={"facecolor": "white", "alpha": 0.85, "edgecolor": "0.3"},
        )
        path = DIR_RESULTS_MAPS / (
            f"{item['lago']}_diferencia_cianobacteria_"
            f"{item['fecha_inicial']}_{item['fecha_final']}.png"
        )
        fig.tight_layout()
        fig.savefig(path, dpi=170, bbox_inches="tight")
        plt.close(fig)
        output.append(path)
    return output


def validate_inputs() -> dict[str, int]:
    rows = validate_manifest_indices()
    missing = [row["ruta_raster"] for row in rows if not (RAIZ / row["ruta_raster"]).is_file()]
    if missing:
        raise InputDataError(f"Faltan {len(missing)} rasters referenciados por el manifiesto")
    for lago in LAGOS:
        dates = sorted({row["fecha"] for row in rows if row["lago"] == lago})
        for fecha in dates:
            load_scene_indices(lago, fecha, rows=rows)
    return {"filas_manifest": len(rows), "rasters": len(rows), "escenas": len(rows) // 3}


def run_correlations() -> dict[str, object]:
    manifest_rows = validate_manifest_indices()
    by_date = build_correlations_by_date(manifest_rows)
    by_lake = build_correlations_by_lake(by_date, manifest_rows)
    _write_csv_atomic(RUTA_CORRELACIONES_FECHA, by_date, CORRELACIONES_FECHA_FIELDS)
    _write_csv_atomic(RUTA_CORRELACIONES_LAGO, by_lake, CORRELACIONES_LAGO_FIELDS)
    coefficient_figure = save_coefficients_figure(by_date)
    hexbins = save_hexbin_figures(manifest_rows)
    return {
        "by_date": by_date,
        "by_lake": by_lake,
        "tables": [RUTA_CORRELACIONES_FECHA, RUTA_CORRELACIONES_LAGO],
        "figures": [coefficient_figure, *hexbins],
    }


def run_distributions() -> dict[str, object]:
    manifest_rows = validate_manifest_indices()
    table, selections = build_distribution_table(manifest_rows)
    _write_csv_atomic(RUTA_DISTRIBUCIONES, table, DISTRIBUCIONES_FIELDS)
    figures = save_distribution_figures(selections, manifest_rows)
    maps = save_difference_maps(selections, manifest_rows)
    return {
        "table": table,
        "selections": selections,
        "table_path": RUTA_DISTRIBUCIONES,
        "figures": figures,
        "maps": maps,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=("validate", "correlate", "distributions", "all"),
        nargs="?",
        default="validate",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary = validate_inputs()
    print(
        f"Entradas correctas: {summary['escenas']} escenas, "
        f"{summary['rasters']} rasters alineados"
    )
    if args.action in ("correlate", "all"):
        result = run_correlations()
        print(
            f"Correlaciones: {len(result['by_date'])} filas por fecha y "
            f"{len(result['by_lake'])} filas por lago"
        )
    if args.action in ("distributions", "all"):
        result = run_distributions()
        print(f"Distribuciones: {len(result['table'])} filas y {len(result['maps'])} mapas")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError, InputDataError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
