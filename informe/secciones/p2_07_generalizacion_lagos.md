# Parte 2, Ejercicio 7: generalización entre lagos

## ¿Qué se hizo?

Se probó si un modelo entrenado con los datos de un lago sirve para
predecir alta presencia de cianobacteria en el otro. Dos experimentos
cruzados, con los tres modelos:

- **Experimento A**: entrenar con Atitlán, evaluar con Amatitlán.
- **Experimento B**: entrenar con Amatitlán, evaluar con Atitlán.

## Un conjunto de predictores más chico, por necesidad

Antes de correr los experimentos hubo que quitar cuatro columnas:
`lago_amatitlan`, `lago_atitlan`, `x_utm` e `y_utm`. Son las mismas cuatro
que ya identificó el ejercicio de evaluación como `COLUMNAS_IDENTIDAD_LAGO`.
Los dos lagos ocupan rangos de coordenadas UTM que no se solapan en
absoluto, así que dejar `x_utm`/`y_utm` no mide generalización entre lagos:
mide si el modelo memorizó en qué rango de coordenadas vio positivos, y el
conjunto de prueba completo de un lago cae fuera de ese rango por
construcción. Con esas cuatro columnas fuera, el modelo solo puede apoyarse
en la firma espectral (`B03`, `B08`, `ndwi`, `ratio_B03_B08`), en variables
temporales, y en las dos distancias relativas al propio contorno del lago
(`dist_orilla_m`, `dist_centroide_m`), que sí tienen el mismo significado
en cualquiera de los dos lagos.

## Los dos experimentos salieron mal, y ese es el resultado

| Experimento | Positivos de entrenamiento | Positivos de prueba | Recall | Precisión | F2 | ROC-AUC |
| --- | --- | --- | --- | --- | --- | --- |
| A: Atitlán → Amatitlán (Regresión Logística) | 7 | 6,358 | 0.000 | 0.000 | 0.000 | 0.859 |
| A: Atitlán → Amatitlán (Random Forest) | 7 | 6,358 | 0.000 | 0.000 | 0.000 | 0.601 |
| A: Atitlán → Amatitlán (Gradient Boosting) | 7 | 6,358 | 0.000 | 0.000 | 0.000 | 0.841 |
| B: Amatitlán → Atitlán (Regresión Logística) | 6,358 | 7 | 1.000 | 0.00007 | 0.0003 | 0.917 |
| B: Amatitlán → Atitlán (Random Forest) | 6,358 | 7 | 1.000 | 0.00022 | 0.0011 | 0.971 |
| B: Amatitlán → Atitlán (Gradient Boosting) | 6,358 | 7 | 1.000 | 0.00062 | 0.0031 | 0.987 |

Ninguno de los dos experimentos produce un modelo útil, pero fallan de
formas opuestas:

**Experimento A** entrena con solo 7 observaciones positivas, las únicas
que tiene Atitlán en el conjunto de datos completo. Con tan poco ejemplo
de lo que es "alta presencia", el modelo aprende un umbral de decisión
demasiado exigente: al evaluarlo contra Amatitlán, no marca ni una sola de
las 6,358 celdas realmente positivas como positiva. El recall es
literalmente cero en los tres modelos. Es interesante notar que el
ROC-AUC no es igual de malo (0.60 a 0.86, según el modelo): las
probabilidades que asigna el modelo sí ordenan razonablemente bien las
celdas de Amatitlán de menor a mayor riesgo, pero el punto de corte
aprendido en Atitlán queda tan alto que ninguna celda de Amatitlán llega a
cruzarlo. El modelo tiene algo de señal útil, pero el umbral que trae no
sirve en el otro lago.

**Experimento B** es el espejo. Entrenado con los 6,358 positivos de
Amatitlán, el modelo detecta las 7 celdas positivas de Atitlán sin
excepción: recall de 1.0 en los tres modelos. El costo es una inundación
de falsos positivos: entre 11,211 (Gradient Boosting) y 103,835 (Regresión
Logística) celdas de Atitlán quedan marcadas como alta presencia sin
serlo, sobre un total de 432,021 observaciones de prueba. La precisión cae
a un rango de 0.007 a 0.06 por ciento. El modelo aprendió que "alta
presencia" se parece a los niveles de reflectancia típicos de Amatitlán, y
aplica ese criterio sin ajustar a la escala completamente distinta de
Atitlán, donde prácticamente todo queda por encima de ese umbral.

