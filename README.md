# Laboratorio 4 - Análisis de Datos Geoespaciales

**CC3084 · Data Science · Universidad del Valle de Guatemala · Semestre II, 2026**

Análisis multitemporal de los lagos Atitlán y Amatitlán con imágenes
Sentinel-2. El repositorio implementa la adquisición de las 22 escenas
oficiales, los índices de cianobacteria, NDVI y NDWI, el análisis temporal y
espacial, correlaciones, extensión, persistencia y comparación de
distribuciones. Todos los productos derivados conservan reglas reproducibles
de alineación, máscara y control de calidad.

## Estado de los ejercicios 1 y 2

- Las 22 combinaciones lago-fecha están centralizadas y validadas.
- Los metadatos oficiales de satélite y nubosidad están en el manifiesto.
- Se generaron AOI de consulta a partir de las cajas del enunciado.
- La conexión usa el backend federado oficial de Copernicus Data Space y la
  colección `SENTINEL2_L2A`.
- Las bandas iniciales son `B03`, `B04`, `B08` y `SCL`. Las primeras tres
  permiten NDWI/NDVI; `SCL` se conserva para control de nubes, sombras y agua.
- La descarga se ejecuta como un batch job por lago-fecha y nunca sobrescribe
  un producto crudo existente.
- La autenticación OIDC y las descargas deben ejecutarse con la cuenta personal
  de Copernicus; no se almacenan usuarios, contraseñas ni tokens.

## Estado del ejercicio 3

- Se identificó y documentó el script de cianobacteria del catálogo de
  Sentinel Hub (`CyanoLakes Chlorophyll-a L1C (NDCI)`, ver `codebook.md`),
  entre varios candidatos disponibles para Sentinel-2.
- El índice de cianobacteria se pide ya calculado a la Process API de
  Sentinel Hub / Copernicus Data Space sobre Sentinel-2 **L1C** (el producto
  para el que está calibrada su fórmula), no se reproduce localmente sobre
  L2A.
- NDVI y NDWI se calculan localmente con las bandas L2A ya descargadas
  (`B04`/`B08` y `B03`/`B08`), enmascarados con la clase agua de `SCL`
  mientras no exista el GeoJSON oficial del contorno del lago.
- Los tres índices de una fecha se exportan alineados a la misma rejilla, en
  GeoTIFF de una sola banda `float32`.
- `data/processed/manifest_indices.csv` es el contrato de 66 filas (22
  escenas x 3 índices) que consume el ejercicio 4.

## Estado del ejercicio 4

- Las 22 escenas oficiales de cianobacteria están calculadas
  (`manifest_indices.csv` sin ninguna fila en `pendiente_calculo`).
- `src/analisis_temporal.py` valida ese manifiesto y construye
  `data/processed/tablas/resumen_temporal.csv` (promedio, mediana,
  desviación estándar, píxeles válidos y cobertura por lago y fecha) leyendo
  únicamente los raster ya exportados; ninguna fila se completa a mano.
- `notebooks/04_analisis_temporal.ipynb` grafica la serie por lago, marca
  picos con un criterio explícito (media + 1 desviación estándar de las
  fechas de cobertura completa de la propia serie), compara ambos lagos en
  un mismo eje y distingue la fecha de cobertura parcial de Amatitlán del
  resto de la serie.
- Amatitlán muestra un aumento marcado en las dos últimas fechas
  (28-abr-2026 y 19-jun-2026, marcadas como pico); Atitlán se mantiene en un
  rango mucho más bajo durante toda la serie. La interpretación completa,
  con lo observado, una posible explicación ambiental y las limitaciones
  por separado, está en la sección 8 del cuaderno.

## Estado del ejercicio 5

- El contorno real de ambos lagos ya se obtuvo de OpenStreetMap (Overpass
  API) y quedó cacheado en `data/raw/geojson/lago_<lago>_boundary.geojson`
  (Atitlán ≈ 124.70 km², Amatitlán ≈ 15.02 km², ver `codebook.md`).
- `src/analisis_espacial.py` intersecta esa geometría real con la máscara
  SCL-agua que ya produjo el ejercicio 3, sobre los raster ya exportados
  (no reprocesa bandas crudas).
