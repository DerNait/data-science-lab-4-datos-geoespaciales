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

## Ejercicio 5 - análisis espacial

`src/analisis_espacial.py` lee únicamente los raster ya exportados por el
ejercicio 3 (`data/processed/manifest_indices.csv`); no reabre bandas
crudas ni cambia la máscara SCL-agua que produjo esos raster. La
geometría real del lago se aplica aquí, sobre los productos ya calculados,
como una intersección adicional.

### Contorno real del lago (OpenStreetMap)

| Campo | Valor |
|---|---|
| Fuente | OpenStreetMap, vía Overpass API |
| Endpoint | `https://overpass-api.de/api/interpreter` |
| Consulta (Overpass QL) | `[out:json][timeout:90]; nwr["natural"="water"]["name"="Lago de Atitlán"]; out geom;` (análoga para Amatitlán; se prueban variantes en español e inglés del nombre) |
| Licencia | Open Database License (ODbL) 1.0 - © OpenStreetMap contributors |
| Fecha de consulta | 2026-08-14 |
| Área obtenida | Atitlán ≈ 124.70 km² (bbox de consulta: 474.23 km², razón 0.263); Amatitlán ≈ 15.02 km² (bbox: 121.71 km², razón 0.123) |

El contorno se pide una sola vez por lago (`request_lake_boundary`) y se
cachea sin sobrescribir en `data/raw/geojson/lago_<lago>_boundary.geojson`,
con el mismo patrón "pedir una vez y cachear" que ya usa
`indices.request_cyano_layer` para el raster crudo de cianobacteria (ver
ejercicio 3). El bbox de consulta original (`aoi_<lago>_bbox.geojson`) no
se modifica ni se sobrescribe. Cualquier fallo de red o "no encontrado" se
relanza como `OverpassError` explícito: nunca se cae en silencio de
vuelta al bbox de consulta como sustituto.

### Máscara combinada (geometría real ∩ máscara SCL-agua)

`combined_valid_mask(array, lago, profile)` calcula
`isfinite(array) & lake_geometry_mask(lago, profile)` directamente sobre
el raster ya exportado, en vez de reabrir las bandas `SCL` crudas. Esto es
posible porque el raster de cada índice solo tiene valores numéricos donde
ya pasó la máscara SCL-agua de esa escena (ver ejercicio 3); intersectar
la geometría real sobre ese mismo array logra "geometría real ∩ máscara ya
usada" sin duplicar ni modificar el pipeline de `indices.py`. La geometría
(en `EPSG:4326`) se reproyecta al CRS del raster (`EPSG:32615`) con
`rasterio.warp.transform_geom` y se rasteriza con
`rasterio.features.geometry_mask`.

Ejemplo de sanidad (Atitlán, `2026-04-13`): máscara SCL-agua sola =
1 218 570 píxeles válidos; máscara combinada (SCL-agua ∩ geometría real) =
1 218 250 píxeles válidos (≈ 0.03 % menos). La máscara SCL-agua ya era
bastante ajustada al lago; la geometría real recorta un margen pequeño
adicional, principalmente en orillas.

### Escala de color fija

`comparison_scale()` calcula el percentil 98 de todos los píxeles válidos
(máscara combinada) de cianobacteria de ambos lagos, con un piso en
`UMBRAL_CIANOBACTERIA_ALTO_UGL` (ver ejercicio 8.1) para que la escala
nunca quede más angosta que el umbral de "valor alto". Es una decisión de
**visualización** (para que los mapas sean comparables entre fechas y
lagos), distinta del umbral cuantitativo usado en 8.1/8.2. En la corrida
actual el percentil 98 global queda por debajo de 10 µg/L, así que la
escala final usada es `[0.00, 10.00]` µg/L (domina el piso del umbral).

### Fecha "crítica" provisional

