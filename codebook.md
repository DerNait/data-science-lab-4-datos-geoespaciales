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