- `notebooks/05_analisis_espacial.ipynb` genera los 22 mapas individuales
  de cianobacteria, un panel comparativo por lago y uno entre lagos (misma
  escala de color fija), un mapa interactivo por lago (Folium) y una
  comparación norte/sur de concentración; todo queda en `results/maps/` y
  `results/tables/metadata_mapas.csv`.

## Estado del ejercicio 8.1 y 8.2

- El umbral de "valor alto" de cianobacteria (10 µg/L, extremo superior del
  nivel de vigilancia de la OMS, antes de Alert Level 1) está fijado en `src/config.py`
  (`UMBRAL_CIANOBACTERIA_ALTO_UGL`), documentado en `codebook.md`.
- `notebooks/08_1_extension_floracion.ipynb` calcula, para las 22 escenas,
  qué porcentaje del área válida del lago supera ese umbral y lo grafica
  en el tiempo (`results/tables/extension_floracion.csv`,
  `results/figures/<lago>_extension_floracion.png`).
- `notebooks/08_2_zonas_persistentes.ipynb` calcula, por píxel, la
  proporción de fechas válidas por encima del umbral (denominador variable
  por píxel) y exporta los raster de persistencia en
  `data/processed/analisis_espacial/<lago>/persistencia/`.

## Estado del ejercicio 6 y 8.3

- Los 66 GeoTIFF requeridos están completos y alineados: 22 escenas por los
  tres índices, en `EPSG:32615` y resolución de 10 m.
- `src/correlaciones.py` valida las rejillas, calcula Pearson y Spearman por
  lago-fecha y construye un resumen agrupado con muestreo equilibrado.
- `notebooks/06_correlaciones.ipynb` conserva la tabla comparativa, las
  gráficas de coeficientes y cuatro diagramas hexbin.
- `notebooks/08_3_distribuciones.ipynb` compara fechas elegidas por reglas
  explícitas, resume percentiles y genera mapas de diferencia
  `fecha_final - fecha_inicial`.
- Las tablas están en `results/tables/`, las figuras en `results/figures/` y
  los mapas de diferencia en `results/maps/`.

## Estado del ejercicio 7, 8.4 y 8.5

- `src/comparacion_lagos.py` consolida en `results/tables/comparacion_lagos.csv`
  lo que ya calcularon los ejercicios 4, 5, 6, 8.1 y 8.2 (promedio temporal,
  frecuencia sobre el umbral, extensión, persistencia y correlación mediana
  con NDVI/NDWI) en una sola fila por lago; no vuelve a abrir raster.
- Amatitlán promedia ~6.29 µg/L frente a ~1.15 µg/L de Atitlán (más de 5x),
  con tendencia creciente frente a estable; ambos lagos comparten el mismo
  umbral de "valor alto" (10 µg/L) fijado en el ejercicio 5.
- `results/tables/patron_estacional.csv` (`notebooks/08_4_patron_estacional.ipynb`)
  agrupa las 11 fechas de cada lago en seca/lluviosa; Atitlán no muestra
  diferencia relevante y Amatitlán solo tiene una fecha de época lluviosa
  (`n=1`), así que no se afirma una estacionalidad robusta.
- `notebooks/07_comparacion_lagos.ipynb` y `notebooks/08_5_interpretacion_global.ipynb`
  separan explícitamente hallazgos sólidos, indicios y limitaciones, y citan
  contexto documentado (autoridades de cuenca AMSA/AMSCLAE, profundidad de
  cada lago) sin presentarlo como causa demostrada por los datos del
  laboratorio.

## Estado de la Parte 2

- La tabla base reúne 492,677 celdas de 50 m; la matriz final conserva
  492,663 filas y 17 predictores después de excluir 14 cocientes B03/B08
  indefinidos.
- Se entrenaron y evaluaron Regresión Logística, Random Forest y Gradient
  Boosting sobre una partición estratificada común. Gradient Boosting fue el
  mejor según F2 (0.958).
- La validación espacial por bloques, la validación temporal y los experimentos
  entre lagos están documentados en los notebooks 14 y 15 y en
  `results/tables/`.
