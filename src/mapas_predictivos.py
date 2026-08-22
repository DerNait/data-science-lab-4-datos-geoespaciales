"""Probabilidades, mapas y diagnostico espacial del mejor modelo."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Sequence

import numpy as np

try:
    from .analisis_espacial import comparison_scale, plot_cyano_map
    from .config import DIR_PROCESSED, DIR_RESULTS_MAPS, DIR_RESULTS_TABLES, LAGOS
    from .evaluacion import leer_metricas, mejor_modelo
    from .features import COLUMNA_RESPUESTA, leer_features
    from .modelos import cargar_modelo, cargar_particion, metadatos_observaciones
except ImportError:  # pragma: no cover
    from analisis_espacial import comparison_scale, plot_cyano_map  # type: ignore
    from config import DIR_PROCESSED, DIR_RESULTS_MAPS, DIR_RESULTS_TABLES, LAGOS  # type: ignore
    from evaluacion import leer_metricas, mejor_modelo  # type: ignore
    from features import COLUMNA_RESPUESTA, leer_features  # type: ignore
    from modelos import cargar_modelo, cargar_particion, metadatos_observaciones  # type: ignore


RUTA_ERRORES_ESPACIALES = DIR_RESULTS_TABLES / "errores_espaciales.csv"
RUTA_PREDICCIONES = DIR_PROCESSED / "ml" / "predicciones_observaciones.parquet"
PASO_CELDA_M = 50.0
UMBRAL_CLASIFICACION = 0.5
LIMITES_PROBABILIDAD = (0.0, 0.25, 0.5, 0.75, 1.0)
ETIQUETAS_PROBABILIDAD = ("muy baja", "baja", "alta", "muy alta")

ERRORES_FIELDS = (
    "lago", "fecha", "zona", "n_prueba", "positivos_reales", "probabilidad_media",
    "verdaderos_negativos", "falsos_positivos", "falsos_negativos", "verdaderos_positivos",
    "tasa_error", "tasa_falsos_positivos", "tasa_falsos_negativos",
)

PREDICCIONES_FIELDS = (
    "indice", "lago", "fecha", "x_utm", "y_utm", "particion", "cyano_alta",
    "probabilidad_alta", "prediccion", "categoria_error",
)


class MapasPredictivosError(RuntimeError):
    pass


def seleccionar_mejor_modelo() -> str:
    filas = [{**fila, "f2": float(fila["f2"])} for fila in leer_metricas()]
    return mejor_modelo(filas)


def clasificar_probabilidades(probabilidades) -> np.ndarray:
    valores = np.asarray(probabilidades, dtype=float)
    if np.any(~np.isfinite(valores)) or np.any((valores < 0) | (valores > 1)):
        raise MapasPredictivosError("Las probabilidades deben ser finitas y estar entre 0 y 1")
    indices = np.searchsorted(np.asarray(LIMITES_PROBABILIDAD[1:-1]), valores, side="right")
    return np.asarray(ETIQUETAS_PROBABILIDAD, dtype=object)[indices]


def categorias_error(y_real, y_predicho) -> np.ndarray:
    real = np.asarray(y_real, dtype=int)
    predicho = np.asarray(y_predicho, dtype=int)
    if real.shape != predicho.shape:
        raise ValueError("La respuesta y la prediccion deben tener el mismo tamano")
    salida = np.empty(real.shape, dtype=object)
    salida[(real == 0) & (predicho == 0)] = "verdadero_negativo"
    salida[(real == 0) & (predicho == 1)] = "falso_positivo"
    salida[(real == 1) & (predicho == 0)] = "falso_negativo"
    salida[(real == 1) & (predicho == 1)] = "verdadero_positivo"
    return salida


def reconstruir_rejilla(x, y, valores, *, paso: float = PASO_CELDA_M):
    """Reconstruye una rejilla regular desde centroides, dejando huecos como NaN."""

    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    valores = np.asarray(valores, dtype=float)
    if not (len(x) == len(y) == len(valores)) or len(x) == 0:
        raise ValueError("x, y y valores deben tener el mismo tamano no vacio")
    x0, y0 = float(x.min()), float(y.min())
    columnas = np.rint((x - x0) / paso).astype(int)
    filas = np.rint((y - y0) / paso).astype(int)
    pares = np.column_stack([filas, columnas])
    if len(np.unique(pares, axis=0)) != len(pares):
        raise MapasPredictivosError("Hay mas de una observacion en una celda de la rejilla")
    rejilla = np.full((filas.max() + 1, columnas.max() + 1), np.nan, dtype=float)
    rejilla[filas, columnas] = valores
    x_edges = x0 - paso / 2 + np.arange(rejilla.shape[1] + 1) * paso
    y_edges = y0 - paso / 2 + np.arange(rejilla.shape[0] + 1) * paso
    return rejilla, x_edges, y_edges


def predecir_observaciones(matriz=None):
    import pandas as pd

    matriz = leer_features() if matriz is None else matriz
    nombre = seleccionar_mejor_modelo()
    paquete = cargar_modelo(nombre)
    columnas = list(paquete["columnas"])
    faltantes = set(columnas) - set(matriz.columns)
    if faltantes:
        raise MapasPredictivosError(f"Faltan columnas para predecir: {sorted(faltantes)}")
    probabilidades = paquete["modelo"].predict_proba(matriz[columnas])[:, 1]
    predicho = (probabilidades >= UMBRAL_CLASIFICACION).astype("int8")
    metadata = metadatos_observaciones(matriz)
    particion = cargar_particion().set_index("indice")["particion"].reindex(matriz.index)
    if particion.isna().any():
        raise MapasPredictivosError("La particion no cubre todas las observaciones")
    resultado = pd.DataFrame(
        {
            "indice": matriz.index,
            "lago": metadata["lago"].to_numpy(),
            "fecha": metadata["fecha"].to_numpy(),
            "x_utm": matriz["x_utm"].to_numpy(),
            "y_utm": matriz["y_utm"].to_numpy(),
            "particion": particion.to_numpy(),
            "cyano_alta": matriz[COLUMNA_RESPUESTA].to_numpy(dtype="int8"),
            "probabilidad_alta": probabilidades,
            "prediccion": predicho,
        },
        index=matriz.index,
    )
    resultado["categoria_error"] = categorias_error(resultado["cyano_alta"], resultado["prediccion"])
    return nombre, resultado


def _zona_espacial(distancia_orilla) -> np.ndarray:
    distancia = np.asarray(distancia_orilla, dtype=float)
    return np.select(
        [distancia <= 250, distancia <= 1000],
        ["orilla_0_250m", "intermedia_250_1000m"],
        default="interior_mas_1000m",
    )


def construir_tabla_errores(predicciones, matriz=None):
    matriz = leer_features() if matriz is None else matriz
    prueba = predicciones[predicciones["particion"] == "prueba"].copy()
    prueba["zona"] = _zona_espacial(matriz.loc[prueba.index, "dist_orilla_m"])
    filas = []
    for (lago, fecha, zona), grupo in prueba.groupby(["lago", "fecha", "zona"], sort=True):
        conteos = grupo["categoria_error"].value_counts()
        vn = int(conteos.get("verdadero_negativo", 0))
        fp = int(conteos.get("falso_positivo", 0))
        fn = int(conteos.get("falso_negativo", 0))
        vp = int(conteos.get("verdadero_positivo", 0))
        positivos = fn + vp
        negativos = vn + fp
        filas.append(
            {
                "lago": lago,
                "fecha": fecha,
                "zona": zona,
                "n_prueba": len(grupo),
                "positivos_reales": positivos,
                "probabilidad_media": round(float(grupo["probabilidad_alta"].mean()), 6),
                "verdaderos_negativos": vn,
                "falsos_positivos": fp,
                "falsos_negativos": fn,
                "verdaderos_positivos": vp,
                "tasa_error": round(float((fp + fn) / len(grupo)), 6),
                "tasa_falsos_positivos": round(float(fp / negativos), 6) if negativos else "indefinido",
                "tasa_falsos_negativos": round(float(fn / positivos), 6) if positivos else "indefinido",
            }
        )
    return filas


def escribir_csv(filas, path: Path, fieldnames: Sequence[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporal = path.with_suffix(path.suffix + ".tmp")
    with temporal.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(filas)
    temporal.replace(path)
    return path


def escribir_predicciones(predicciones, path: Path | None = None) -> Path:
    path = RUTA_PREDICCIONES if path is None else path
    path.parent.mkdir(parents=True, exist_ok=True)
    temporal = path.with_suffix(path.suffix + ".tmp")
    predicciones.loc[:, list(PREDICCIONES_FIELDS)].to_parquet(temporal, index=False)
    temporal.replace(path)
    return path


def fecha_representativa(predicciones, lago: str) -> str:
    subconjunto = predicciones[predicciones["lago"] == lago]
    resumen = subconjunto.groupby("fecha")["cyano_alta"].agg(["sum", "count"])
    resumen["tasa"] = resumen["sum"] / resumen["count"]
    # Mayor numero absoluto de positivos; fecha mas reciente como desempate.
    resumen = resumen.sort_values(["sum", "tasa"], ascending=False)
    maximo = resumen.iloc[0]["sum"]
    candidatas = sorted(resumen[resumen["sum"] == maximo].index)
    return str(candidatas[-1])


def agregar_celdas_para_mapa(tabla):
    """Colapsa solapes de teselas Sentinel-2 sobre el mismo centroide."""

    celdas = (
        tabla.groupby(["x_utm", "y_utm"], as_index=False)
        .agg(cyano_alta=("cyano_alta", "max"), probabilidad_alta=("probabilidad_alta", "mean"))
    )
    celdas["prediccion"] = (celdas["probabilidad_alta"] >= UMBRAL_CLASIFICACION).astype("int8")
    celdas["categoria_error"] = categorias_error(celdas["cyano_alta"], celdas["prediccion"])
    return celdas


def figura_mapa_lago(predicciones, lago: str, *, escala_cyano=None, out_path: Path | None = None) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import BoundaryNorm, ListedColormap

    fecha = fecha_representativa(predicciones, lago)
    tabla = predicciones[(predicciones["lago"] == lago) & (predicciones["fecha"] == fecha)]
    if tabla.empty:
        raise MapasPredictivosError(f"No hay observaciones para {lago} {fecha}")
    tabla = agregar_celdas_para_mapa(tabla)

    escala_cyano = comparison_scale(lagos=tuple(LAGOS)) if escala_cyano is None else escala_cyano
    fig, ejes = plt.subplots(1, 3, figsize=(17, 5.4))
    plot_cyano_map(lago, fecha, ax=ejes[0], vmin=escala_cyano[0], vmax=escala_cyano[1])
    fig.colorbar(ejes[0].images[-1], ax=ejes[0], fraction=0.046, label="cianobacteria (ug/L, proxy)")
    ejes[0].set_title("Referencia satelital de la Parte I")

    rejilla_prob, x_edges, y_edges = reconstruir_rejilla(
        tabla["x_utm"], tabla["y_utm"], tabla["probabilidad_alta"]
    )
    cmap_prob = ListedColormap(["#edf8fb", "#b2e2e2", "#fdbb84", "#e34a33"])
    norm_prob = BoundaryNorm(LIMITES_PROBABILIDAD, cmap_prob.N)
    im_prob = ejes[1].pcolormesh(x_edges, y_edges, rejilla_prob, cmap=cmap_prob, norm=norm_prob, shading="flat")
    cbar = fig.colorbar(im_prob, ax=ejes[1], fraction=0.046, ticks=[0.125, 0.375, 0.625, 0.875])
    cbar.ax.set_yticklabels(ETIQUETAS_PROBABILIDAD)
    ejes[1].set_title("Probabilidad predicha de alta presencia")

    codigos = {"verdadero_negativo": 0, "falso_positivo": 1, "falso_negativo": 2, "verdadero_positivo": 3}
    valores_error = tabla["categoria_error"].map(codigos).to_numpy(dtype=float)
    rejilla_error, xe, ye = reconstruir_rejilla(tabla["x_utm"], tabla["y_utm"], valores_error)
    cmap_error = ListedColormap(["#d9d9d9", "#fdae61", "#762a83", "#1b7837"])
    im_error = ejes[2].pcolormesh(xe, ye, rejilla_error, cmap=cmap_error, vmin=-0.5, vmax=3.5, shading="flat")
    cbar_error = fig.colorbar(im_error, ax=ejes[2], fraction=0.046, ticks=[0, 1, 2, 3])
    cbar_error.ax.set_yticklabels(["VN", "FP", "FN", "VP"])
    ejes[2].set_title("Aciertos y errores a umbral 0.50")

    for eje in ejes:
        eje.set_xlabel("Este (m, UTM)")
        eje.set_ylabel("Norte (m, UTM)")
        eje.set_aspect("equal")
    fig.suptitle(f"{LAGOS[lago].nombre} - {fecha}", fontsize=15)
    fig.tight_layout()
    out_path = DIR_RESULTS_MAPS / f"{lago}_probabilidad_cianobacteria.png" if out_path is None else out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=170, bbox_inches="tight")
    plt.close(fig)
    return out_path


def generar() -> dict[str, object]:
    matriz = leer_features()
    nombre, predicciones = predecir_observaciones(matriz)
    escribir_predicciones(predicciones)
    filas_errores = construir_tabla_errores(predicciones, matriz)
    escribir_csv(filas_errores, RUTA_ERRORES_ESPACIALES, ERRORES_FIELDS)
    escala = comparison_scale(lagos=tuple(LAGOS))
    mapas = [figura_mapa_lago(predicciones, lago, escala_cyano=escala) for lago in sorted(LAGOS)]
    return {
        "modelo": nombre,
        "observaciones": len(predicciones),
        "probabilidad_min": float(predicciones["probabilidad_alta"].min()),
        "probabilidad_max": float(predicciones["probabilidad_alta"].max()),
        "mapas": mapas,
        "errores": RUTA_ERRORES_ESPACIALES,
    }


def verificar() -> dict[str, object]:
    problemas = []
    matriz = leer_features()
    nombre, predicciones = predecir_observaciones(matriz)
    if len(predicciones) != len(matriz):
        problemas.append("El numero de predicciones no coincide con las observaciones")
    if not predicciones["probabilidad_alta"].between(0, 1).all():
        problemas.append("Hay probabilidades fuera de 0 a 1")
    for lago in LAGOS:
        mapa = DIR_RESULTS_MAPS / f"{lago}_probabilidad_cianobacteria.png"
        if not mapa.is_file() or mapa.stat().st_size == 0:
            problemas.append(f"Falta el mapa {mapa}")
    for ruta, campos in ((RUTA_ERRORES_ESPACIALES, ERRORES_FIELDS),):
        if not ruta.is_file():
            problemas.append(f"Falta {ruta}")
            continue
        with ruta.open(newline="", encoding="utf-8") as stream:
            lector = csv.DictReader(stream)
            primera = next(lector, None)
        if primera is None or set(primera) != set(campos):
            problemas.append(f"{ruta} esta vacio o no tiene el contrato esperado")
    if not RUTA_PREDICCIONES.is_file():
        problemas.append(f"Falta {RUTA_PREDICCIONES}")
    else:
        import pandas as pd

        predicciones_guardadas = pd.read_parquet(RUTA_PREDICCIONES)
        if len(predicciones_guardadas) != len(matriz):
            problemas.append("El archivo de probabilidades no cubre todas las observaciones")
        if set(predicciones_guardadas.columns) != set(PREDICCIONES_FIELDS):
            problemas.append("El archivo de probabilidades no tiene el contrato esperado")
    if problemas:
        raise MapasPredictivosError("Los mapas predictivos no cumplen el contrato:\n  - " + "\n  - ".join(problemas))
    return {"modelo": nombre, "observaciones": len(predicciones), "lagos": len(LAGOS)}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("generar", "verificar"), nargs="?", default="verificar")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.action == "generar":
        resumen = generar()
        print(f"Modelo: {resumen['modelo']}; {resumen['observaciones']} probabilidades")
        print(f"Rango: {resumen['probabilidad_min']:.6f} a {resumen['probabilidad_max']:.6f}")
        for ruta in resumen["mapas"]:
            print(f"Mapa: {ruta}")
        return 0
    resumen = verificar()
    print(f"Verificacion correcta: {resumen['observaciones']} predicciones y {resumen['lagos']} mapas.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except MapasPredictivosError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
