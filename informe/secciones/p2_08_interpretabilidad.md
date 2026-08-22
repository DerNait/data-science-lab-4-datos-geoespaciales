# Parte 2, Ejercicio 8: interpretación y explicabilidad del modelo

## ¿Qué se hizo?

Para el mejor modelo (Gradient Boosting) se calculó su importancia de variables nativa
(ganancia acumulada de XGBoost) y se complementó con SHAP (SHapley Additive exPlanations)
sobre una muestra determinística y reproducible de 5,000 filas —calcular SHAP exactamente
sobre las 492,663 observaciones del conjunto completo es computacionalmente inviable, y una
muestra de este tamaño ya estabiliza el promedio de contribuciones—.

**Tabla y figuras de esta sección** (`src/interpretabilidad.py`, notebook
`16_interpretabilidad.ipynb`): `results/tables/importancia_variables.csv` (una fila por
predictor, con las dos lecturas de importancia y la dirección de efecto);
`results/figures/importancia_variables.png` (gráfico de barras de importancia global);
`results/figures/shap_summary.png` (SHAP Summary Plot).

## Dos lecturas que no coinciden, y por qué hay que contrastarlas

La importancia nativa de XGBoost está dominada casi por completo por las columnas de
identidad de lago: `lago_amatitlan` concentra el 55.4 % de la ganancia total del modelo y
`lago_atitlan` otro 37.0 %, es decir, más del 92 % de la importancia "oficial" del modelo
recae en solo dos columnas que únicamente le dicen en qué lago está la celda.

Si esa fuera la única lectura, la conclusión sería que el modelo no aprendió nada sobre
cianobacteria, solo aprendió a copiar la tasa base de cada lago. Pero el ejercicio 5 ya
mostró, con el diagnóstico de ablación (`results/tables/diagnostico_identidad_lago.csv`),
que quitar esas cuatro columnas de identidad/posición apenas baja el F2 del Gradient
Boosting de 0.958 a 0.947. Esa es la señal de que la ganancia nativa está sobrevalorando la
identidad de lago —probablemente porque es la variable que produce las divisiones más
"limpias" en los primeros árboles, no necesariamente la más informativa sobre cianobacteria
por sí sola— y de que hay que mirar SHAP, calculado sobre las predicciones reales, para una
lectura más matizada.

## Importancia global según SHAP

Ordenando por la magnitud media absoluta del efecto SHAP (normalizada), las variables con
mayor influencia sobre la predicción del Gradient Boosting son:

| Variable | Magnitud SHAP (normalizada) | Dirección del efecto |
| --- | ---: | --- |
| `B03` | 0.209 | Efecto no monótono o débil |
| `lago_amatitlan` | 0.140 | Valores altos aumentan la predicción |
| `y_utm` | 0.121 | Valores altos disminuyen la predicción |
| `B08` | 0.110 | Valores altos aumentan la predicción |
| `x_utm` | 0.085 | Valores altos aumentan la predicción |
| `ndwi_vecindad_3x3` | 0.076 | Valores altos disminuyen la predicción |
| `dist_orilla_m` | 0.052 | Valores altos disminuyen la predicción |
| `dia_anio_cos` | 0.040 | Valores altos disminuyen la predicción |
| `ndwi` | 0.031 | Valores altos disminuyen la predicción |
| `dist_centroide_m` | 0.031 | Valores altos aumentan la predicción |

Con SHAP, `B03` —la banda verde, no la identidad de lago— es la variable con mayor magnitud
de efecto, aunque su relación con la predicción no es monótona (su correlación de Spearman
con el valor SHAP es prácticamente nula, 0.034): probablemente porque `B03` participa en
combinación con `B08` y `ndwi` de formas no lineales que un solo coeficiente de correlación
no resume.

## Interpretación ambiental de las variables más influyentes

- **`B08` (infrarrojo cercano)** tiene una correlación fuerte y positiva con su efecto SHAP
  (0.897): reflectancia alta en el NIR empuja la predicción hacia alta presencia, consistente
  con que el infrarrojo cercano es sensible a materia orgánica y biomasa algal en la
  superficie del agua.
- **`ndwi` y `ndwi_vecindad_3x3`** tienen correlación negativa con su efecto SHAP (−0.69 y
  −0.63): valores altos de NDWI (agua ópticamente más limpia, tanto en la celda como en su
  vecindad) empujan la predicción hacia ausencia, y viceversa. Esto es consistente con la
  relación NDWI-cianobacteria inversa que ya se había medido en el ejercicio 6 de la Parte I.
- **`dist_orilla_m`** tiene correlación negativa (−0.71): mientras más lejos está una celda
  de la orilla, menor la probabilidad de alta presencia. Esto coincide con el mecanismo
  ambiental esperado —las floraciones se acumulan cerca de la costa, donde hay menos mezcla y
  más aporte de nutrientes— y confirma que la variable de ingeniería de características
  construida en el ejercicio 3 captura una señal real, no solo ruido geográfico.
- **`lago_amatitlan`** (0.57 de correlación positiva) y **`lago_atitlan`** (−0.57, la misma
  relación con signo opuesto) confirman lo ya visto: pertenecer a Amatitlán empuja hacia alta
  presencia, simplemente porque ahí es donde está casi toda la señal positiva del conjunto de
  datos.
- **`estacion_lluviosa`** (correlación positiva de 0.78, aunque con magnitud SHAP baja,
  0.005) es consistente con la hipótesis ya planteada en el ejercicio 8.4 de la Parte I —más
  lluvia puede arrastrar más nutrientes hacia el lago—, aunque su peso en el modelo es
  marginal comparado con las variables espectrales y espaciales.

## No basta con mostrar las gráficas

El patrón que emerge de SHAP, leído en conjunto, es coherente con lo que ya se sabía del
comportamiento físico de una floración de cianobacterias: reflectancia alta en el
infrarrojo cercano, reflectancia de agua "menos limpia" (NDWI bajo) tanto en la celda como
en su entorno inmediato, y proximidad a la orilla, son las condiciones que el modelo asocia
con alta presencia. Que la variable dominante en la ganancia nativa (identidad de lago) no
sea la dominante en SHAP, y que quitarla apenas cambie el desempeño, refuerza que el modelo
sí está aprendiendo señal espectral y espacial genuina, y no solo memorizando en qué lago
está parado —aunque, como ya mostró el ejercicio 7, esa señal genuina todavía no alcanza
para generalizar de un lago al otro sin recalibración.
