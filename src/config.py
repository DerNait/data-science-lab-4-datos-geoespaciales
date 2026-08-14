from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path


RAIZ = Path(__file__).resolve().parent.parent
DIR_DATA = RAIZ / "data"
DIR_RAW = DIR_DATA / "raw"
DIR_GEOJSON = DIR_RAW / "geojson"
DIR_RASTERS = DIR_RAW / "rasters"
DIR_PROCESSED = DIR_DATA / "processed"
DIR_INDICES = DIR_PROCESSED / "indices"
DIR_TABLAS = DIR_PROCESSED / "tablas"

RUTA_MANIFEST_ESCENAS = DIR_RAW / "manifest_escenas.csv"
RUTA_MANIFEST_INDICES = DIR_PROCESSED / "manifest_indices.csv"

OPENEO_BACKEND_URL = os.getenv(
    "OPENEO_BACKEND_URL", "https://openeofed.dataspace.copernicus.eu"
)
OPENEO_COLLECTION_ID = os.getenv("OPENEO_COLLECTION_ID", "SENTINEL2_L2A")

# B03, B04 y B08 permiten calcular NDWI y NDVI. SCL se incluye únicamente
# como banda de calidad para identificar nubes, sombras, agua y nodata en L2A.
BANDAS_MINIMAS = ("B03", "B04", "B08", "SCL")

CRS_AOI = "EPSG:4326"

# --- Ejercicio 3 (Persona B): índices NDVI, NDWI y cianobacteria ---------

DIR_EVALSCRIPTS = RAIZ / "src" / "evalscripts"
RUTA_CYANO_EVALSCRIPT_ORIGINAL = DIR_EVALSCRIPTS / "cyano_ndci_l1c_original.js"
RUTA_CYANO_EVALSCRIPT_NUMERICO = DIR_EVALSCRIPTS / "cyano_ndci_l1c_numeric.js"

# Script elegido del catálogo https://custom-scripts.sentinel-hub.com tras
# revisar varios candidatos para Sentinel-2 (NDCI L1C, Se2WaQ, Maximum Peak
# Height Bloom Index, APA Script). Se documenta aquí, en codebook.md y en el
# notebook 03_indices.ipynb el porqué de la elección: es el único de los
# candidatos nombrado explícitamente para cianobacteria, con fórmula y
# umbrales públicos y auditables (no es una caja negra).
CYANO_SCRIPT = {
    "nombre": "CyanoLakes Chlorophyll-a L1C (NDCI)",
    "autores": "Jeremy Kravitz & Mark Matthews (2020)",
    "url_catalogo": (
        "https://custom-scripts.sentinel-hub.com/custom-scripts/"
        "sentinel-2/cyanobacteria_chla_ndci_l1c/"
    ),
    "url_fuente": (
        "https://github.com/sentinel-hub/custom-scripts/blob/master/"
        "sentinel-2/cyanobacteria_chla_ndci_l1c/script.js"
    ),
    "fecha_consulta": "2026-08-13",
    "producto_sentinel": "Sentinel-2 L1C (reflectancia TOA)",
    "bandas": ("B02", "B03", "B04", "B05", "B07", "B08", "B8A", "B11", "B12"),
    "formula_ndci": "NDCI = (B05 - B04) / (B05 + B04)",
    "formula_chl": "chl = 826.57*NDCI^3 - 176.43*NDCI^2 + 19*NDCI + 4.071",
    "mascara": (
        "Water Body Index propio del script: agua si MNDWI>0.42 o NDWI>0.4 o "
        "AWEInsh>0.1879 o AWEIsh>0.1112 o NDVI<-0.2 o NDWI_leaves>1, con "
        "filtro adicional de zonas urbanas/suelo desnudo (AWEInsh<=-0.03 o "
        "DBSI>0 anulan la clase agua)."
    ),
    "unidad": "µg/L (proxy de clorofila-a; polinomio ajustado sobre dataset simulado)",
    "rango_valido": (0.0, 500.0),
    "formula_version": "cyano-ndci-l1c-v1-numeric",
}

INDICES = ("ndvi", "ndwi", "cianobacteria")

FORMULAS_INDICES = {
    "ndvi": "NDVI = (B08 - B04) / (B08 + B04)",
    "ndwi": "NDWI = (B03 - B08) / (B03 + B08)",
    "cianobacteria": CYANO_SCRIPT["formula_chl"],
}

# Resolución común (metros) a la que se alinean los tres índices de una
# misma fecha antes de exportarlos, para que queden espacialmente
# comparables entre sí.
RESOLUCION_OBJETIVO_M = 10

MANIFEST_INDICES_FIELDS = (
    "lago",
    "fecha",
    "indice",
    "ruta_raster",
    "metodo",
    "formula_version",
    "unidad",
    "dtype",
    "nodata",
    "crs",
    "resolucion_m",
    "pixeles_validos",
    "pixeles_lago",
    "cobertura_valida_pct",
    "quality_flag",
)

# Copernicus Data Space Ecosystem / Sentinel Hub (Process API) para obtener
# el resultado numérico del script de cianobacteria. Son credenciales de
# tipo OAuth client (Dashboard > User Settings > OAuth clients), distintas
# de la sesión OIDC personal usada por openEO. Nunca se escriben valores
# reales en config.py, .env.example ni en el notebook.
SENTINEL_HUB_TOKEN_URL = os.getenv(
    "SENTINEL_HUB_TOKEN_URL",
    "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token",
)
SENTINEL_HUB_PROCESS_URL = os.getenv(
    "SENTINEL_HUB_PROCESS_URL", "https://sh.dataspace.copernicus.eu/api/v1/process"
)
SENTINEL_HUB_CLIENT_ID = os.getenv("SENTINEL_HUB_CLIENT_ID", "")
SENTINEL_HUB_CLIENT_SECRET = os.getenv("SENTINEL_HUB_CLIENT_SECRET", "")
SENTINEL2_L1C_TYPE = "S2L1C"