## Comparación contra el caso de ambos lagos mezclados

Para que la comparación sea justa hay que usar el mismo conjunto reducido
de predictores en los dos casos. La tabla de diagnóstico del ejercicio de
evaluación (`results/tables/diagnostico_identidad_lago.csv`) ya entrenó y
evaluó los tres modelos sin esas mismas cuatro columnas, pero sobre la
partición aleatoria 70/30 que mezcla observaciones de los dos lagos en
entrenamiento y en prueba:

| Modelo | F2 (ambos lagos mezclados, sin identidad de lago) | F2 (generalización entre lagos) |
| --- | --- | --- |
| Regresión Logística | 0.593 | 0.000 |
| Random Forest | 0.926 | 0.000 / 0.001 |
| Gradient Boosting | 0.944 | 0.000 / 0.003 |

Cuando el modelo ve observaciones de los dos lagos durante el
entrenamiento, aunque sea sin saber explícitamente a cuál pertenece cada
una, el desempeño se mantiene alto. En cuanto el entrenamiento se limita a
un solo lago, el desempeño se desploma a valores casi nulos. La diferencia
no está en si el modelo conoce la etiqueta del lago: está en si alguna vez
vio ejemplos representativos del rango de condiciones del lago que
después tiene que predecir.

## ¿Generaliza un modelo entrenado en un lago al otro?

No, con los datos de este laboratorio. Los dos experimentos muestran que
la capacidad de un modelo entrenado en un lago para predecir en el otro es
prácticamente nula, aunque el ROC-AUC del experimento B sugiera que hay
algo de estructura espectral compartida (las probabilidades sí ordenan
razonablemente, el problema es la calibración del umbral, no la ausencia
total de señal).

Amatitlán y Atitlán son sistemas muy distintos, con causas documentadas
por sus propias autoridades de manejo de cuenca:

- **Profundidad y volumen**. Atitlán es un lago volcánico, uno de los más
  profundos de Centroamérica; Amatitlán es comparativamente playo. Un lago
  profundo con mucho volumen diluye los nutrientes que le entran; uno
  playo los concentra cerca de la superficie, donde las cianobacterias los
  aprovechan. Eso se traduce en una firma espectral de fondo muy distinta
  entre los dos lagos, incluso en observaciones sin ninguna floración.
- **Presión urbana y aguas residuales**. La cuenca de Amatitlán está
  dentro del área metropolitana de la Ciudad de Guatemala y recibe desde
  hace décadas una carga importante de aguas residuales e industriales; su
  autoridad de cuenca (AMSA) documenta un problema crónico de
  eutrofización. La cuenca de Atitlán, con autoridad AMSCLAE, tiene
  comparativamente menor densidad urbana y menor carga histórica de aguas
  residuales sin tratar. El rango completo de reflectancia que ve el
  modelo durante el entrenamiento en cada lago refleja esa diferencia de
  presión ambiental de fondo.
- **Escasez extrema de ejemplos positivos en Atitlán**. Con solo 7 celdas
  positivas en todo el período, cualquier modelo entrenado ahí aprende de
  una muestra demasiado pequeña para capturar cómo se ve una floración
  real, más allá de esos 7 casos puntuales.

La consecuencia práctica es clara: un modelo de este tipo no se puede
entrenar en un lago y desplegar en otro sin recalibrar, como mínimo, el
punto de corte de decisión a la escala de reflectancia propia del lago de
destino. Lo que sí parece transferirse, según el ROC-AUC del experimento
B, es el orden relativo de riesgo dentro de cada lago, aunque no se
disponga de suficientes datos de Atitlán para confirmarlo con la misma
solidez que en Amatitlán.