- `src/interpretabilidad.py` produce importancia global y SHAP sobre una muestra
  determinística de 5,000 filas.
- `src/mapas_predictivos.py` calcula una probabilidad para cada observación,
  reconstruye la rejilla de 50 m y genera un mapa comparativo por lago junto con
  el diagnóstico espacial de errores.
## Estructura

```text
.
├── data/
│   ├── raw/
│   │   ├── geojson/                 # AOI bbox + contorno real (OSM) de cada lago, EPSG:4326
│   │   ├── rasters/                 # assets originales de openEO y cianobacteria, ignorados por Git
│   │   └── manifest_escenas.csv     # las 22 escenas oficiales
│   └── processed/
│       ├── indices/                 # GeoTIFF de NDVI, NDWI y cianobacteria
│       ├── analisis_espacial/       # GeoTIFF de persistencia (proporción alta, conteo de fechas)
│       ├── tablas/                  # resumen_temporal.csv
│       └── manifest_indices.csv     # contrato de 66 filas hacia el ejercicio 4
├── notebooks/
│   ├── 01_02_conexion_y_descarga.ipynb
│   ├── 03_indices.ipynb
│   ├── 04_analisis_temporal.ipynb
│   ├── 05_analisis_espacial.ipynb
│   ├── 06_correlaciones.ipynb
│   ├── 07_comparacion_lagos.ipynb
│   ├── 08_1_extension_floracion.ipynb
│   ├── 08_2_zonas_persistentes.ipynb
│   ├── 08_3_distribuciones.ipynb
│   ├── 08_4_patron_estacional.ipynb
│   ├── 08_5_interpretacion_global.ipynb
│   ├── 09_dataset_ml.ipynb ... 15_generalizacion_lagos.ipynb
│   ├── 16_interpretabilidad.ipynb
│   └── 17_mapas_predictivos.ipynb
├── results/
│   ├── maps/                        # mapas espaciales, persistencia y diferencias temporales
│   ├── figures/                     # series, correlaciones y distribuciones
│   └── tables/                      # resúmenes espaciales, correlaciones, distribuciones y comparación
├── src/
│   ├── config.py                    # coordenadas, fechas, script de cianobacteria y config común
│   ├── adquisicion.py               # preparación, consulta y descarga openEO
│   ├── indices.py                   # NDVI, NDWI, cianobacteria y manifest_indices.csv
│   ├── analisis_temporal.py         # resumen_temporal.csv, picos y validación del manifiesto de índices
│   ├── analisis_espacial.py         # contorno real, mapas, extensión de floración y persistencia
│   ├── correlaciones.py             # correlaciones, distribuciones y mapas de diferencia
│   ├── comparacion_lagos.py         # tabla comparativa Atitlán vs. Amatitlán y patrón estacional
│   ├── dataset_ml.py, respuesta.py y features.py
│   ├── modelos.py, evaluacion.py y validacion.py
│   ├── interpretabilidad.py          # importancia global y SHAP reproducible
│   ├── mapas_predictivos.py          # probabilidades, mapas y errores espaciales
│   ├── evalscripts/                 # script de cianobacteria (original y adaptación numérica)
│   ├── raster_utils.py              # validación local de GeoTIFF
│   └── run_pipeline.py              # preparación segura de esta etapa
├── informe/secciones/
├── tests/
├── codebook.md
├── requirements.txt
└── README.md
```

## Preparar el entorno

Desde la raíz del repositorio:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

En macOS, Linux o WSL, la activación equivalente es:

```bash
source .venv/bin/activate
```

No es necesario guardar credenciales en `.env`. La autenticación de openEO
utiliza OIDC y solicita iniciar sesión con Copernicus cuando se ejecuta una
operación remota.

## Flujo reproducible

### 1. Preparar y validar sin conexión

```powershell
python src/run_pipeline.py
python src/adquisicion.py validate
```

Estos comandos no autentican, no descargan y no crean batch jobs. Verifican
coordenadas, las 11 fechas por lago, duplicados, GeoJSON y manifiesto.

### 2. Inspeccionar el plan de consulta

Una sola escena:

```powershell
python src/adquisicion.py plan --lago amatitlan --fecha 2025-01-28
```