@dataclass(frozen=True)
class Lago:
    slug: str
    nombre: str
    west: float
    east: float
    south: float
    north: float

    def bbox(self) -> dict[str, float | str]:
        return {
            "west": self.west,
            "south": self.south,
            "east": self.east,
            "north": self.north,
            "crs": CRS_AOI,
        }


@dataclass(frozen=True)
class EscenaOficial:
    lago: str
    fecha: str
    nubosidad_oficial_pct: float
    satelite_oficial: str
    cobertura_valida_oficial_pct: float | None = None
    observacion_oficial: str = ""

    def fecha_date(self) -> date:
        return date.fromisoformat(self.fecha)


LAGOS = {
    "atitlan": Lago(
        slug="atitlan",
        nombre="Lago de Atitlán",
        west=-91.326256,
        east=-91.07151,
        south=14.5948,
        north=14.750979,
    ),
    "amatitlan": Lago(
        slug="amatitlan",
        nombre="Lago de Amatitlán",
        west=-90.638065,
        east=-90.512924,
        south=14.412347,
        north=14.493799,
    ),
}


ESCENAS_OFICIALES = (
    EscenaOficial("amatitlan", "2025-01-28", 0.06, "Sentinel-2B"),
    EscenaOficial("amatitlan", "2025-04-15", 0.09, "Sentinel-2A"),
    EscenaOficial("amatitlan", "2025-04-28", 1.03, "Sentinel-2B"),
    EscenaOficial("amatitlan", "2025-11-24", 0.50, "Sentinel-2B"),
    EscenaOficial("amatitlan", "2026-01-08", 0.77, "Sentinel-2C"),
    EscenaOficial("amatitlan", "2026-02-02", 0.39, "Sentinel-2B"),
    EscenaOficial(
        "amatitlan",
        "2026-02-07",
        0.02,
        "Sentinel-2C",
        cobertura_valida_oficial_pct=57.1,
        observacion_oficial=(
            "Fecha oficial incluida para completar 11 observaciones; "
            "cobertura válida parcial aproximada de 57.1 %."
        ),
    ),
    EscenaOficial("amatitlan", "2026-03-29", 0.01, "Sentinel-2C"),
    EscenaOficial("amatitlan", "2026-04-13", 0.09, "Sentinel-2B"),
    EscenaOficial("amatitlan", "2026-04-28", 4.96, "Sentinel-2C"),
    EscenaOficial("amatitlan", "2026-06-19", 13.00, "Sentinel-2A"),
    EscenaOficial("atitlan", "2025-01-18", 0.02, "Sentinel-2B"),
    EscenaOficial("atitlan", "2025-04-13", 0.54, "Sentinel-2C"),
    EscenaOficial("atitlan", "2025-05-13", 4.37, "Sentinel-2C"),
    EscenaOficial("atitlan", "2025-07-17", 3.57, "Sentinel-2A"),
    EscenaOficial("atitlan", "2025-11-21", 3.15, "Sentinel-2A"),
    EscenaOficial("atitlan", "2025-12-29", 3.17, "Sentinel-2C"),
    EscenaOficial("atitlan", "2026-02-12", 0.04, "Sentinel-2B"),
    EscenaOficial("atitlan", "2026-03-24", 3.17, "Sentinel-2B"),
    EscenaOficial("atitlan", "2026-04-13", 0.01, "Sentinel-2B"),
    EscenaOficial("atitlan", "2026-04-28", 4.96, "Sentinel-2C"),
    EscenaOficial("atitlan", "2026-07-22", 4.02, "Sentinel-2B"),
)


def validate_configuration() -> None:
    """Valida el contrato estático antes de consultar o descargar datos."""

    if set(LAGOS) != {"atitlan", "amatitlan"}:
        raise ValueError("La configuración debe contener Atitlán y Amatitlán")

    if len(ESCENAS_OFICIALES) != 22:
        raise ValueError("Se esperaban exactamente 22 escenas oficiales")

    keys = [(scene.lago, scene.fecha) for scene in ESCENAS_OFICIALES]
    if len(keys) != len(set(keys)):
        raise ValueError("Existen combinaciones lago-fecha duplicadas")

    for slug, lago in LAGOS.items():
        if not (lago.west < lago.east and lago.south < lago.north):
            raise ValueError(f"Caja espacial inválida para {slug}")
        n_scenes = sum(scene.lago == slug for scene in ESCENAS_OFICIALES)
        if n_scenes != 11:
            raise ValueError(f"{slug} debe tener exactamente 11 fechas")

    for scene in ESCENAS_OFICIALES:
        if scene.lago not in LAGOS:
            raise ValueError(f"Lago desconocido en escena: {scene.lago}")
        scene.fecha_date()
        if not 0 <= scene.nubosidad_oficial_pct <= 100:
            raise ValueError(f"Nubosidad inválida para {scene.lago} {scene.fecha}")

    partial = next(
        scene
        for scene in ESCENAS_OFICIALES
        if scene.lago == "amatitlan" and scene.fecha == "2026-02-07"
    )
    if partial.cobertura_valida_oficial_pct != 57.1:
        raise ValueError("Se perdió la advertencia de cobertura parcial oficial")


validate_configuration()