Los paneles comparativos usan como fecha crítica la que
`analisis_temporal.flag_peaks()` ya marca como pico (media + 1 desviación
estándar) en cada lago. Es una elección provisional, documentada como tal
en `notebooks/05_analisis_espacial.ipynb`; el ejercicio 7 (comparación
conjunta de los dos lagos) puede confirmarla o ajustarla.

### Variables de `results/tables/metadata_mapas.csv`

Una fila por mapa generado (individual, comparativo, comparación entre
lagos, persistencia o interactivo).

| Variable | Tipo | Descripción |
|---|---|---|
| `lago` | texto | Lago o lagos (`;` si aplica a varios) |
| `fecha` | texto | Fecha o fechas (`;` si el mapa combina varias) |
| `indice` | texto | Siempre `cianobacteria` |
| `tipo_mapa` | categoría | `individual`, `comparativo`, `comparativo_entre_lagos`, `persistencia` o `interactivo` |
| `archivo` | texto | Ruta relativa a la raíz del repositorio |
| `formato` | categoría | `png` o `html` |
| `vmin`, `vmax` | decimal | Escala de color usada en ese mapa |
| `umbral_alto_ugl` | decimal | Umbral de "valor alto" usado (solo en mapas de persistencia) |
| `generado_en` | texto | Marca de tiempo ISO de cuándo se generó el archivo |

### Convención de nombres de archivo

| Contenido | Ruta |
|---|---|
| Mapa individual | `results/maps/<lago>_<fecha>_cianobacteria.png` |
| Panel comparativo por lago | `results/maps/<lago>_comparativo_cianobacteria.png` |
| Comparación entre lagos (fecha común) | `results/maps/comparacion_lagos_2026-04-13_cianobacteria.png` |
| Mapa de persistencia | `results/maps/<lago>_persistencia_cianobacteria.png` |
| Mapa interactivo | `results/maps/<lago>_interactivo.html` |
| Serie de extensión (8.1) | `results/figures/<lago>_extension_floracion.png` |
| Contorno real OSM | `data/raw/geojson/lago_<lago>_boundary.geojson` |

## Ejercicio 8.1 - extensión espacial de valores altos

### Umbral de "valor alto"

`UMBRAL_CIANOBACTERIA_ALTO_UGL = 10.0` (`src/config.py`) es un umbral de
salud pública **externo a este conjunto de datos**, fijado antes de
calcular qué porcentaje de cada lago queda por encima, para no elegirlo
según qué tan llamativo se vea el resultado. Se aplica únicamente a
píxeles que pasan la máscara combinada (geometría real ∩ SCL-agua) de la
escena correspondiente, y en la Parte II es también el corte de la
variable respuesta binaria `cyano_alta` (ver más abajo, "Ejercicio 2").

**Nota de precisión (corregida respecto a una versión anterior de este
codebook):** este umbral no corresponde exactamente al "Alert Level 1" de
la OMS como se afirmaba antes. Verificando la tabla original: 10 µg/L cae
en el extremo superior del **nivel de vigilancia** de la OMS (~1-12 µg/L),
justo antes de entrar a Alert Level 1 (~12-24 µg/L). Sí corresponde con
precisión al rango **eutrófico** (8-25 µg/L) de la clasificación trófica
de la OECD (1982). Ver "Ejercicio 2 - justificación del punto de corte"
para las referencias completas y verificadas.

### Área de píxel

El CRS de salida de los raster ya es UTM (`EPSG:32615`, metros), por lo
que el área de un píxel es simplemente `resolucion_m ** 2`
(`pixel_area_m2` en `src/analisis_espacial.py`): a 10 m de resolución,
100 m² por píxel. No se construye una rejilla de área equivalente
adicional porque el CRS proyectado ya da área real directamente.

### Variables de `results/tables/extension_floracion.csv`

Una fila por lago y fecha, solo para las escenas de cianobacteria ya
calculadas (22 filas, 11 por lago).

