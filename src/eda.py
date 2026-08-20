"""Ejercicio 1.5 de la Parte 2: analisis exploratorio de las variables del
conjunto de datos de Machine Learning.

Solo lee el conjunto de datos que ya construyo el ejercicio 1
(`src/dataset_ml.py`); no reabre rasters ni recalcula indices.
"""

from __future__ import annotations

from pathlib import Path

try:  # Permite `python -m src.eda` ademas de la importacion normal.
    from .config import DIR_RESULTS_FIGURES, LAGOS
except ImportError:  # pragma: no cover
    from config import DIR_RESULTS_FIGURES, LAGOS  # type: ignore

VARIABLES_NUMERICAS = ("B03", "B08", "ndvi", "ndwi", "cianobacteria_ugl")

# cianobacteria_ugl es fuertemente asimetrica a la derecha (la mayoria de
# celdas tiene valores bajos, unas pocas muy altas); escala log en el eje
# hace visible la forma de esa cola sin recortarla.
VARIABLES_ESCALA_LOG = ("cianobacteria_ugl",)


def _ruta_figura(nombre: str) -> Path:
    DIR_RESULTS_FIGURES.mkdir(parents=True, exist_ok=True)
    return DIR_RESULTS_FIGURES / f"eda_{nombre}.png"


def estadisticas_descriptivas(tabla, *, por: str = "lago"):
    """Estadisticas descriptivas de las variables numericas, agrupadas.

    `por` es "lago", "fecha" o None (sin agrupar, resumen global).
    """

    columnas = list(VARIABLES_NUMERICAS)
    if por is None:
        return tabla[columnas].describe().T
    return tabla.groupby(por)[columnas].describe()


def figura_histogramas(tabla, *, out_path: Path | None = None) -> Path:
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, len(VARIABLES_NUMERICAS), figsize=(4 * len(VARIABLES_NUMERICAS), 3.5))
    for ax, variable in zip(axes, VARIABLES_NUMERICAS):
        valores = tabla[variable].dropna()
        log = variable in VARIABLES_ESCALA_LOG
        if log:
            valores = valores[valores > 0]
        ax.hist(valores, bins=60, color="#2a6f77", alpha=0.85)
        if log:
            ax.set_yscale("log")
            ax.set_title(f"{variable} (eje y en log)")
        else:
            ax.set_title(variable)
        ax.set_xlabel(variable)
        ax.grid(alpha=0.2)
    axes[0].set_ylabel("frecuencia")
    fig.suptitle("Distribucion de las variables numericas del dataset de ML")
    fig.tight_layout()
    out_path = _ruta_figura("histogramas") if out_path is None else out_path
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path


def figura_boxplot_cianobacteria_por_lago(tabla, *, out_path: Path | None = None) -> Path:
    import matplotlib.pyplot as plt

    lagos = sorted(LAGOS)
    datos = [tabla.loc[tabla["lago"] == lago, "cianobacteria_ugl"] for lago in lagos]

    fig, ax = plt.subplots(figsize=(6, 4.5))
    ax.boxplot(datos, tick_labels=[LAGOS[l].nombre for l in lagos], showfliers=True)
    ax.set_ylabel("cianobacteria_ugl (proxy, µg/L)")
    ax.set_title("Distribucion de cianobacteria por lago (todas las fechas)")
    ax.grid(alpha=0.2)
    fig.tight_layout()
    out_path = _ruta_figura("boxplot_cianobacteria_por_lago") if out_path is None else out_path
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path


def figura_boxplot_cianobacteria_por_fecha(tabla, lago: str, *, out_path: Path | None = None) -> Path:
    import matplotlib.pyplot as plt

    subconjunto = tabla[tabla["lago"] == lago]
    fechas = sorted(subconjunto["fecha"].unique())
    datos = [subconjunto.loc[subconjunto["fecha"] == fecha, "cianobacteria_ugl"] for fecha in fechas]

    fig, ax = plt.subplots(figsize=(10, 4.5))
    ax.boxplot(datos, tick_labels=fechas, showfliers=False)
    ax.set_ylabel("cianobacteria_ugl (proxy, µg/L)")
    ax.set_title(f"{LAGOS[lago].nombre}: distribucion de cianobacteria por fecha")
    ax.tick_params(axis="x", rotation=55)
    ax.grid(alpha=0.2)
    fig.tight_layout()
    out_path = _ruta_figura(f"boxplot_cianobacteria_por_fecha_{lago}") if out_path is None else out_path
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path


def matriz_correlacion(tabla):
    return tabla[list(VARIABLES_NUMERICAS)].corr(method="pearson")


def figura_matriz_correlacion(tabla, *, out_path: Path | None = None) -> Path:
    import matplotlib.pyplot as plt

    corr = matriz_correlacion(tabla)
    fig, ax = plt.subplots(figsize=(5.5, 5))
    im = ax.imshow(corr.values, vmin=-1, vmax=1, cmap="RdBu_r")
    ax.set_xticks(range(len(corr.columns)))
    ax.set_yticks(range(len(corr.columns)))
    ax.set_xticklabels(corr.columns, rotation=45, ha="right")
    ax.set_yticklabels(corr.columns)
    for i in range(len(corr.columns)):
        for j in range(len(corr.columns)):
            ax.text(j, i, f"{corr.values[i, j]:.2f}", ha="center", va="center", fontsize=8)
    fig.colorbar(im, ax=ax, fraction=0.046, label="correlacion de Pearson")
    ax.set_title("Correlacion entre variables numericas")
    fig.tight_layout()
    out_path = _ruta_figura("matriz_correlacion") if out_path is None else out_path
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path


def figura_dispersion_geografica(tabla, lago: str, *, out_path: Path | None = None) -> Path:
    import matplotlib.pyplot as plt

    subconjunto = tabla[tabla["lago"] == lago]
    fig, ax = plt.subplots(figsize=(6.5, 5.5))
    orden = subconjunto["cianobacteria_ugl"].argsort()
    disperso = subconjunto.iloc[orden]
    im = ax.scatter(
        disperso["lon"], disperso["lat"], c=disperso["cianobacteria_ugl"],
        cmap="YlOrRd", s=4, vmin=0,
    )
    fig.colorbar(im, ax=ax, label="cianobacteria_ugl (proxy, µg/L)")
    ax.set_xlabel("longitud")
    ax.set_ylabel("latitud")
    ax.set_title(f"{LAGOS[lago].nombre}: dispersion geografica de todas las fechas")
    fig.tight_layout()
    out_path = _ruta_figura(f"dispersion_geografica_{lago}") if out_path is None else out_path
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path


def generar_todas_las_figuras(tabla) -> list[Path]:
    rutas = [figura_histogramas(tabla), figura_boxplot_cianobacteria_por_lago(tabla), figura_matriz_correlacion(tabla)]
    for lago in sorted(LAGOS):
        rutas.append(figura_boxplot_cianobacteria_por_fecha(tabla, lago))
        rutas.append(figura_dispersion_geografica(tabla, lago))
    return rutas
