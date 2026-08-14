# Laboratorio 4 - Análisis de Datos Geoespaciales

**CC3084 · Data Science · Universidad del Valle de Guatemala · Semestre II, 2026**

Análisis multitemporal de los lagos Atitlán y Amatitlán con imágenes
Sentinel-2. Esta etapa implementa los ejercicios 1 a 4: conexión con
Copernicus Data Space mediante openEO, definición reproducible de las 22
escenas oficiales, descarga limitada a los AOI y bandas necesarias, el
cálculo de NDVI, NDWI y el índice de cianobacteria, y el resumen y análisis
temporal de cianobacteria por lago y fecha.

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

- `src/analisis_temporal.py` valida `manifest_indices.csv` y reporta
  cuántas de las 22 escenas de cianobacteria ya están listas antes de
  calcular nada; ninguna fila pendiente se completa manualmente.
- Con las escenas que sí tienen raster calculado, construye
  `data/processed/tablas/resumen_temporal.csv` (promedio, mediana,
  desviación estándar, píxeles válidos y cobertura por lago y fecha).
- `notebooks/04_analisis_temporal.ipynb` grafica la serie por lago, marca
  picos con un criterio explícito (media + 1 desviación estándar de la
  propia serie) y distingue la fecha de cobertura parcial de Amatitlán del
  resto de la serie.
- Como el ejercicio 3 todavía no ha calculado cianobacteria para ninguna
  escena, el resumen temporal y las gráficas están vacíos por ahora; el
  cuaderno lo reporta explícitamente en lugar de fallar.

## Estructura

```text
.
├── data/
│   ├── raw/
│   │   ├── geojson/                 # AOI bbox de consulta en EPSG:4326
│   │   ├── rasters/                 # assets originales de openEO y cianobacteria, ignorados por Git
│   │   └── manifest_escenas.csv     # las 22 escenas oficiales
│   └── processed/
│       ├── indices/                 # GeoTIFF de NDVI, NDWI y cianobacteria
│       ├── tablas/                  # resumen_temporal.csv
│       └── manifest_indices.csv     # contrato de 66 filas hacia el ejercicio 4
├── notebooks/
│   ├── 01_02_conexion_y_descarga.ipynb
│   ├── 03_indices.ipynb
│   └── 04_analisis_temporal.ipynb
├── src/
│   ├── config.py                    # coordenadas, fechas, script de cianobacteria y config común
│   ├── adquisicion.py               # preparación, consulta y descarga openEO
│   ├── indices.py                   # NDVI, NDWI, cianobacteria y manifest_indices.csv
│   ├── analisis_temporal.py         # resumen_temporal.csv, picos y validación del manifiesto de índices
│   ├── evalscripts/                 # script de cianobacteria (original y adaptación numérica)
│   ├── raster_utils.py              # validación local de GeoTIFF
│   └── run_pipeline.py              # preparación segura de esta etapa
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

## Uso de los notebooks

Abrir Jupyter desde la raíz:

```powershell
jupyter notebook notebooks/01_02_conexion_y_descarga.ipynb
jupyter notebook notebooks/03_indices.ipynb
jupyter notebook notebooks/04_analisis_temporal.ipynb
```

Los tres notebooks se pueden ejecutar de arriba a abajo sin conexión ni
credenciales. Los dos primeros desactivan sus celdas remotas por bandera
(`EJECUTAR_...`); para autenticar, descargar o calcular cianobacteria vía
Sentinel Hub, se cambia únicamente la bandera indicada en la celda
correspondiente. Las operaciones demostrativas siempre apuntan a una sola
escena; el lote de 22 escenas se confirma aparte. El cuaderno 04 no tiene
banderas remotas: valida el manifiesto de índices y grafica lo que ya esté
calculado; si todavía no hay ninguna escena lista, lo reporta en vez de
fallar.

## Limitación geométrica actual

El repositorio no contenía los GeoJSON originales de los lagos al implementar
esta etapa. Por eso `data/raw/geojson/` contiene polígonos rectangulares
construidos con las coordenadas oficiales. Sus propiedades declaran
`geometry_role=query_bbox` e `is_lake_boundary=false`.

Estos AOI son válidos para limitar la consulta del ejercicio 2, pero **no deben
usarse como si fueran el contorno del agua** en promedios o mapas espaciales.
Cuando se incorporen los GeoJSON oficiales, deben conservarse como fuente
cruda separada y usarse para enmascarar el lago en los ejercicios posteriores.

Mientras tanto, el ejercicio 3 usa una máscara interina: la clase "agua"
(valor 6) de la banda `SCL` de Sentinel-2 L2A, dentro del bbox de consulta,
excluyendo nubes/sombras/nieve de cada fecha (ver `codebook.md`). Es una
máscara calculada por escena, más ajustada que un rectángulo fijo, pero debe
intersectarse con el GeoJSON oficial del lago en cuanto esté disponible, no
reemplazarse por él sin más.

## Datos y Git

Los AOI, manifiestos, código, notebooks y resúmenes pequeños se versionan. Los
GeoTIFF originales y los índices derivados se regeneran y están ignorados por
Git. Nunca se deben agregar `.env`, tokens, contraseñas, cachés o rutas
absolutas de una computadora.

## Referencias técnicas

- [openEO en Copernicus Data Space](https://documentation.dataspace.copernicus.eu/APIs/openEO/Python_Client/Python.html)
- [Batch jobs del cliente Python de openEO](https://open-eo.github.io/openeo-python-client/batch_jobs.html)

