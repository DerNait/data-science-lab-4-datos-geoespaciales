# Parte 2, Ejercicio 9: generación de mapas predictivos

## ¿Qué se hizo?

Con el Gradient Boosting ya elegido como mejor modelo, se calculó la probabilidad de alta
presencia para cada observación del conjunto de datos y se reconstruyeron esas
probabilidades espacialmente, usando el centroide UTM (`x_utm`, `y_utm`) de cada celda de
50 m. Se generó un mapa de probabilidad por lago —`results/maps/amatitlan_probabilidad_cianobacteria.png`
y `results/maps/atitlan_probabilidad_cianobacteria.png`—, con una escala de cuatro bandas
que distingue probabilidad **muy baja** `[0, 0.25)`, **baja** `[0.25, 0.50)`, **alta**
`[0.50, 0.75)` y **muy alta** `[0.75, 1]`; el umbral de decisión para la matriz de confusión
espacial es 0.50, el mismo punto de corte convencional usado en el resto del laboratorio.

Para el análisis de errores se dividió el área de cada lago en tres zonas según su distancia
a la orilla —`orilla_0_250m`, `intermedia_250_1000m` e `interior_mas_1000m`—, reutilizando
`dist_orilla_m` del ejercicio 3, y se calculó, solo sobre la partición de prueba, la matriz
de confusión y las tasas de error de cada combinación lago-fecha-zona
(`results/tables/errores_espaciales.csv`).

## Comparación con los mapas de cianobacteria de la Parte I

Los mapas de probabilidad (`results/maps/amatitlan_probabilidad_cianobacteria.png`,
`results/maps/atitlan_probabilidad_cianobacteria.png`) reproducen, en general, la misma
geografía del problema que ya mostraban los mapas de cianobacteria medida de la Parte I
(ejercicio 5): comparados contra `results/maps/amatitlan_2026-04-28_cianobacteria.png` y
`results/maps/amatitlan_2026-06-19_cianobacteria.png` —las dos fechas de mayor floración—,
buena parte del lago aparece en las bandas alta y muy alta en ambos pares de mapas;
comparados contra `results/maps/atitlan_comparativo_cianobacteria.png`, casi la totalidad de
Atitlán se mantiene en la banda muy baja en las 11 fechas medidas y en el mapa de
probabilidad, con solo un puñado de celdas puntuales elevándose por encima de eso.

## Aciertos, falsos positivos y falsos negativos por zona

La distribución de las tres zonas es muy distinta entre lagos: en Amatitlán, un lago
pequeño, casi todas las celdas de prueba caen en `orilla_0_250m` o `intermedia_250_1000m` —la
zona interior tiene apenas 1 a 3 observaciones por fecha—, mientras que en Atitlán, un lago
grande y profundo, la mayoría de las celdas caen en `interior_mas_1000m` (entre 1,987 y 7,928
por fecha).

En las dos fechas de mayor floración de Amatitlán, el modelo mantiene una detección alta en
ambas zonas costeras, pero **la tasa de falsos positivos es sistemáticamente mayor en la
orilla que en la zona intermedia**:

| Fecha | Zona | Positivos reales | Falsos positivos | Tasa de falsos positivos |
| --- | --- | ---: | ---: | ---: |
| 2026-04-28 | orilla (0–250 m) | 297 | 21 | 4.30 % |
| 2026-04-28 | intermedia (250–1000 m) | 229 | 7 | 1.33 % |
| 2026-06-19 | orilla (0–250 m) | 426 | 58 | 13.74 % |
| 2026-06-19 | intermedia (250–1000 m) | 499 | 15 | 5.36 % |

Es un patrón consistente en casi todas las fechas de Amatitlán con señal positiva, no solo
en las dos más extremas: la franja más cercana a la orilla es también la que concentra más
falsos positivos, no menos. Una explicación plausible es que la orilla es la zona de
transición más abrupta entre condiciones de agua clara y condiciones de floración —el propio
`ndwi_vecindad_3x3` cambia más rápido ahí—, así que es donde el modelo tiene el margen de
decisión más estrecho y comete más errores de sobre-predicción, aun cuando su probabilidad
media en esa zona ya es alta.

En Atitlán, el patrón es distinto por escasez de datos: en 10 de sus 11 fechas no hay ningún
falso positivo en ninguna zona (probabilidad media predicha por debajo de 0.001 en casi
todas las combinaciones lago-fecha-zona), y la única excepción es una sola celda mal
clasificada en la orilla el 2025-12-29. El modelo no tiene prácticamente ninguna dificultad
sistemática en Atitlán simplemente porque casi no hay señal positiva contra la cual
equivocarse.

## ¿Hay regiones con dificultad sistemática?

Sí: la franja costera de Amatitlán (`orilla_0_250m`) es la región donde el modelo comete
sistemáticamente más falsos positivos, precisamente la zona que, según el ejercicio 8,
concentra la mayor probabilidad de alta presencia real. Esto es coherente con el mecanismo
ambiental esperado —la orilla es donde ocurren las floraciones— y con una limitación
razonable del modelo: es más fácil equivocarse por exceso de alerta en una zona
genuinamente propensa a la floración que en una zona interior donde casi nunca ocurre nada.
No se observa lo contrario (una región interior con floraciones sistemáticamente no
detectadas) en los datos disponibles.