| Variable | Tipo | Descripción |
|---|---|---|
| `lago` | texto categórico | `atitlan` o `amatitlan` |
| `fecha` | fecha ISO | Fecha oficial `YYYY-MM-DD` |
| `umbral_alto_ugl` | decimal | Umbral usado (10.0) |
| `resolucion_m` | decimal | Resolución de la rejilla (heredada del manifiesto de índices) |
| `area_pixel_m2` | decimal | `resolucion_m ** 2` |
| `pixeles_validos_lago` | entero | Píxeles que pasan la máscara combinada |
| `pixeles_altos` | entero | De los anteriores, cuántos superan el umbral |
| `area_valida_m2` | decimal | `pixeles_validos_lago * area_pixel_m2` |
| `area_alta_m2` | decimal | `pixeles_altos * area_pixel_m2` |
| `porcentaje_alto` | decimal | `100 * area_alta_m2 / area_valida_m2` |
| `cobertura_valida_pct` | decimal | Heredada de `manifest_indices.csv`, sin recalcular |
| `quality_flag` | categoría | Heredado de `manifest_indices.csv` (para no ocultar cobertura parcial ni fechas atípicas) |

### Resultado en las 22 escenas

Amatitlán crece de forma marcada en las últimas fechas de la serie:
36.30 % del área válida el `2026-04-28` y 54.40 % el `2026-06-19` (las
mismas dos fechas ya marcadas como pico en el ejercicio 4), frente a
valores por debajo de 8 % en el resto de sus fechas. Atitlán se mantiene
con una extensión de valores altos mínima durante todo el período (máximo
0.10 %, la mayoría de las fechas por debajo de 0.05 %).

## Ejercicio 8.2 - zonas persistentes

### Verificación de rejilla entre fechas

Los tres índices de una misma fecha ya se exportan alineados (ejercicio
3), pero cada fecha se calcula por separado; antes de apilar las 11
fechas de un lago, `check_grid_consistency(lago)` verifica que compartan
CRS, `transform`, ancho y alto. En la corrida actual ambos lagos son
consistentes entre sus 11 fechas (no fue necesario re-alinear). Si no lo
fueran, `stack_cianobacteria_arrays` reutiliza `align_to_reference` (ya
usado en el ejercicio 3) para llevar cada fecha a la rejilla de la primera
fecha lista del lago, sin reprocesar bandas crudas.

### Denominador variable por píxel

`persistence_raster(lago, ..., min_fechas_validas=3)` calcula, por
píxel: `conteo_valido` (número de las 11 fechas en que ese píxel fue
válido: pasó SCL-agua ∩ geometría real ∩ no es `NaN`) y `proporcion_alto`
(`conteo_alto / conteo_valido`). El denominador **no es siempre 11**:
varía por nubes, sombras o el área válida de cada escena. Con menos de
`min_fechas_validas` observaciones válidas, el píxel queda `NaN` (dato
insuficiente), no en cero ni excluido silenciosamente del raster.

### Variables de los GeoTIFF de persistencia

`data/processed/analisis_espacial/<lago>/persistencia/`:

| Archivo | Contenido | Unidad |
|---|---|---|
| `proporcion_alto.tif` | Fracción de fechas válidas con cianobacteria ≥ umbral, por píxel | `fraccion_0_1` |
| `conteo_valido_fechas.tif` | Número de fechas válidas usadas en ese píxel | `conteo_de_fechas` |

### Resultado en ambos lagos

Con `min_fechas_validas = 3`: Amatitlán tiene 72.37 % de su área válida
con al menos un episodio de valor alto en el período, pero solo 0.15 % es
persistentemente alta (≥ 50 % de sus fechas válidas) — consistente con que
el aumento de cianobacteria es reciente (últimas dos fechas), no sostenido
durante todo el período. Atitlán tiene 0.17 % de su área con algún
episodio alto y apenas 0.006 % persistentemente alta. Esta comparación es
un hallazgo descriptivo, no una prueba de causa ambiental; la
interpretación completa que cruza persistencia, distribuciones y
correlaciones corresponde al análisis conjunto de los dos lagos.

