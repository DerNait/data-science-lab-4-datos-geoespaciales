# Ejercicio 5: dónde se concentra la cianobacteria dentro de cada lago

## ¿Qué se hizo?

Los ejercicios anteriores midieron un solo número de cianobacteria por
fecha y lago (un promedio). Este ejercicio va un paso más allá y mira
**dentro** de cada lago: se generó un mapa de cianobacteria para cada una
de las 22 fechas oficiales, y se compararon esos mapas entre sí usando
siempre la misma escala de color, para que un color represente lo mismo
en cualquier mapa.

Antes de generar los mapas se resolvió un pendiente importante: hasta el
ejercicio 3, el área de "lago" usada en los cálculos era una aproximación
calculada automáticamente por el propio satélite (qué píxel parece agua
en cada imagen), porque todavía no se tenía el contorno real del lago. En
este ejercicio se obtuvo ese contorno real (de OpenStreetMap, la
plataforma abierta de mapas colaborativos) y se combinó con la
aproximación anterior: un punto del mapa solo se considera parte del lago
si **ambos** criterios coinciden. En la práctica, el contorno real recorta
solo un margen pequeño adicional (menos del 0.03 % de los puntos en el
caso revisado), porque la aproximación automática ya era bastante
ajustada.

## Lo que muestran los datos

**El contorno real es mucho más pequeño que la caja de consulta usada
para descargar las imágenes**, como era de esperar (la caja rectangular
incluye tierra alrededor del lago): el área real de Atitlán es de
aproximadamente 124.7 km² (la caja de consulta mide 474.2 km², casi 4
veces más grande) y la de Amatitlán es de aproximadamente 15.0 km² (la
caja de consulta mide 121.7 km², más de 8 veces más grande). Estos valores
son consistentes con el área real conocida de ambos lagos.

**Los mapas comparativos** (misma escala de color, guardados en
`results/maps/`) muestran con claridad la diferencia entre lagos ya
observada en los ejercicios 3 y 4: en las fechas de Amatitlán con mayor
cianobacteria (28 de abril y 19 de junio de 2026), buena parte de la
superficie del lago aparece en colores intensos, mientras que Atitlán se
mantiene en colores bajos en todas sus fechas, incluida la fecha común del
13 de abril de 2026 que permite comparar ambos lagos lado a lado con
exactamente la misma escala.

Como una primera aproximación a la ubicación de la cianobacteria dentro
del lago, se comparó el promedio de la mitad norte contra la mitad sur de
cada lago en su fecha de mayor cianobacteria. Esta comparación es
ilustrativa de una sola fecha, no un patrón espacial confirmado; el
análisis de persistencia del ejercicio 8.2 (qué zonas se repiten a lo
largo de las 11 fechas) es la evidencia más sólida sobre "dónde" se
concentra la cianobacteria de forma sostenida.

## Una nota sobre las fechas usadas en las comparaciones

Para los paneles comparativos se necesitaba, por lago, una fecha de valor
bajo (referencia) y una fecha "crítica" de valor alto. Mientras no exista
todavía la comparación conjunta de ambos lagos (ejercicio 7), la fecha
crítica se tomó del mismo criterio de "pico" ya usado en el ejercicio 4
(la fecha que supera en más de una desviación estándar el promedio normal
de ese lago). Es una elección razonable pero provisional: si el ejercicio
7 identifica una fecha crítica distinta al mirar ambos lagos en conjunto,
los mapas comparativos de este ejercicio deben regenerarse con esa fecha.

## Qué tan confiables son estos números (limitaciones)

- La comparación norte/sur de la sección anterior se calculó sobre **una
  sola fecha** por lago; no debe leerse como una conclusión sobre todo el
  período. La sección de persistencia (ejercicio 8.2) resume las 11
  fechas y es la fuente más confiable para hablar de zonas "que se repiten".
- El contorno real proviene de OpenStreetMap, una fuente colaborativa
  abierta, no de un catastro oficial de los lagos. Se documentó su origen,
  fecha de consulta y licencia en `codebook.md`; el área obtenida es
  consistente con el área real conocida de ambos lagos, lo cual da
  confianza en su precisión para este uso.
- Los mapas heredan las mismas advertencias de calidad del ejercicio 3 y
  4: las fechas marcadas como "revisar con cautela" (más de la mitad de
  las fechas de Atitlán) no deben interpretarse como si tuvieran la misma
  confiabilidad que una fecha limpia; un cambio de color en esas fechas
  puede deberse a un artefacto de la imagen y no a un evento real.
- El índice sigue siendo un indicador relativo (proxy), no una medición de
  laboratorio; los colores del mapa comparan intensidad relativa entre
  puntos y fechas, no una concentración exacta de cianobacteria.

## Qué queda documentado en el repositorio

`data/raw/geojson/lago_<lago>_boundary.geojson` contiene el contorno real
de cada lago. `results/maps/` contiene los 22 mapas individuales, los
paneles comparativos por lago, la comparación entre lagos en la fecha
común, los mapas de persistencia (ejercicio 8.2) y un mapa interactivo por
lago (formato HTML, se abre en cualquier navegador). `results/tables/metadata_mapas.csv`
enumera cada mapa generado con su fecha, tipo y escala de color. El
cuaderno `notebooks/05_analisis_espacial.ipynb` genera todos estos
productos y documenta las decisiones de visualización tomadas antes de
ver los resultados.
