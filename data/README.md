# Datos del Laboratorio 4

## `raw/`

Es la fuente recibida o descargada y no se modifica manualmente:

- `geojson/`: contiene actualmente los bbox de consulta creados con las
  coordenadas del enunciado. No son el contorno de los lagos.
- `manifest_escenas.csv`: inventario de las 22 escenas oficiales y estado de
  adquisición.
- `rasters/`: assets originales de los batch jobs de openEO. Su contenido es
  pesado, reproducible y está ignorado por Git.

Si el curso proporciona los GeoJSON originales de Atitlán y Amatitlán, deben
copiarse sin editar a `raw/geojson/`. No se debe reemplazar silenciosamente el
bbox ni presentar el rectángulo como máscara del agua.

## `processed/`

Contendrá índices y tablas generados por código a partir de `raw/`. Estos
archivos nunca sustituyen ni sobrescriben sus insumos.

## Regeneración

Consultar el flujo y los comandos en el `README.md` de la raíz del repositorio.

