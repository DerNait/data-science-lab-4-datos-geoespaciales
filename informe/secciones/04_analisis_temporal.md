# Ejercicio 4: evolución de la cianobacteria a lo largo del tiempo

## ¿Qué se hizo?

Con el índice de cianobacteria ya calculado para las 22 fechas oficiales
(11 en el lago de Amatitlán y 11 en el lago de Atitlán, ver ejercicio 3),
se resumió cada fecha en un solo número por lago: el promedio de
cianobacteria sobre los píxeles de agua válidos de esa imagen. Con esos 22
promedios se armó una línea de tiempo por lago para ver si la
cianobacteria sube, baja o se mantiene estable.

Antes de mirar los números se definió una regla fija para decidir qué
fecha cuenta como un "pico": una fecha es pico si su promedio supera en
más de una desviación estándar el promedio normal de ese mismo lago. Esa
regla se decidió antes de ver los resultados, precisamente para no elegir
los picos "a ojo".

## Lo que muestran los datos

**Amatitlán** se mantiene en un nivel relativamente estable durante casi
toda la serie (entre 4.3 y 6.7 en la mayoría de las fechas, de enero de
2025 a marzo de 2026), pero sube de forma marcada en las dos últimas
fechas disponibles: el 28 de abril de 2026 y, más aún, el 19 de junio de
2026. Esas dos fechas son justamente las que la regla de arriba identifica
como picos.

**Atitlán** se mantiene en valores mucho más bajos que Amatitlán durante
toda la serie (entre 0.27 y 2.13), sin mostrar una tendencia clara de
subida o bajada sostenida. Solo una fecha, el 13 de abril de 2026, queda
marcada como pico, y por un margen pequeño.

En pocas palabras: en el período analizado, Amatitlán muestra señales de
un aumento reciente de cianobacteria que Atitlán no muestra.

## Posible explicación (no es una conclusión definitiva)

El aumento en Amatitlán ocurre en abril y junio, que coincide con el
inicio de la temporada de lluvias en Guatemala. Más lluvia puede arrastrar
más nutrientes hacia el lago desde su cuenca, lo que favorece el
crecimiento de cianobacterias. Amatitlán además es un lago con
antecedentes ya conocidos de problemas de este tipo. Esta es una hipótesis
razonable, no algo que estos datos por sí solos puedan comprobar: no se
midió lluvia, temperatura ni nutrientes directamente.

Los valores bajos y estables de Atitlán son consistentes con ser un lago
más profundo y con menor entrada de nutrientes, pero tampoco se puede
afirmar esto como una causa comprobada con la información disponible aquí.

## Qué tan confiables son estos números (limitaciones)

- Cada lago tiene solo 11 fechas, y no están espaciadas de forma regular
  en el tiempo. No es una serie de tiempo completa: no se le aplicó ni se
  le debe aplicar ningún método que asuma estacionalidad o tendencias
  estadísticamente sólidas. Lo que se presenta aquí es una exploración
  descriptiva, no una predicción.
- La fecha del 7 de febrero de 2026 en Amatitlán tiene menos de la mitad
  de la imagen con datos utilizables (~57 % de cobertura válida), una
  advertencia que viene desde el enunciado del laboratorio. Ese punto se
  mantiene marcado en la tabla y en la gráfica, y no participó en calcular
  el umbral que define los picos, para no distorsionar la comparación.
- En Atitlán, 6 de las 11 fechas (más de la mitad) quedaron marcadas con
  una advertencia de calidad: una parte relevante de los píxeles de esa
  imagen cae fuera del rango esperado del índice, casi siempre por
  reflectancia muy baja típica de aguas profundas y claras (el mismo
  fenómeno que ya afectó a NDVI/NDWI en el ejercicio 3, ver esa sección
  para el detalle técnico). Esto no invalida la comparación entre lagos
  (Atitlán es consistentemente mucho más bajo que Amatitlán en las 11
  fechas), pero sí pide cautela al leer el valor exacto de cualquier fecha
  individual de Atitlán.
- El índice de cianobacteria usado en todo este laboratorio es un
  indicador (proxy) calculado con una fórmula ajustada sobre datos
  simulados, no una medición de laboratorio real de clorofila. Debe
  leerse como una señal relativa para comparar fechas y lagos entre sí,
  no como una concentración exacta de cianobacteria en microgramos por
  litro.

## Qué queda documentado en el repositorio

`data/processed/tablas/resumen_temporal.csv` contiene, para cada una de
las 22 combinaciones lago-fecha, el promedio, la mediana, la desviación
estándar, los píxeles válidos usados y la cobertura de datos. El cuaderno
`notebooks/04_analisis_temporal.ipynb` genera esa tabla, las gráficas por
lago y la comparación conjunta, marcando los picos y la fecha de cobertura
parcial de forma visible.