## Ejercicio 6 - correlaciones con NDVI y NDWI

### Regla de emparejamiento

`src/correlaciones.py` exige que cianobacteria, NDVI y NDWI compartan CRS,
transformación, ancho y alto en cada lago-fecha. Los coeficientes se calculan
con los píxeles que pasan simultáneamente la geometría real del lago, la
máscara SCL-agua heredada del procesamiento y la condición `isfinite` de los
dos valores comparados. No se rellenan ausencias con cero.

Pearson resume asociación lineal y Spearman asociación monótona por rangos.
Se reportan ambos por fecha. Para el valor agrupado se extrae una muestra
determinística y equilibrada de hasta 10 000 pares por fecha, evitando que una
escena con mayor cobertura domine el resultado. Los valores p son
exploratorios porque la autocorrelación espacial viola la independencia ideal
entre píxeles vecinos.

### `results/tables/correlaciones_por_fecha.csv`

Una fila por combinación lago-fecha-índice-método (88 filas).

| Variable | Descripción |
|---|---|
| `lago`, `fecha` | Escena analizada |
| `indice` | `ndvi` o `ndwi` |
| `metodo` | `pearson` o `spearman` |
| `coeficiente` | Coeficiente entre -1 y 1 |
| `p_value` | Significancia exploratoria; `<1e-300` indica subdesbordamiento numérico |
| `n_pares` | Píxeles válidos simultáneamente |
| `direccion`, `magnitud` | Etiquetas interpretativas derivadas del signo y valor absoluto |
| `quality_flag_cianobacteria`, `quality_flag_indice` | Advertencias heredadas del manifiesto |
| `nota_inferencia` | Recordatorio sobre autocorrelación espacial |

### `results/tables/correlaciones_por_lago.csv`

Una fila por lago-índice-método (8 filas). Incluye `n_fechas`, total de pares,
media, mediana, mínimo y máximo de los coeficientes por fecha, fracción de
fechas positivas y el coeficiente agrupado estratificado con su tamaño de
muestra. La mediana por fecha es la referencia principal; el valor agrupado es
un contraste y no debe interpretarse aislado.

### Resultado descriptivo

Amatitlán presenta una relación cianobacteria-NDVI predominantemente positiva
(medianas por fecha: Pearson 0.67 y Spearman 0.63) y una relación con NDWI
predominantemente negativa (-0.59 y -0.51). Atitlán tiene medianas por fecha
débiles para NDVI (0.03 y 0.13) y NDWI (aproximadamente 0.00 y -0.07). El
Spearman agrupado de NDWI en Atitlán (-0.53) difiere de la evidencia por fecha,
por lo que se conserva como ejemplo de que mezclar fechas puede cambiar la
interpretación.

## Ejercicio 8.3 - distribuciones y mapas de diferencia

### Selección de fechas

Las fechas se etiquetan antes de graficar con cuatro criterios reproducibles:
`referencia_primera_fecha_completa`, `pico_temporal`, `mayor_extension` y
`fecha_comun_lagos` (`2026-04-13`). Una fecha puede satisfacer más de un
criterio. Las distribuciones usan la misma máscara común de geometría, agua y
validez de los tres índices.

### `results/tables/distribuciones_por_fecha.csv`

Una fila por lago-fecha (22 filas).

| Variable | Descripción |
|---|---|
| `lago`, `fecha` | Escena analizada |
| `n_pixeles` | Número de píxeles válidos incluidos |
| `min`, `max` | Extremos conservados en la tabla |
| `p01`, `p05`, `q25`, `mediana`, `q75`, `p95`, `p99` | Percentiles de la distribución |
| `media`, `desviacion_std` | Media y desviación estándar poblacional |
| `quality_flag` | Estado heredado del manifiesto de cianobacteria |
| `criterio_seleccion` | Uno o más criterios usados para elegir la fecha en las figuras |

