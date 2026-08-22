# Parte 2, Ejercicio 6: validación espacial y temporal

## ¿Qué se hizo?

Los tres modelos ya elegidos en el ejercicio anterior se reentrenaron, con
exactamente los mismos hiperparámetros, bajo dos esquemas de evaluación
distintos de la partición aleatoria 70/30: agrupando por bloque espacial y
encadenando por fecha. El objetivo no fue buscar un modelo mejor, sino medir
cuánto cambia el desempeño ya medido cuando el conjunto de prueba deja de
tener observaciones casi idénticas a las de entrenamiento.

## Cuadrícula de bloques espaciales

Antes de fijar un tamaño de bloque se comprobó si un kilómetro alcanzaba.
Con esa medida, Amatitlán queda en 35 bloques, 34 de ellos con algún
positivo y una mediana de 1,123 observaciones por bloque; Atitlán queda en
168 bloques, 3 con algún positivo y una mediana de 3,378 observaciones por
bloque. La diferencia entre lagos no es casualidad: son 60,642 observaciones
contra 432,035, así que el mismo tamaño de bloque produce una malla mucho más
fina, en número de observaciones por bloque, sobre el lago más grande.

| Lago | Tamaño de bloque | Bloques totales | Bloques con algún positivo | Obs. por bloque (mediana) |
| --- | --- | --- | --- | --- |
| Amatitlán | 500 m | 95 | 90 | 685 |
| Atitlán | 1000 m | 168 | 3 | 3,378 |

Para Amatitlán se evaluó también la cuadrícula de 1 km del enunciado, y se
prefirió 500 m: con 1 km los 35 bloques dejan un margen más estrecho para
repartir en varios pliegues de validación cruzada agrupada, y a 500 m casi
todos los bloques (90 de 95) siguen conteniendo algún positivo, así que no
se pierde cobertura por refinar la cuadrícula. Atitlán se dejó en 1 km,
porque su problema no es de resolución: solo 3 de sus 168 bloques
concentran los 7 positivos que tiene en total. Refinar la cuadrícula ahí no
agrega positivos donde no los hay, solo fragmenta más un problema que ya es
de escasez absoluta, no de tamaño de celda.

La figura de bloques de cada lago (`results/maps/amatitlan_bloques_espaciales.png`
y `results/maps/atitlan_bloques_espaciales.png`) muestra la cuadrícula sobre
el contorno real del lago, coloreando cada observación según si su bloque
contiene o no algún caso de alta presencia. En Amatitlán casi todo el lago
queda en rojo: la alta presencia está repartida por buena parte del
espejo de agua. En Atitlán solo tres manchas puntuales, dos en el extremo
suroeste y una en el extremo sureste, concentran toda la señal positiva
del lago.

## Validación espacial con GroupKFold

Cada observación quedó asignada a exactamente un bloque, y la validación
cruzada se hizo agrupando por ese bloque (`GroupKFold` de cinco pliegues,
sobre los bloques de ambos lagos juntos): ninguna observación de un mismo
bloque se reparte entre entrenamiento y prueba dentro de un pliegue. Los
tres modelos se reentrenaron con exactamente los mismos hiperparámetros que
ya eligió el ejercicio de construcción de modelos.

| Modelo | F2 (70/30 aleatorio) | F2 (espacial, promedio de 5 pliegues) | Diferencia |
| --- | --- | --- | --- |
| Regresión Logística | 0.692 | 0.692 | ≈ 0 |
| Random Forest | 0.941 | 0.910 | −0.031 |
| Gradient Boosting | 0.958 | 0.925 | −0.033 |

El desempeño baja en los dos modelos de árboles, y se mantiene igual en la
Regresión Logística. La caída es moderada pero real: entre 3 y 4 puntos de
F2 para los dos mejores modelos. La explicación es la que anticipa el
enunciado: en la partición aleatoria, dos celdas de 50 metros contiguas de
la misma fecha son casi el mismo píxel, así que el conjunto de prueba
aleatorio casi siempre tiene una vecina casi idéntica en el de
entrenamiento. Agrupar por bloque de 500 m o 1 km elimina esa fuga de
información entre vecinos, y la estimación que queda es más honesta,
aunque más baja. La Regresión Logística, al ser el modelo con menos
capacidad de memorizar patrones locales finos, es la que menos se ve
afectada por esa fuga en primer lugar.

