# Parte 2, Ejercicio 5: evaluación de los modelos

## ¿Qué se hizo?

Se evaluaron los tres modelos sobre el mismo conjunto de prueba de 147,799
observaciones, de las cuales 1,910 tienen alta presencia de cianobacteria. Se
calcularon exactitud, precisión, recall, F1, ROC-AUC y la matriz de confusión de
cada uno, más dos métricas adicionales: F2, por la razón ambiental que se
explica abajo, y PR-AUC, porque con solo 1.29 por ciento de positivos el ROC-AUC
se ve favorecido por la enorme cantidad de negativos fáciles y puede parecer
excelente aunque el modelo funcione mal sobre la clase que importa.

## Lo que muestran los datos

| Modelo | Exactitud | Precisión | Recall | F1 | F2 | ROC-AUC | PR-AUC |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Regresión Logística | 0.972 | 0.316 | 0.984 | 0.479 | 0.692 | 0.997 | 0.824 |
| Random Forest | 0.997 | 0.839 | 0.971 | 0.900 | 0.942 | 1.000 | 0.979 |
| Gradient Boosting | 0.998 | 0.898 | 0.976 | 0.936 | 0.959 | 1.000 | 0.988 |

Lo primero que salta a la vista es que la exactitud no sirve para comparar: los
tres modelos superan el 97 por ciento simplemente porque el 98.7 por ciento de
las celdas es negativo. Un modelo que predijera siempre ausencia obtendría 98.7
por ciento y sería completamente inútil.

La Regresión Logística consigue el recall más alto de los tres, 0.984, pero a un
costo enorme en precisión: marca 4,058 celdas como alta presencia cuando no lo
son. Los dos modelos de árboles conservan casi el mismo recall con muchísima más
precisión. El **Gradient Boosting es el mejor modelo**: gana en casi todos los
criterios, y en particular en F2, que es la métrica de comparación elegida.

## Los dos errores desde el contexto ambiental

Un **falso positivo** es marcar alta presencia donde no la hay. Su costo es
operativo: se moviliza un muestreo de campo innecesario o se emite una
advertencia que después no se sostiene. Si se repite mucho, erosiona la confianza
en el sistema de alerta, pero no genera exposición de nadie.

Un **falso negativo** es no detectar una zona que sí tiene alta presencia. Su
costo es de salud pública: una floración capaz de producir cianotoxinas queda sin
alerta, y esa agua se usa para recreación, pesca, riego y abastecimiento. El
umbral de 10 microgramos por litro que define la variable respuesta es
precisamente el Alert Level 1 de la OMS, el nivel a partir del cual se recomienda
vigilancia activa e información al público.

Los dos errores no son simétricos. En un sistema de monitoreo de riesgo
sanitario, el costo de no advertir supera al de advertir de más. **El error que
importa reducir es el falso negativo.**

De ahí se sigue la elección de métrica. Ni la exactitud ni F1 son adecuadas: la
primera está dominada por los negativos y la segunda pesa igual la precisión y el
recall. La métrica correcta es **F2**, que pesa el recall cuatro veces más que la
precisión. Es la que se usó para ajustar los hiperparámetros y la que se usa aquí
para declarar un ganador.

Traducido a consecuencias concretas sobre el conjunto de prueba:

| Modelo | Zonas altas no detectadas | Porcentaje sin detectar | Inspecciones innecesarias por zona detectada |
| --- | --- | --- | --- |
| Regresión Logística | 31 | 1.62 % | 2.16 |
| Random Forest | 55 | 2.88 % | 0.19 |
| Gradient Boosting | 46 | 2.41 % | 0.11 |

La Regresión Logística deja escapar menos zonas, 31 frente a 46, pero cuesta 2.16
inspecciones innecesarias por cada zona correctamente detectada, contra 0.11 del
Gradient Boosting: casi veinte veces más trabajo de campo desperdiciado. Para una
herramienta de apoyo al monitoreo, esa diferencia decide: el Gradient Boosting
ofrece prácticamente el mismo nivel de protección a un costo operativo mucho
menor.

## Un diagnóstico sobre de dónde viene el desempeño

Las cifras anteriores son muy altas, así que antes de darlas por buenas se
comprobó que el modelo no estuviera tomando un atajo.

Amatitlán tiene 10.48 por ciento de celdas positivas y Atitlán 0.0016 por ciento,
siete de 432 mil. Con esa asimetría, saber en qué lago está una celda es casi
saber la respuesta. Y el modelo tiene cuatro formas de saberlo: las dos columnas
que identifican el lago y, de manera implícita, las dos coordenadas, porque los
dos lagos ocupan rangos de coordenadas que no se solapan y un solo corte los
separa.

Se reentrenó cada modelo sin esas cuatro columnas, conservando sus
hiperparámetros. Los resultados están en
`results/tables/diagnostico_identidad_lago.csv`. Los dos modelos de árboles
conservan casi todo su desempeño: el F2 del Gradient Boosting baja de 0.959 a
0.944. La Regresión Logística es la que más dependía de la ubicación, y su PR-AUC
cae de 0.824 a 0.546.

La conclusión es que la capacidad predictiva de los modelos de árboles viene de
la firma espectral y de las variables derivadas, no de un atajo geográfico. Un
detalle metodológico que conviene señalar: hay que quitar las cuatro columnas a
la vez. Retirar solo las que nombran el lago no mide nada, porque el modelo se
apoya en la coordenada este, que separa los dos lagos igual de bien, y el
desempeño no se mueve.

## Advertencia sobre estas cifras

La división en entrenamiento y prueba es aleatoria, y dos celdas de 50 metros
contiguas de la misma fecha son casi el mismo píxel. Eso significa que muchas
observaciones del conjunto de prueba tienen una vecina casi idéntica en el de
entrenamiento, y que estas métricas son con toda probabilidad optimistas.

Medir cuánto se inflan es exactamente el propósito de la validación espacial del
ejercicio siguiente, y las cifras de esta sección deben leerse como el punto de
comparación contra el que se contrastan esos resultados, no como una estimación
del desempeño en zonas nuevas.