Los histogramas y boxplots usan límites comunes basados en percentiles solo
para mantener legibilidad; los CSV conservan todos los valores válidos. Los
mapas de diferencia verifican rejilla exacta, calculan
`fecha_final - fecha_inicial` y emplean una escala divergente centrada en cero.

Amatitlán aumenta su mediana de 4.49 µg/L en la referencia a 10.73 µg/L en la
fecha de mayor extensión; su percentil 95 llega a 21.34 µg/L. Atitlán mantiene
medianas menores y su fecha final seleccionada (`2026-07-22`) conserva la
bandera `revisar_valores_atipicos`, por lo que la diferencia se interpreta con
cautela.

## Ejercicio 7 - comparación de lagos

### `results/tables/comparacion_lagos.csv`

Una fila por lago (2 filas). Consolida columnas ya calculadas por los
ejercicios 4 (`resumen_temporal.csv`), 8.1 (`extension_floracion.csv`), 8.2
(resumen de persistencia, ver más abajo) y 6 (`correlaciones_por_lago.csv`);
`src/comparacion_lagos.py` no vuelve a abrir raster.

| Variable | Descripción |
|---|---|
| `n_fechas_calculado` / `n_fechas_total` | Fechas sin advertencia de calidad frente al total de 11 |
| `cyano_promedio_general`, `cyano_mediana_general` | Estadísticos sobre las 11 fechas (no solo las "calculado", para no sesgar la base de comparación entre lagos) |
| `frecuencia_fechas_sobre_umbral`, `pct_fechas_sobre_umbral` | Fechas cuyo `cyano_promedio` iguala o supera `UMBRAL_CIANOBACTERIA_ALTO_UGL` |
| `porcentaje_alto_promedio`, `porcentaje_alto_maximo`, `fecha_porcentaje_alto_maximo` | De `extension_floracion.csv` |
| `pct_area_alguna_vez_alta`, `pct_area_persistente` | Copiados de `RESUMEN_PERSISTENCIA` en `config.py` (ver nota abajo) |
| `correlacion_ndvi_pearson_mediana`, `correlacion_ndwi_pearson_mediana` | De `correlaciones_por_lago.csv` |
| `tendencia_temporal` | `creciente` / `decreciente` / `estable`: compara el promedio de la primera mitad de fechas contra la segunda mitad (umbral de diferencia: 0.5 µg/L) |

`RESUMEN_PERSISTENCIA` en `config.py` guarda los dos porcentajes de
persistencia (8.2) como constantes documentadas, copiados de
`informe/secciones/08_2_zonas_persistentes.md`, porque esos raster derivados
no se versionan y `comparacion_lagos.py` no depende de reabrirlos. Si se
re-ejecuta el ejercicio 8.2, esa constante debe actualizarse a mano.

**Nota de confiabilidad:** Atitlán tiene solo 5 de 11 fechas sin advertencia
de calidad (`revisar_valores_atipicos` por la inestabilidad numérica sobre
agua profunda, ver ejercicio 3), frente a 10 de 11 en Amatitlán. Parte de la
diferencia observada entre lagos podría reflejar, en alguna medida, esa menor
confiabilidad relativa de los datos de Atitlán, no solo una diferencia
biológica real; el ejercicio 7 discute esto explícitamente en vez de
omitirlo.

## Ejercicio 8.4 - patrón estacional

### `results/tables/patron_estacional.csv`

Agrupa `resumen_temporal.csv` por lago y estación climática de Guatemala
(`MESES_ESTACION_SECA = nov-abr`, `MESES_ESTACION_LLUVIOSA = may-oct`, según
el patrón general documentado por el INSIVUMEH). Es una agrupación de
calendario, no una medición meteorológica del laboratorio.