Las 22 escenas:

```powershell
python src/adquisicion.py plan
```

Cada fecha se consulta como un intervalo de un día: desde la fecha oficial
inclusive hasta el día siguiente. No se aplica un filtro que cambie las fechas
oficiales por otras escenas.

### 3. Comprobar conexión y colección

```powershell
python src/adquisicion.py check-connection
```

El cliente abrirá o mostrará el flujo OIDC. La comprobación confirma que
`SENTINEL2_L2A` y las bandas mínimas están disponibles en el backend.

### 4. Descargar primero una escena de prueba

```powershell
python src/adquisicion.py download --lago amatitlan --fecha 2025-01-28
```

El resultado se guarda en:

```text
data/raw/rasters/amatitlan/2025-01-28/
```

Después de descargar, el script abre los GeoTIFF, valida CRS y dimensiones,
calcula cobertura numérica válida y actualiza la fila correspondiente del
manifiesto.

### 5. Descargar el lote oficial

Solo después de revisar la escena de prueba:

```powershell
python src/adquisicion.py download --confirm-batch
```

La confirmación es obligatoria porque el comando crea hasta 22 batch jobs y
puede consumir créditos o recursos de la cuenta.

También se puede procesar un lago completo:

```powershell
python src/adquisicion.py download --lago atitlan --confirm-batch
```

## Flujo reproducible del ejercicio 3

No es necesario guardar credenciales de Sentinel Hub si solo se calculan
NDVI/NDWI localmente. Para pedir el índice de cianobacteria a la Process API
se necesita un OAuth client de Copernicus Data Space (Dashboard > User
Settings > OAuth clients) y sus valores en `.env` como
`SENTINEL_HUB_CLIENT_ID` / `SENTINEL_HUB_CLIENT_SECRET`.
El proyecto carga automáticamente el archivo local `.env` mediante
`python-dotenv`; las variables exportadas explícitamente en la terminal tienen
prioridad y no son sobrescritas.

### 1. Preparar y validar el manifiesto de índices

```powershell
python src/indices.py prepare
python src/indices.py validate
```

Crea/valida `data/processed/manifest_indices.csv` con 66 filas en estado
`pendiente_calculo`. No requiere raster descargados ni credenciales.

### 2. Pedir el raster crudo de cianobacteria de una escena

Requiere `SENTINEL_HUB_CLIENT_ID`/`SENTINEL_HUB_CLIENT_SECRET`:

```powershell
python src/indices.py fetch-cyano --lago amatitlan --fecha 2025-01-28
```

Guarda el resultado sin modificar en
`data/raw/rasters/amatitlan/2025-01-28/cyano_ndci_l1c.tif` y nunca
sobrescribe un archivo existente.

### 3. Calcular los tres índices de una escena de prueba

Requiere tener ya descargadas las bandas B03, B04, B08 y SCL de esa fecha.
NDVI y NDWI **no dependen de credenciales de Sentinel Hub**: se calculan y
exportan siempre que existan esas bandas. Si el raster crudo de
cianobacteria no está disponible y no se pasa `--fetch-cyano-remote`, esa
escena simplemente se omite para cianobacteria (su fila queda
`pendiente_calculo`) sin bloquear NDVI/NDWI:

```powershell
python src/indices.py compute --lago amatitlan --fecha 2025-01-28 --fetch-cyano-remote
```

Exporta `data/processed/indices/amatitlan/2025-01-28/{ndvi,ndwi,cianobacteria}.tif`
(cianobacteria solo si hay credenciales o raster crudo disponible) y
actualiza las filas correspondientes de `manifest_indices.csv`.

### 4. Calcular el lote de 22 escenas

Solo después de revisar la escena de prueba. Se puede correr sin
`--fetch-cyano-remote` para dejar listos los 44 GeoTIFF de NDVI/NDWI de una
vez mientras se consiguen las credenciales de Sentinel Hub, y repetirlo
después con `--fetch-cyano-remote` para completar cianobacteria:

```powershell
python src/indices.py compute --confirm-batch --fetch-cyano-remote
```

## Flujo reproducible del ejercicio 4

