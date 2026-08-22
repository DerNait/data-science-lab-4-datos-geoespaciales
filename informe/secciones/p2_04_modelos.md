# Parte 2, Ejercicio 4: construcción de los modelos de Machine Learning

## ¿Qué se hizo?

Se entrenaron los tres modelos de clasificación que pide el enunciado sobre la
matriz de predictores construida en el ejercicio 3: Regresión Logística, Random
Forest y Gradient Boosting, este último con XGBoost. El objetivo de los tres es
el mismo: decidir, para cada celda de 50 metros dentro de alguno de los dos
lagos y en una fecha concreta, si tiene alta presencia de cianobacteria.

El conjunto de datos tiene 492,663 observaciones, de las cuales solo el 1.29 por
ciento supera el umbral de 10 microgramos por litro. Ese desbalance condicionó
tres decisiones que se tomaron antes de entrenar nada.

**La división se hizo estratificada.** Se separó el 70 por ciento para
entrenamiento y el 30 por ciento para prueba, conservando en ambos la misma
proporción de casos positivos. Con una división aleatoria simple, el conjunto de
prueba podía quedar con muy pocos casos de alta presencia, y cualquier métrica
calculada sobre él habría sido inestable. El resultado fueron 344,864
observaciones de entrenamiento con 4,455 positivas y 147,799 de prueba con 1,910
positivas: 1.2918 por ciento y 1.2923 por ciento respectivamente.

**Esa división quedó guardada en disco.** El enunciado pide mantener el mismo
conjunto de prueba para que la comparación entre modelos sea justa, y además los
ejercicios posteriores de validación, generalización e interpretabilidad tienen
que evaluar sobre exactamente el mismo conjunto. Por eso la partición se
persistió en un archivo, junto con el lago y la fecha de cada observación, que
son los datos que la validación espacial y la temporal necesitan para agrupar.

**Los tres modelos compensan el desbalance de forma explícita.** Sin
reponderar la clase positiva, la manera más fácil de minimizar el error es
predecir siempre ausencia, que ya acierta el 98.7 por ciento de las veces. La
Regresión Logística y el Random Forest usan pesos de clase balanceados, y el
Gradient Boosting usa el parámetro equivalente, con una razón de 76.4 negativos
por cada positivo.

## Decisiones de modelado

La Regresión Logística se montó dentro de una tubería que primero estandariza
las variables. Es necesario porque están en unidades muy distintas: la
reflectancia va de 0 a 1 y las distancias van en metros, en decenas de miles. Al
estar dentro de la tubería, la estandarización se ajusta solo con los datos de
entrenamiento de cada pliegue de validación cruzada y no filtra información.

A ese mismo modelo se le quitaron dos columnas: la que indica si la observación
es de Atitlán y la que indica si la fecha es de estación seca. Junto con sus
complementarias forman pares que siempre suman uno, y para un modelo lineal con
intercepto eso es colinealidad perfecta. Los modelos de árboles no tienen ese
problema y conservan las cuatro columnas.

## Ajuste de hiperparámetros

Se usó búsqueda aleatoria con validación cruzada estratificada de tres pliegues,
siempre sobre el conjunto de entrenamiento. El conjunto de prueba no participó
en ningún momento de la selección.

El criterio para elegir el modelo final fue F2 y no exactitud ni F1. La razón es
ambiental y se desarrolla en la sección siguiente: el error que interesa reducir
es no detectar una floración, así que la métrica de selección debe pesar el
recall por encima de la precisión. Elegir por exactitud habría premiado al
modelo que predice siempre ausencia.

Lo que se evaluó y lo que se eligió quedó registrado en la tabla
`results/tables/hiperparametros_modelos.csv`. En resumen:

| Modelo | Hiperparámetros explorados | Configuración elegida |
| --- | --- | --- |
| Regresión Logística | intensidad de regularización y algoritmo de optimización | C = 10, lbfgs |
| Random Forest | número de árboles, profundidad máxima, hojas mínimas y variables por corte | 200 árboles, profundidad 20, 5 hojas mínimas, raíz cuadrada de variables |
| Gradient Boosting | número de árboles, profundidad, tasa de aprendizaje, submuestreo de filas y de columnas | 200 árboles, profundidad 9, tasa 0.1, submuestreo 0.8 y 0.8 |

Los F2 de validación cruzada que justificaron cada elección fueron 0.696 para la
Regresión Logística, 0.942 para el Random Forest y 0.955 para el Gradient
Boosting.
