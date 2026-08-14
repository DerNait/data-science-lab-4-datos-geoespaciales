# Laboratorio 4 - Análisis de Datos Geoespaciales

**CC3084 · Data Science · Universidad del Valle de Guatemala · Semestre II, 2026**

Análisis multitemporal de los lagos Atitlán y Amatitlán con imágenes
Sentinel-2. Esta primera etapa implementa los ejercicios 1 y 2: conexión con
Copernicus Data Space mediante openEO, definición reproducible de las 22
escenas oficiales y descarga limitada a los AOI y bandas necesarias.

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

## Estructura

```text
.
├── data/
│   ├── raw/
│   │   ├── geojson/                 # AOI bbox de consulta en EPSG:4326
│   │   ├── rasters/                 # assets originales de openEO, ignorados por Git
│   │   └── manifest_escenas.csv     # las 22 escenas oficiales
│   └── processed/
│       ├── indices/
│       └── tablas/
├── notebooks/
│   └── 01_02_conexion_y_descarga.ipynb
├── src/
│   ├── config.py                    # coordenadas, fechas y configuración común
│   ├── adquisicion.py               # preparación, consulta y descarga openEO
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

## Uso del notebook

Abrir Jupyter desde la raíz:

```powershell
jupyter notebook notebooks/01_02_conexion_y_descarga.ipynb
```

El notebook se puede ejecutar sin conexión porque las celdas remotas vienen
desactivadas. Para autenticar o descargar, se cambia únicamente la bandera
indicada en la celda correspondiente. La descarga demostrativa siempre apunta
a una sola escena.

## Limitación geométrica actual

El repositorio no contenía los GeoJSON originales de los lagos al implementar
esta etapa. Por eso `data/raw/geojson/` contiene polígonos rectangulares
construidos con las coordenadas oficiales. Sus propiedades declaran
`geometry_role=query_bbox` e `is_lake_boundary=false`.

Estos AOI son válidos para limitar la consulta del ejercicio 2, pero **no deben
usarse como si fueran el contorno del agua** en promedios o mapas espaciales.
Cuando se incorporen los GeoJSON oficiales, deben conservarse como fuente
cruda separada y usarse para enmascarar el lago en los ejercicios posteriores.

## Datos y Git

Los AOI, manifiestos, código, notebooks y resúmenes pequeños se versionan. Los
GeoTIFF originales y los índices derivados se regeneran y están ignorados por
Git. Nunca se deben agregar `.env`, tokens, contraseñas, cachés o rutas
absolutas de una computadora.

## Referencias técnicas

- [openEO en Copernicus Data Space](https://documentation.dataspace.copernicus.eu/APIs/openEO/Python_Client/Python.html)
- [Batch jobs del cliente Python de openEO](https://open-eo.github.io/openeo-python-client/batch_jobs.html)