No requiere credenciales: solo lee `manifest_indices.csv` y los GeoTIFF de
cianobacteria que el ejercicio 3 ya haya exportado.

### 1. Ver cuántas escenas de cianobacteria están listas

```powershell
python src/analisis_temporal.py report
```

Cuenta, sobre las 22 escenas oficiales, cuántas tienen ya un raster de
cianobacteria calculado y lista las fechas pendientes.

### 2. Validar el manifiesto de índices

```powershell
python src/analisis_temporal.py validate
```

Valida estructura y, para las filas ya listas, que declaren unidad, dtype,
píxeles válidos y cobertura. No corrige nada: si falta un campo, indica
que debe corregirse en el cálculo de índices.

### 3. Construir el resumen temporal

```powershell
python src/analisis_temporal.py build
```

Escribe `data/processed/tablas/resumen_temporal.csv` con las escenas de
cianobacteria ya calculadas (promedio, mediana, desviación estándar,
píxeles válidos y cobertura por lago y fecha). Si todavía no hay ninguna
escena calculada, no escribe nada y lo indica explícitamente.

## Flujo reproducible del ejercicio 5, 8.1 y 8.2

No requiere credenciales de Sentinel Hub: solo lee `manifest_indices.csv`
y los GeoTIFF de cianobacteria ya exportados. Pedir el contorno real del
lago sí requiere conexión a Overpass (una sola vez por lago; el resultado
se cachea).

### 1. Pedir el contorno real de un lago (una sola vez)

```powershell
python src/analisis_espacial.py fetch-boundary --lago atitlan
python src/analisis_espacial.py fetch-boundary --lago amatitlan
```

Guarda el contorno real (OpenStreetMap) en
`data/raw/geojson/lago_<lago>_boundary.geojson` y nunca sobrescribe uno
existente. Si Overpass no responde o no encuentra el lago, falla con un
error explícito en vez de usar el bbox como sustituto.

### 2. Verificar consistencia de rejilla entre fechas

```powershell
python src/analisis_espacial.py check-grid
```

### 3. Extensión de valores altos (ejercicio 8.1)

```powershell
python src/analisis_espacial.py extension
```

Escribe `results/tables/extension_floracion.csv` con el porcentaje de área
válida por encima de `UMBRAL_CIANOBACTERIA_ALTO_UGL` para cada una de las
22 escenas.

### 4. Zonas persistentes (ejercicio 8.2)

```powershell
python src/analisis_espacial.py persistence --lago atitlan
python src/analisis_espacial.py persistence --lago amatitlan
```

Exporta los GeoTIFF de persistencia en
`data/processed/analisis_espacial/<lago>/persistencia/`.

### 5. Mapas y notebooks

```powershell
jupyter notebook notebooks/05_analisis_espacial.ipynb
jupyter notebook notebooks/08_1_extension_floracion.ipynb
jupyter notebook notebooks/08_2_zonas_persistentes.ipynb
```

El cuaderno 05 genera los 22 mapas individuales, los paneles comparativos,
el mapa interactivo (Folium) y `results/tables/metadata_mapas.csv`. Los
cuadernos 8.1 y 8.2 leen directamente los productos ya calculados por el
ejercicio 3 y por el propio ejercicio 5 (contorno real cacheado); no
descargan ni recalculan índices.

## Flujo reproducible del ejercicio 6 y 8.3

Estos análisis trabajan sin conexión una vez que existen los 66 GeoTIFF
alineados de cianobacteria, NDVI y NDWI (22 fechas por 3 índices). Primero se
puede comprobar el insumo sin generar resultados:

```powershell
python src/correlaciones.py validate
```

Para calcular las correlaciones, las distribuciones y todas sus figuras:

```powershell
python src/correlaciones.py all
```

El ejercicio 6 calcula Pearson y Spearman por lago, fecha e índice usando
solamente pares de píxeles válidos simultáneamente dentro de la geometría real
del lago. El resumen agrupado equilibra las fechas con un máximo común de
pares, para evitar que una escena con más píxeles domine el resultado.

El ejercicio 8.3 selecciona las fechas mediante reglas reproducibles
(referencia, pico temporal, mayor extensión y fecha común), compara sus
distribuciones con límites gráficos comunes y genera mapas de diferencia con
la convención `fecha_final - fecha_inicial`. No modifica los raster de entrada.

