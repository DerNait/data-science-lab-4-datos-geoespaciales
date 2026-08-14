# Ejercicio 8.2: zonas del lago con cianobacteria persistente

## ¿Qué se hizo?

El ejercicio 8.1 midió qué tan grande era el área alta en cada fecha por
separado. Este ejercicio pregunta algo distinto: **¿son siempre los mismos
puntos del lago los que se ven afectados, o cambia de un lado a otro cada
vez?** Para responder, se calculó, para cada punto del lago, en qué
fracción de las fechas en que ese punto tuvo datos utilizables su
cianobacteria superó el umbral de "valor alto" (el mismo de 8.1: 10
microgramos por litro). Un punto con esa fracción cerca de 1 tuvo
cianobacteria alta casi siempre que se pudo observar; un punto cerca de 0
casi nunca la tuvo.

Un detalle importante: no todos los puntos del lago tienen la misma
cantidad de observaciones útiles, porque las nubes tapan zonas distintas
en cada fecha. Por eso la fracción de cada punto se calculó sobre el
número de fechas en que **ese punto en particular** tuvo dato (no siempre
las 11), y se exigió un mínimo de 3 fechas observadas por punto para
calcular su fracción; los puntos con menos observaciones que eso quedan
marcados como "sin datos suficientes" en vez de forzar un resultado poco
confiable.

## Lo que muestran los datos

**Amatitlán**: el 72.4 % del área del lago con datos suficientes tuvo
cianobacteria alta en **al menos una** de sus fechas observadas durante el
período. Sin embargo, solo el 0.15 % del área tuvo cianobacteria alta en
la **mitad o más** de sus fechas observadas. En otras palabras: la
floración reciente y extensa que se vio en el ejercicio 8.1 (más de la
mitad del lago el 19 de junio de 2026) afectó zonas amplias del lago, pero
todavía no se repite de forma sostenida en los mismos puntos a lo largo de
todo el período observado; es coherente con que el aumento de
cianobacteria en Amatitlán se concentra en las últimas fechas de la
serie, no en todo el año y medio analizado.

**Atitlán**: solo el 0.17 % de su área tuvo cianobacteria alta alguna vez,
y apenas el 0.006 % de forma persistente (la mitad o más de las fechas
observadas). Esto confirma, a nivel de cada punto del lago (no solo en
promedio), que Atitlán prácticamente no presentó cianobacteria por encima
del umbral de referencia durante el período analizado.

## Posible explicación (no es una conclusión definitiva)

Que la mayor parte del área "alguna vez alta" de Amatitlán no sea también
"persistentemente alta" es consistente con un evento reciente (fin de
la temporada seca/inicio de lluvias de 2026) más que con una condición
estable de todo el lago durante año y medio. No se puede concluir con
estos datos si esa tendencia va a mantenerse, disminuir o extenderse a más
puntos del lago en fechas futuras: se necesitarían más observaciones
posteriores a junio de 2026 para saberlo.

## Qué tan confiables son estos números (limitaciones)

- El período cubierto son 11 fechas irregulares por lago a lo largo de
  aproximadamente año y medio, no una serie continua; "persistente"
  significa "repetido en varias de las fechas realmente observadas", no
  "constante en el tiempo".
- Los puntos con menos de 3 fechas observadas se excluyeron del cálculo de
  fracción (no se les asignó un valor inventado); esos puntos suelen
  coincidir con zonas frecuentemente cubiertas por nubes en las imágenes
  disponibles.
- Esta comparación describe un patrón, no prueba una causa: no mide
  directamente nutrientes, corrientes, profundidad ni uso del suelo
  alrededor de cada punto del lago.

## Qué queda documentado en el repositorio

Los raster de persistencia (`proporcion_alto.tif` y
`conteo_valido_fechas.tif`, uno por lago) están en
`data/processed/analisis_espacial/<lago>/persistencia/`. Los mapas de
persistencia (dos paneles: fracción de fechas altas y número de fechas
usadas) están en `results/maps/<lago>_persistencia_cianobacteria.png`. El
cuaderno `notebooks/08_2_zonas_persistentes.ipynb` genera ambos productos
y el resumen numérico citado arriba.
