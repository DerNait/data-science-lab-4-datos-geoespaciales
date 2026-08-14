# Codebook - adquisición Sentinel-2

## Fuente y unidad de observación

El manifiesto `data/raw/manifest_escenas.csv` contiene una fila por combinación
oficial de lago y fecha. Son 22 filas: 11 para Atitlán y 11 para Amatitlán.
Las fechas, satélites, nubosidad y coordenadas provienen del enunciado del
Laboratorio 4. La colección configurada para la consulta es Sentinel-2 Level-2A
en Copernicus Data Space.

## Variables de `manifest_escenas.csv`

| Variable | Tipo | Descripción y valores válidos |
|---|---|---|
| `lago` | texto categórico | `atitlan` o `amatitlan` |
| `fecha` | fecha ISO | Fecha oficial `YYYY-MM-DD` |
| `satelite_oficial` | texto categórico | Sentinel-2A, Sentinel-2B o Sentinel-2C indicado en el PDF |
| `nubosidad_oficial_pct` | decimal | Porcentaje de nubosidad proporcionado para la escena |
| `cobertura_valida_oficial_pct` | decimal nullable | Cobertura válida advertida por el enunciado; 57.1 para Amatitlán `2026-02-07` |
| `west`, `east`, `south`, `north` | decimal | Caja de consulta en longitud/latitud WGS84 |
| `producto` | texto | Colección openEO; por defecto `SENTINEL2_L2A` |
| `bandas` | texto separado por `;` | Bandas solicitadas al batch job |
| `metodo_descarga` | texto | Proveedor y API utilizados |
| `id_adquisicion` | texto nullable | Identificador del batch job de openEO |
| `estado` | categoría | `pendiente`, `en_proceso`, `validado` o `fallido` |
| `ruta_local` | texto nullable | Una o más rutas relativas de los assets descargados |
| `cobertura_valida_pct` | decimal nullable | Porcentaje de píxeles numéricamente válidos medido en los GeoTIFF descargados |
| `crs_salida` | texto nullable | CRS declarado por el producto descargado |
| `resolucion_salida` | texto nullable | Resolución de píxel encontrada en los assets |
| `quality_flag` | categoría | Estado de calidad o advertencia que debe conservar el análisis |
| `observaciones` | texto | Incidencias oficiales o errores auditables de adquisición |

`nubosidad_oficial_pct` y `cobertura_valida_pct` no son la misma medida. La
primera es metadato de la escena; la segunda se calcula sobre el producto
descargado. Tampoco debe reemplazarse la advertencia oficial de 57.1 % con una
medición distinta sin conservar ambas.

## Bandas de la primera descarga

| Banda | Resolución nominal | Uso previsto |
|---|---:|---|
| `B03` | 10 m | Verde; numerador de NDWI junto con B08 |
| `B04` | 10 m | Rojo; numerador de NDVI junto con B08 |
| `B08` | 10 m | Infrarrojo cercano; NDVI y NDWI |
| `SCL` | 20 m | Clasificación de escena para control de nubes, sombras, agua y nodata |

La resolución registrada en el manifiesto debe ser la del archivo recibido,
no solamente la nominal. El backend puede alinear o remuestrear bandas al
exportarlas juntas; cualquier remuestreo posterior debe documentarse.

Las bandas adicionales del índice de cianobacteria se definirán en el ejercicio
3 después de identificar el script exacto. No se descargan por anticipado y no
se deducen de una imagen RGB coloreada.

## GeoJSON de consulta

Los archivos `aoi_atitlan_bbox.geojson` y `aoi_amatitlan_bbox.geojson` están en
`EPSG:4326`. Cada uno contiene un rectángulo creado con las coordenadas del
enunciado. Sus campos principales son:

| Propiedad | Significado |
|---|---|
| `geometry_role` | `query_bbox`: limita la consulta al área de interés |
| `is_lake_boundary` | `false`: no representa el contorno exacto del agua |
| `source` | Procedencia de las coordenadas |

Los GeoJSON oficiales de los lagos, cuando estén disponibles, deben guardarse
sin alterar en `data/raw/geojson/` con nombres distintos.

## Reglas de calidad

- No se aceptan fechas distintas a las 22 oficiales.
- Cada lago debe tener exactamente 11 registros.
- No puede repetirse una combinación `lago` + `fecha`.
- Las cajas deben satisfacer `west < east` y `south < north`.
- Una descarga no sobrescribe una carpeta cruda que ya contiene archivos.
- Todo GeoTIFF descargado debe declarar CRS y tener dimensiones positivas.
- La escena parcial de Amatitlán `2026-02-07` conserva siempre su advertencia.

## Ejercicio 3 - índices NDVI, NDWI y cianobacteria