Los productos quedan en `results/tables/`, `results/figures/` y
`results/maps/`. La metodología y el diccionario de cada tabla están en
`codebook.md`.

## Uso de los notebooks

Abrir Jupyter desde la raíz:

```powershell
jupyter notebook notebooks/01_02_conexion_y_descarga.ipynb
jupyter notebook notebooks/03_indices.ipynb
jupyter notebook notebooks/04_analisis_temporal.ipynb
jupyter notebook notebooks/05_analisis_espacial.ipynb
jupyter notebook notebooks/06_correlaciones.ipynb
jupyter notebook notebooks/08_1_extension_floracion.ipynb
jupyter notebook notebooks/08_2_zonas_persistentes.ipynb
jupyter notebook notebooks/08_3_distribuciones.ipynb
```

Los notebooks se pueden ejecutar de arriba a abajo sin conexión ni
credenciales, salvo la sección de contorno real del ejercicio 5
(`EJECUTAR_DESCARGA_CONTORNO`, en `False` por defecto porque el contorno
ya está cacheado). Los dos primeros notebooks desactivan sus celdas
remotas por bandera (`EJECUTAR_...`); para autenticar, descargar o
calcular cianobacteria vía Sentinel Hub, se cambia únicamente la bandera
indicada en la celda correspondiente. Las operaciones demostrativas
siempre apuntan a una sola escena; el lote de 22 escenas se confirma
aparte. El cuaderno 04 no tiene banderas remotas: valida el manifiesto de
índices y grafica lo que ya esté calculado; si todavía no hay ninguna
escena lista, lo reporta en vez de fallar. Los cuadernos 8.1 y 8.2 tampoco
requieren red: leen directamente los productos ya calculados. Los cuadernos
06 y 8.3 tampoco usan credenciales ni red: validan y documentan los resultados
calculados a partir de los 66 GeoTIFF locales.

## Geometría real de los lagos

El contorno real de cada lago (no solo su caja de consulta) se obtuvo de
OpenStreetMap vía Overpass API y está cacheado, sin sobrescribir el bbox
original, en:

- `data/raw/geojson/aoi_<lago>_bbox.geojson` — caja rectangular de consulta
  (`geometry_role=query_bbox`, `is_lake_boundary=false`), usada para
  limitar la descarga del ejercicio 2. **No representa el contorno del
  agua.**
- `data/raw/geojson/lago_<lago>_boundary.geojson` — contorno real del
  lago (`geometry_role=lake_boundary`, `is_lake_boundary=true`), obtenido
  de OpenStreetMap (licencia ODbL, ver `codebook.md` para la consulta
  exacta y la fecha).

El ejercicio 3 sigue usando su máscara por escena: la clase "agua" (valor
6) de la banda `SCL` de Sentinel-2 L2A, excluyendo nubes/sombras/nieve de
cada fecha (ver `codebook.md`). Esa máscara **no se reemplazó ni se
reprocesó**: el ejercicio 5 (`src/analisis_espacial.py`,
`combined_valid_mask`) la **intersecta** con el contorno real sobre los
raster ya exportados, de modo que un píxel cuenta como válido solo si pasa
ambos filtros. Esta intersección es la que usan los mapas del ejercicio 5
y los cálculos de extensión (8.1) y persistencia (8.2); el manifiesto de
índices y los raster de NDVI/NDWI/cianobacteria del ejercicio 3 quedan sin
cambios.

## Datos y Git

Los AOI, el contorno real de los lagos, manifiestos, código, notebooks y
resúmenes/tablas pequeñas se versionan. Los GeoTIFF originales, los
índices derivados y los raster de persistencia se regeneran y están
ignorados por Git. Nunca se deben agregar `.env`, tokens, contraseñas,
cachés o rutas absolutas de una computadora.

## Referencias técnicas

- [openEO en Copernicus Data Space](https://documentation.dataspace.copernicus.eu/APIs/openEO/Python_Client/Python.html)
- [Batch jobs del cliente Python de openEO](https://open-eo.github.io/openeo-python-client/batch_jobs.html)

