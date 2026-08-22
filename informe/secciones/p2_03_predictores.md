# Parte 2, Ejercicio 3: selección y construcción de variables predictoras

## Conjunto de predictores

Se definieron 17 predictores, agrupados en cinco categorías. La tabla completa, con la
justificación de cada uno, está en `results/tables/diccionario_predictores.csv`
(notebook `11_predictores.ipynb`):

| Categoría | Variables | Qué aportan |
| --- | --- | --- |
| Bandas espectrales | `B03`, `B08` | Reflectancia de superficie en verde e infrarrojo cercano; el agua con más material en suspensión o algas refleja distinto en ambas bandas, y el NIR en particular es muy sensible a materia orgánica superficial |
| Índice | `ndwi` | `(B03−B08)/(B03+B08)`; una cianobacteria alta suele bajar el NDWI porque la superficie deja de comportarse ópticamente como agua limpia |
| Características espaciales | `x_utm`, `y_utm`, `dist_orilla_m`, `dist_centroide_m` | Posición absoluta dentro del lago y distancia relativa a la orilla o al centro; las floraciones tienden a acumularse cerca de la costa, donde hay menos mezcla y más aporte de nutrientes, mientras que el centro es zona más profunda y mezclada |
| Características temporales | `mes`, `dia_anio_sin`, `dia_anio_cos`, `estacion_lluviosa`, `estacion_seca` | Aproximan variación estacional de temperatura y lluvia; el día del año se codifica con seno y coseno para que el modelo lo trate como un ciclo continuo y no como un número entero con un salto artificial entre el 31 de diciembre y el 1 de enero |
| Calidad y derivadas | `frac_valida`, `ratio_B03_B08`, `ndwi_vecindad_3x3` | `frac_valida` es la fracción de píxeles de 10 m válidos en la celda (no deriva de la respuesta); `ratio_B03_B08` es un contraste verde/infrarrojo distinto de cada banda por separado; `ndwi_vecindad_3x3` promedia el NDWI de las celdas vecinas para capturar contexto espacial local en vez de tratar cada celda como independiente |
| Identidad de lago | `lago_amatitlan`, `lago_atitlan` | Codificación one-hot del lago; permite al modelo separar el comportamiento base de cada lago, dado que difieren en profundidad y presión urbana |

## Ingeniería de características

Tres de estos predictores no vienen directamente de los rásteres de la Parte I y se
construyeron específicamente para este laboratorio:

- **`ratio_B03_B08`**: cociente entre las bandas verde e infrarrojo cercano. Es sensible al
  material particulado y a la biomasa superficial de una forma que ninguna de las dos bandas
  por separado captura, porque normaliza la reflectancia relativa entre ambas en vez de
  depender del nivel absoluto de cada una.
- **`dist_orilla_m` y `dist_centroide_m`**: distancia en metros del centroide de cada celda
  al borde del contorno real del lago (mismo polígono de OpenStreetMap del ejercicio 5 de la
  Parte I) y a su centroide, respectivamente. Se calculan una sola vez por lago y se
  reutilizan para todas las fechas, ya que la geometría del lago no cambia entre escenas.
- **`ndwi_vecindad_3x3`**: promedio del NDWI en la vecindad de 3×3 celdas de 50 m alrededor
  de cada celda, en la misma fecha. Le da al modelo una noción de textura y contexto local
  —si toda una zona alrededor de la celda ya se ve como agua clara o no— en vez de evaluar
  cada celda de forma aislada.

Ninguna de estas tres variables interviene en el cálculo del índice de cianobacteria ni de
`cyano_alta`, así que no introducen el mismo riesgo de fuga que se descartó en el ejercicio
2 para `B04` y `ndvi`.

**Tabla de esta sección**: `results/tables/diccionario_predictores.csv` (las 17 variables,
con tipo, descripción y justificación completas). No se generó una figura dedicada para
este ejercicio; la matriz de correlación de `eda_matriz_correlacion.png` (ejercicio 1) ya
cubre las cinco variables numéricas de origen antes de la ingeniería de características.
