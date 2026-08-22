# Parte 2, Ejercicio 1: preparación de los datos para Machine Learning

## ¿Qué se hizo?

Se partió de los rásteres de 10 metros de resolución que ya existían de la Parte I —B03,
B04, B08, NDVI, NDWI y el índice de cianobacteria, para las 22 escenas oficiales— y se
agregaron en celdas de 50 metros: cada celda resume un bloque de 5×5 píxeles de 10 m
mediante su promedio. Agregar a 50 m reduce el ruido píxel a píxel propio de un sensor de
10 m, y además deja el conjunto de datos en una escala compatible con la cuadrícula de
validación espacial de 500 m a 1 km que pide el ejercicio 6: cada bloque espacial terminó
conteniendo un número manejable de celdas en vez de cientos de miles de píxeles sueltos.

Antes de agregar, se descartaron a nivel de píxel de 10 m: los puntos fuera del contorno
real del lago (el mismo polígono de OpenStreetMap que ya se validó en el ejercicio 5 de la
Parte I), los píxeles `NoData`, los píxeles marcados como nube, sombra o nieve por la banda
de clasificación de escena (SCL) de Sentinel-2, y cualquier valor de NDVI, NDWI o
cianobacteria fuera de su rango físicamente interpretable (`[-1, 1]` para los índices
normalizados, `[0, 500] µg/L` para cianobacteria). Una celda de 50 m solo se conserva si al
menos 13 de sus 25 píxeles de 10 m pasaron todos esos filtros —mayoría estricta—; con menos
de 13 píxeles válidos, el promedio de la celda dejaría de ser representativo de un área
comparable al resto del conjunto de datos.

## Lo que muestran los datos

El conjunto de datos final tiene **492,677 observaciones**: 60,642 en Amatitlán y 432,035
en Atitlán. La diferencia de casi un orden de magnitud no es una decisión de muestreo, es
geometría: Atitlán tiene un área real de ~124.7 km² frente a los ~15.0 km² de Amatitlán (ver
ejercicio 5 de la Parte I), así que a la misma resolución de 50 m produce muchas más celdas.

Por fecha, Amatitlán se mantiene notablemente estable —entre 5,163 y 5,630 observaciones en
sus 11 fechas—, lo cual es consistente con un lago pequeño donde casi toda el área válida se
recupera en casi cualquier escena. Atitlán, en cambio, varía mucho más: de 8,994
observaciones en la fecha más afectada por nubes (2025-01-18) a 48,683 en la fecha más
completa (2025-04-13). Esta variación reproduce, a nivel de conteo de celdas, la misma
inestabilidad de cobertura que el ejercicio 3 de la Parte I ya había detectado en Atitlán
por la reflectancia casi nula de sus aguas profundas y claras.

El conjunto de datos tiene 14 columnas: `lago` y `fecha` (texto), `x_utm`/`y_utm`/`lon`/`lat`
(coordenadas, `float64`), `B03`/`B04`/`B08`/`ndvi`/`ndwi`/`cianobacteria_ugl` (`float32`),
`n_pixeles_validos` (`int16`) y `frac_valida` (`float32`). **Ninguna columna tiene valores
faltantes (0.0 % en las 14)**: por construcción, cualquier celda con datos insuficientes ya
quedó excluida antes de llegar a esta tabla, así que no hace falta imputar nada más adelante.

El análisis exploratorio de estas variables (notebook `10_variable_respuesta.ipynb`, sección
del ejercicio 1.5) confirma el mismo patrón ya visto en la Parte I a nivel de escena
completa: `cianobacteria_ugl` tiene una distribución muy asimétrica, con la gran mayoría de
las celdas en valores bajos y una cola larga de valores altos concentrada casi por completo
en Amatitlán y en sus fechas más recientes; `B03` y `B08` muestran rangos de reflectancia
claramente distintos entre los dos lagos, lo cual anticipa por qué, más adelante, la
identidad del lago resulta tan fácil de inferir a partir de las bandas espectrales.

## Decisiones de preparación y limpieza

- **Agregar a 50 m en vez de trabajar con los píxeles de 10 m originales** evita que el
  conjunto de datos tenga más de 12 millones de filas y sincroniza la unidad de observación
  con la escala de la validación espacial posterior.
- **El umbral de 13/25 píxeles válidos** (mayoría estricta) se fijó para no descartar toda
  celda que toque el borde del lago o una nube pequeña, pero sí excluir celdas donde el
  promedio estaría dominado por muy pocos píxeles.
- **Los mismos filtros de calidad de la Parte I (contorno real, SCL, rango físico) se
  heredan sin relajarse**, precisamente para que esta tabla sea consistente con los mapas y
  estadísticas ya validados en la primera parte del laboratorio.

Estos productos quedan documentados en `results/tables/inventario_dataset_ml.csv`
(conteos totales, por lago, por fecha, tipos y porcentaje de faltantes) y se generan con
`python src/dataset_ml.py construir` / el notebook `09_dataset_ml.ipynb`.

**Figuras del análisis exploratorio** (`src/eda.py`, notebook `10_variable_respuesta.ipynb`):

| Archivo | Contenido |
| --- | --- |
| `results/figures/eda_histogramas.png` | Histogramas de B03, B08, NDVI, NDWI y cianobacteria_ugl (esta última en escala logarítmica por su fuerte asimetría) |
| `results/figures/eda_matriz_correlacion.png` | Matriz de correlación de Pearson entre esas cinco variables numéricas del dataset |
| `results/figures/eda_boxplot_cianobacteria_por_lago.png` | Diagrama de caja de cianobacteria_ugl, Amatitlán vs. Atitlán, todas las fechas |
| `results/figures/eda_boxplot_cianobacteria_por_fecha_amatitlan.png` | Diagrama de caja de cianobacteria_ugl por fecha, Amatitlán |
| `results/figures/eda_boxplot_cianobacteria_por_fecha_atitlan.png` | Diagrama de caja de cianobacteria_ugl por fecha, Atitlán |
| `results/figures/eda_dispersion_geografica_amatitlan.png` | Dispersión geográfica (lon/lat) de cianobacteria_ugl, todas las fechas, Amatitlán |
| `results/figures/eda_dispersion_geografica_atitlan.png` | Dispersión geográfica (lon/lat) de cianobacteria_ugl, todas las fechas, Atitlán |