## Validación temporal

La sección de ejercicios no describe esta parte, pero la rúbrica la puntúa
de forma explícita dentro de "validación geoespacial y temporal", así que
se implementó de todas formas. Se probaron dos estrategias, ambas
agrupando por fecha en vez de por observación individual:

- **Encadenamiento hacia adelante**: se entrena con todas las fechas
  anteriores a una fecha de prueba, y se evalúa sobre esa fecha, avanzando
  fecha por fecha a través del calendario.
- **Dejar una fecha fuera**: se entrena con las demás 19 fechas y se
  evalúa sobre la que queda fuera, una vez por cada una de las 20 fechas
  distintas del conjunto de datos.

| Modelo | F2 (70/30 aleatorio) | F2 (encadenado) | F2 (deja una fecha fuera) |
| --- | --- | --- | --- |
| Regresión Logística | 0.692 | 0.387 | 0.257 |
| Random Forest | 0.941 | 0.247 | 0.264 |
| Gradient Boosting | 0.958 | 0.321 | 0.364 |

La caída aquí es mucho más severa que en la validación espacial: el F2 del
Gradient Boosting pasa de 0.958 a un rango de 0.32 a 0.36 según la
estrategia, y el Random Forest, el segundo mejor modelo bajo el esquema
aleatorio, es el que más sufre bajo encadenamiento. La razón está en cómo
se distribuyen los positivos en el tiempo: el 56.3 por ciento de los casos
de alta presencia de Amatitlán caen en una sola fecha (2026-06-19) y el
34.6 por ciento en otra (2026-04-28). Un modelo que nunca vio esas dos
fechas en su historial de entrenamiento no tiene de dónde aprender el
patrón que las distingue, y un modelo evaluado sobre una fecha distinta a
esas dos tiene poco que predecir de todas formas. La validación temporal
expone algo que la espacial no: el problema no es solo de vecindad
geográfica, es que la señal de alta presencia está concentrada en muy
pocos momentos del calendario, y generalizar de un momento a otro es
mucho más difícil que generalizar de un lugar a otro cercano.

### Pliegues indefinidos

De los 117 pliegues temporales calculados (3 modelos × 39 combinaciones de
fecha y estrategia), 54 quedaron con Recall, Precisión, F1, F2, ROC-AUC y
PR-AUC marcados explícitamente como **indefinido**, no como cero. Esto
ocurre en dos situaciones distintas, y las dos se reportan igual de
explícitas en `results/tables/metricas_validacion_temporal.csv`:

- El conjunto de **prueba** de esa fecha no tiene ningún caso positivo
  (varias fechas de Amatitlán y casi todas las de Atitlán tienen cero
  positivos), así que Recall y las métricas que dependen de él no se
  pueden calcular.
- El conjunto de **entrenamiento** todavía no tiene ningún caso positivo,
  algo que solo pasa al principio del encadenamiento hacia adelante: las
  primeras tres fechas del calendario (2025-01-18, 2025-01-28, 2025-04-13)
  no traen ningún positivo entre las tres, así que no hay con qué ajustar
  un clasificador binario todavía. Esos pliegues se dejan registrados con
  su conteo real de observaciones de prueba, no se descartan en silencio.

Forzar estos casos a cero habría sido engañoso: un cero de Recall se lee
como "el modelo falló en detectar los positivos", cuando en realidad no
había ningún positivo que detectar, o ningún positivo del que aprender.

## Conclusión de esta sección

Las dos validaciones coinciden en que la partición aleatoria 70/30 es
optimista, pero no en la misma magnitud. La validación espacial rebaja el
F2 del mejor modelo en unos 3 puntos porcentuales: un ajuste moderado, que
sigue dejando a los modelos de árboles con un desempeño alto sobre celdas
geográficamente nuevas. La validación temporal lo rebaja mucho más, a
menos de la mitad: la capacidad de generalizar a un momento del calendario
distinto es, con los datos de este laboratorio, bastante más limitada que
la de generalizar a un lugar distinto dentro del mismo período. Cualquier
afirmación sobre qué tan bien funcionaría este modelo en producción debe
apoyarse en las cifras de validación espacial y temporal, no en las del
70/30 aleatorio del ejercicio anterior, que sirven como punto de
comparación pero sobrestiman el desempeño real.