| Variable | Descripción |
|---|---|
| `lago`, `estacion` | `seca` o `lluviosa` |
| `n_fechas` | Cuántas de las 11 fechas oficiales caen en esa estación |
| `cyano_promedio`, `cyano_mediana`, `cyano_std` | Sobre `cyano_promedio` de `resumen_temporal.csv` |
| `fechas` | Fechas incluidas, separadas por `;` |

Amatitlán solo tiene `n_fechas=1` en época lluviosa (2026-06-19, que además es
su fecha con más cianobacteria de toda la serie), así que no se puede separar
un efecto estacional de la tendencia creciente general ya documentada en el
ejercicio 4. Atitlán no muestra diferencia relevante entre estaciones (1.14 vs.
1.18 µg/L). Con 11 fechas irregulares por lago no corresponde afirmar una
estacionalidad robusta, solo describir estos indicios.


# Parte II - Machine Learning

## Ejercicio 1 - conjunto de datos tabular (`data/processed/ml/dataset_ml.parquet`)

No versionado (regenerable con `python src/dataset_ml.py construir`). Una fila
por celda agregada de 50 m (bloques de 5x5 píxeles de 10 m) dentro del
contorno real de un lago, en una fecha oficial.

| Variable | Tipo | Descripción |
|---|---|---|
| `lago`, `fecha` | texto | Identifican la escena de origen |
| `x_utm`, `y_utm` | decimal | Centroide de la celda en `EPSG:32615` (metros) |
| `lon`, `lat` | decimal | Mismo centroide reproyectado a `EPSG:4326` |
| `B03`, `B04`, `B08` | decimal | Reflectancia de superficie (0-1), promedio de la celda |
| `ndvi`, `ndwi` | decimal | Promedio de la celda |
| `cianobacteria_ugl` | decimal | Promedio de la celda (µg/L, proxy) |
| `n_pixeles_validos` | entero | 0-25, píxeles de 10 m válidos dentro de la celda |
| `frac_valida` | decimal | `n_pixeles_validos / 25` |

Una celda se conserva solo si `n_pixeles_validos >= 13` (mayoría estricta).
Se descartan a nivel de píxel de 10 m, antes de agregar: puntos fuera del
contorno real del lago, `nodata`, nubes/sombras/nieve (SCL), y valores de
NDVI/NDWI/cianobacteria fuera de su rango físicamente interpretable
(`[-1,1]` para los índices normalizados, `[0,500]` para cianobacteria).
`results/tables/inventario_dataset_ml.csv` (versionado) documenta el total
de observaciones, el desglose por lago y fecha, y el tipo y porcentaje de
faltantes de cada variable.

## Ejercicio 2 - variable respuesta (`src/respuesta.py`)

### Binarización

`cyano_alta = 1` si `cianobacteria_ugl >= UMBRAL_CIANOBACTERIA_ALTO_UGL`
(10.0 µg/L), si no `0`. Mismo umbral que el ejercicio 8.1/8.2 de la Parte I.

### Justificación del punto de corte (verificada)

- **OECD (1982).** *Eutrophication of waters: Monitoring, assessment and
  control*. OECD. Clasificación trófica por clorofila-a media anual:
  oligotrófico ≤2.5 µg/L, mesotrófico 2.5-8, **eutrófico 8-25**,
  hipereutrófico ≥25. 10 µg/L cae dentro del rango eutrófico.
- **World Health Organization. (2003).** *Guidelines for safe recreational
  water environments: Volume 1, Coastal and fresh waters*.
  https://www.who.int/publications/i/item/9241545801. Marco de niveles de
  alerta para cianobacterias por clorofila-a con dominancia de
  cianobacterias: nivel de vigilancia ~1-12 µg/L, Alert Level 1 ~12-24
  µg/L. 10 µg/L cae en el extremo superior del nivel de vigilancia, justo
  antes de Alert Level 1 (no "es" Alert Level 1, una imprecisión que tenía
  una versión anterior de este documento).