### Script de cianobacteria elegido

El catálogo https://custom-scripts.sentinel-hub.com/custom-scripts/sentinel-2/
tiene varios scripts relacionados con agua/algas para Sentinel-2: NDCI L1C,
Se2WaQ (calidad de agua general), Maximum Peak Height Bloom Index y APA
Script (plantas acuáticas). Se revisaron los cuatro antes de elegir uno,
como exige la planificación del avance.

| Campo | Valor |
|---|---|
| Nombre | CyanoLakes Chlorophyll-a L1C (NDCI) |
| Autores | Jeremy Kravitz & Mark Matthews (2020) |
| Catálogo | https://custom-scripts.sentinel-hub.com/custom-scripts/sentinel-2/cyanobacteria_chla_ndci_l1c/ |
| Código fuente | https://github.com/sentinel-hub/custom-scripts/blob/master/sentinel-2/cyanobacteria_chla_ndci_l1c/script.js |
| Fecha de consulta | 2026-08-13 |
| Producto Sentinel compatible | Sentinel-2 **L1C** (reflectancia TOA) |
| Bandas usadas | B02, B03, B04, B05, B07, B08, B8A, B11, B12 |
| NDCI | `NDCI = (B05 - B04) / (B05 + B04)` |
| Clorofila-a (proxy de cianobacteria) | `chl = 826.57*NDCI^3 - 176.43*NDCI^2 + 19*NDCI + 4.071` |
| Unidad | µg/L (ajuste sobre dataset simulado; no es una medición de laboratorio) |
| Rango de referencia | 0 a 500 µg/L |
| Máscara de agua propia del script | agua si `MNDWI>0.42` o `NDWI>0.4` o `AWEInsh>0.1879` o `AWEIsh>0.1112` o `NDVI<-0.2` o `NDWI_leaves>1`; se anula si `AWEInsh<=-0.03` o `DBSI>0` (filtro de zonas urbanas/suelo desnudo) |

Se eligió este script porque es el único de los cuatro candidatos nombrado
explícitamente para cianobacteria (no para calidad de agua en general) y
porque su fórmula y umbrales son públicos, no una caja negra.

`src/evalscripts/cyano_ndci_l1c_original.js` es una copia textual, sin
modificar, del script del catálogo (evidencia auditable). Su salida nativa
es una imagen RGB de visualización, no un raster numérico, por lo que **no
se usa para pedir datos**: el laboratorio exige explícitamente un raster
numérico apto para estadísticas.

`src/evalscripts/cyano_ndci_l1c_numeric.js` es la adaptación usada en la
práctica: mismas fórmulas, mismos umbrales, mismas 9 bandas de entrada;
solo cambia la salida, de un color a un valor `FLOAT32` (`chl`) con una
banda `dataMask` que marca válido únicamente lo que el propio script
clasifica como agua. No se agregó, quitó ni simplificó ningún término de la
fórmula original.

### Decisión: L1C vía Sentinel Hub, no reproducción local sobre L2A