### `results/tables/distribucion_respuesta.csv`

Una fila por combinación de corte/lago-o-fecha/clase. Columnas: `corte`
(`global`, `por_lago`, `por_fecha`), `lago`, `fecha`, `cyano_alta` (0 o 1),
`n`, `pct`.

### Desbalance de clases (números reales del dataset)

| Corte | n_total | n_positivos | % positivos | negativos por positivo |
|---|---:|---:|---:|---:|
| Global | 492677 | 6365 | 1.29 % | 76.4 |
| Amatitlán | 60642 | 6358 | 10.48 % | 8.5 |
| Atitlán | 432035 | 7 | 0.0016 % | 61718 |

El 99.9 % de las observaciones positivas del dataset completo vienen de
Amatitlán. Consecuencias: accuracy global es engañosa (predecir siempre 0
da ~98.7 % de accuracy sin aprender nada); los modelos sin ajuste tienden a
sesgarse hacia la clase mayoritaria; deben usarse Precision/Recall/F1/
ROC-AUC en vez de accuracy; y un modelo entrenado solo con datos de Atitlán
casi no tiene positivos de los que aprender, lo que anticipa dificultad en
el ejercicio 7 (generalización entre lagos) del experimento "entrenar en
Atitlán, evaluar en Amatitlán".

### `VARIABLES_EXCLUIDAS_RESPUESTA` (`src/config.py`) - fuga de datos

El script CyanoLakes calcula `NDCI = (B05-B04)/(B05+B04)` y `chl` a partir
de ese NDCI; `B05` no se descargó, así que la fuga entra por `B04`.

| Variable | Razón de exclusión |
|---|---|
| `cianobacteria_ugl` | Es la variable de la que se deriva `cyano_alta` |
| `B04` | Entra directamente en el NDCI que calcula la clorofila-a |
| `ndvi` | `(B08-B04)/(B08+B04)`: usa B04, fuga indirecta |

`B03` y `B08` sí pueden usarse como predictoras: en el script de
cianobacteria solo intervienen en la máscara de agua, no en el valor
numérico de `chl`.

## Ejercicio 8 - interpretabilidad

`results/tables/importancia_variables.csv` contiene una fila por predictor del
mejor modelo. `importancia_modelo` e `importancia_modelo_normalizada` son la
importancia nativa de XGBoost; `shap_media_absoluta` y su versión normalizada
resumen la magnitud media del efecto SHAP. `correlacion_valor_shap` es Spearman
entre el valor de la variable y su contribución SHAP, y `direccion_efecto`
traduce el signo cuando la relación es suficientemente monotónica. Los valores
se calculan sobre 5,000 filas seleccionadas con
`correlaciones.deterministic_sample`.

Las figuras versionadas son `results/figures/importancia_variables.png` y
`results/figures/shap_summary.png`.

## Ejercicio 9 - probabilidades y errores espaciales

`data/processed/ml/predicciones_observaciones.parquet` es regenerable y no se
versiona. Conserva una fila por observación de la matriz final con lago, fecha,
centroide UTM, partición, respuesta, probabilidad, clase predicha y categoría de
error. El umbral de decisión es 0.50.

Los mapas agrupan la probabilidad en cuatro intervalos: muy baja `[0, 0.25)`,
baja `[0.25, 0.50)`, alta `[0.50, 0.75)` y muy alta `[0.75, 1]`. Si dos teselas
se superponen en el mismo centroide, su probabilidad se promedia para dibujar
una única celda de 50 m.

`results/tables/errores_espaciales.csv` usa solo la partición de prueba y agrupa
por lago, fecha y zona (`orilla_0_250m`, `intermedia_250_1000m` e
`interior_mas_1000m`). Reporta observaciones, positivos reales, probabilidad
media, los cuatro elementos de la matriz de confusión y tasas de error. Una tasa
sin denominador válido se escribe como `indefinido`, nunca como cero.