El polinomio de clorofila-a fue calibrado sobre reflectancia **L1C** (tope
de atmósfera), no sobre L2A (reflectancia de superficie, ya corregida
atmosféricamente) usada para NDVI/NDWI. Reproducir la
fórmula localmente sobre L2A daría valores distintos a los que el script
fue diseñado a producir. Por eso, siguiendo el enunciado ("descargue el
resultado del script de Sentinel Hub cuando sea posible"), el índice de
cianobacteria se pide directamente a la Process API de Sentinel Hub /
Copernicus Data Space sobre Sentinel-2 L1C, y el resultado (ya calculado)
se guarda como raster crudo:

| Elemento | Valor |
|---|---|
| Token OAuth2 (client credentials) | `https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token` |
| Process API | `https://sh.dataspace.copernicus.eu/api/v1/process` |
| Tipo de colección | `S2L1C` |
| Credenciales | OAuth client de Copernicus Data Space (Dashboard > User Settings > OAuth clients), variables `SENTINEL_HUB_CLIENT_ID` / `SENTINEL_HUB_CLIENT_SECRET` en `.env`, nunca versionadas |

El raster crudo se guarda sin modificar en
`data/raw/rasters/<lago>/<fecha>/cyano_ndci_l1c.tif` (mismo criterio de "no
sobrescribir" usado para las bandas L2A).

### Fórmulas de NDVI y NDWI

- `NDVI = (B08 - B04) / (B08 + B04)`
- `NDWI = (B03 - B08) / (B03 + B08)`

Ambas se calculan localmente sobre las bandas L2A ya descargadas.
Donde el denominador es 0 el resultado se guarda como `nodata` (no como
error ni como 0), evitando divisiones inválidas.

Además de la clase SCL, se excluye cualquier píxel donde B03, B04 u B08
tenga exactamente el valor `nodata` del raster (-32768 en las descargas de
openEO). Se detectó en la primera escena real (`amatitlan/2025-01-28`) que
SCL puede marcar un píxel como agua (clase 6) aunque una banda de
reflectancia esté en `nodata`; ocurre en 12 de las 22 escenas descargadas,
en magnitudes pequeñas (1 a 367 píxeles por escena). Sin este filtro
adicional esos píxeles producirían valores de NDVI/NDWI sin sentido.

**Valores fuera de \[-1, 1\] y columna `frac_valores_atipicos`:** NDVI y NDWI
están matemáticamente acotados a [-1, 1]. Sobre agua profunda, B04 y/o B08
pueden tener reflectancia muy cercana a cero (a veces negativa) por ruido de
la corrección atmosférica de Sentinel-2 L2A; eso vuelve inestable el
cociente y produce valores fuera de ese rango. No es un error de cálculo:
la fórmula se aplicó tal cual sobre las bandas descargadas, sin recortar ni
excluir esos píxeles, porque el enunciado no pide una fórmula distinta.

En vez de reportar solo un promedio general, `manifest_indices.csv` guarda
por fila la fracción de píxeles fuera de rango (`frac_valores_atipicos`).
En las 22 escenas reales esa fracción es casi siempre baja (0-8 %), pero
**tres fechas de Atitlán se apartan claramente del resto** y superan el
umbral `UMBRAL_FRACCION_VALORES_ATIPICOS = 0.10` definido en `config.py`:

| Fecha | NDVI fuera de rango | NDWI fuera de rango |
|---|---:|---:|
| `2025-01-18` | 27.9 % | 30.7 % |
| `2025-11-21` | 15.4 % | 16.3 % |
| `2026-02-12` | 13.4 % | 20.3 % |

Esas tres filas quedan con `quality_flag = revisar_valores_atipicos` (en
vez de `calculado`) para que el análisis temporal (ejercicio 4) y el
informe no traten su promedio como igual de confiable que el resto; por
ejemplo, `2025-01-18` tiene una mediana de NDVI de 0.55 (parecería
vegetación densa), claramente un artefacto de las bandas y no una lectura
real sobre agua. Debe interpretarse como limitación de los datos de esas
fechas puntuales, no como hallazgo ambiental.

### Máscara espacial mientras no exista el GeoJSON oficial del lago

Los GeoJSON actuales (`data/raw/geojson/aoi_*_bbox.geojson`) son cajas de
consulta, no el contorno del agua (ver sección "GeoJSON de consulta" más
arriba). Mientras ese contorno oficial no esté disponible, NDVI y NDWI se
enmascaran con la clase **agua (valor 6)** de la banda `SCL` de Sentinel-2
L2A, excluyendo además nubes, sombras, nieve, píxeles saturados y `nodata`
(clases SCL 0, 1, 2, 3, 8, 9, 10, 11). Es una máscara calculada por escena
(cambia con las nubes de cada fecha), más precisa que un polígono fijo,
pero puede incluir agua fuera del lago si hubiera otro cuerpo de agua
dentro del bbox. Cuando el GeoJSON oficial esté disponible debe
**intersectarse** con esta máscara, no reemplazarla.

La máscara de cianobacteria es independiente: usa el water body index que
trae el propio script (basado en L1C), no la SCL de L2A, porque son
productos y fechas de reflectancia distintos.

### Alineación espacial

Los tres índices de una misma fecha se exportan sobre la misma rejilla
(resolución objetivo `RESOLUCION_OBJETIVO_M = 10` m, CRS y transform de las
bandas L2A). Si el raster de cianobacteria llega con una rejilla distinta,
se realinea con remuestreo bilineal (`rasterio.warp.reproject`) antes de
comparar o correlacionar los tres productos.

### Límite de tamaño de la Process API (bbox de Atitlán)

La Process API de Sentinel Hub rechaza peticiones síncronas con
`width`/`height` mayores a 2500 px (`SENTINEL_HUB_MAX_DIMENSION_PX` en
`src/indices.py`). La caja de Atitlán a `RESOLUCION_OBJETIVO_M = 10` m
produce 2836×1739 px, por encima de ese límite (Amatitlán, más pequeña,
queda justo por debajo con 1393×906 px). `request_cyano_layer` detecta
cuando la dimensión mayor excede el límite y reduce `width`/`height`
proporcionalmente (mismo aspect ratio) antes de pedir el raster. Esto solo
afecta la resolución del insumo crudo de cianobacteria de Atitlán: el
`align_to_reference` posterior lo remuestrea igual a la rejilla común de
10 m, así que el GeoTIFF exportado en `data/processed/indices/` no cambia
de resolución.

### Variables de `data/processed/manifest_indices.csv`

Contrato de entrega del ejercicio 3 hacia el ejercicio 4. Una fila por lago, fecha
e índice: 22 escenas x 3 índices = 66 filas.

| Variable | Tipo | Descripción |
|---|---|---|
| `lago` | texto categórico | `atitlan` o `amatitlan` |
| `fecha` | fecha ISO | Fecha oficial `YYYY-MM-DD` |
| `indice` | texto categórico | `ndvi`, `ndwi` o `cianobacteria` |
| `ruta_raster` | texto | Ruta relativa del GeoTIFF de una sola banda `float32` |
| `metodo` | texto | Cómo se obtuvo (local L2A + máscara SCL, o Sentinel Hub Process API sobre L1C) |
| `formula_version` | texto | Identificador de versión de fórmula (`ndvi-v1`, `ndwi-v1`, `cyano-ndci-l1c-v1-numeric`) |
| `unidad` | texto | `adimensional` (NDVI/NDWI) o µg/L (cianobacteria) |
| `dtype` | texto | Siempre `float32` |
| `nodata` | texto | Siempre `nan` |
| `crs` | texto | CRS del raster exportado |
| `resolucion_m` | decimal | Resolución de la rejilla común |
| `pixeles_validos` | entero | Píxeles no `nodata` del índice |
| `pixeles_lago` | entero | Píxeles que pasan la máscara de agua/válido usada |
| `cobertura_valida_pct` | decimal | `100 * pixeles_validos / pixeles_totales` |
| `frac_valores_atipicos` | decimal (0-1) | Fracción de píxeles fuera del rango teórico del índice ([-1,1] en NDVI/NDWI, [0,500] en cianobacteria). Vacío para cianobacteria mientras no se calcule |
| `quality_flag` | categoría | `pendiente_calculo`, `calculado`, `cobertura_parcial_oficial` o `revisar_valores_atipicos` |

`quality_flag = revisar_valores_atipicos` se asigna cuando
`frac_valores_atipicos` supera `UMBRAL_FRACCION_VALORES_ATIPICOS` (0.10);
ver la sección de fórmulas de NDVI/NDWI para las tres fechas de Atitlán
afectadas y su interpretación.

`quality_flag = cobertura_parcial_oficial` se conserva para las tres filas
de `amatitlan 2026-02-07`, heredando la advertencia de
`manifest_escenas.csv`.

## Ejercicio 4 - análisis temporal de cianobacteria

`src/analisis_temporal.py` lee únicamente `manifest_indices.csv` (nunca
rutas propias) para construir `data/processed/tablas/resumen_temporal.csv`.
No corrige raster ni completa filas pendientes: si una fila lista de
cianobacteria tiene un campo vacío, se lanza un error para que se corrija
en el cálculo de índices, no en este paso.

### Variables de `data/processed/tablas/resumen_temporal.csv`

Una fila por lago y fecha, solo para las escenas de cianobacteria que ya
tienen `quality_flag` distinto de `pendiente_calculo`.

| Variable | Tipo | Descripción |
|---|---|---|
| `lago` | texto categórico | `atitlan` o `amatitlan` |
| `fecha` | fecha ISO | Fecha oficial `YYYY-MM-DD` |
| `cyano_promedio` | decimal | Promedio de cianobacteria sobre los píxeles válidos del raster |
| `cyano_mediana` | decimal | Mediana de los mismos píxeles válidos |
| `cyano_std` | decimal | Desviación estándar de los mismos píxeles válidos |
| `pixeles_validos` | entero | Píxeles no `nodata` usados en las estadísticas anteriores |
| `cobertura_valida_pct` | decimal | `100 * pixeles_validos / pixeles_totales` del raster |
| `quality_flag` | categoría | Heredado de `manifest_indices.csv`: `calculado` o `cobertura_parcial_oficial` |

### Criterio de "pico"

Una fecha se marca como pico si su `cyano_promedio` supera en
`PICO_DESVIACIONES` (1.0 por defecto, `src/config.py`) desviaciones
estándar el promedio de la propia serie del lago. La media y desviación de
referencia se calculan solo con fechas de `quality_flag == "calculado"`;
las fechas de cobertura parcial se evalúan contra ese mismo umbral pero no
participan en calcularlo, para no distorsionar la referencia con una
escena menos confiable. Con menos de dos fechas completas en un lago no
hay suficiente información para un umbral significativo y ninguna fecha se
marca como pico.

Es un umbral descriptivo y repetible, no un modelo de series de tiempo:
cada lago tiene 11 observaciones irregulares, insuficientes para afirmar
estacionalidad o tendencias estadísticamente robustas.

