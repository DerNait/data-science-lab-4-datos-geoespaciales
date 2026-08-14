# Ejercicio 8.1: qué tan grande es el área con cianobacteria alta

## ¿Qué se hizo?

El promedio de cianobacteria de un lago puede subir tanto porque una zona
pequeña tiene un valor extremo como porque una parte grande del lago tiene
un valor moderadamente alto; el promedio por sí solo no distingue esos dos
casos. Este ejercicio calcula, para cada una de las 22 fechas oficiales,
qué porcentaje del área del lago (dentro del contorno real y con datos
utilizables) supera un umbral fijo de "valor alto".

Ese umbral (10 microgramos por litro) no se eligió mirando estos datos:
es el nivel de "Alerta 1" que recomienda la Organización Mundial de la
Salud en su guía de aguas recreativas seguras (2003) para clorofila-a
asociada a cianobacterias. Se fijó antes de calcular ningún resultado,
precisamente para que la definición de "alto" no dependiera de qué tan
llamativo se viera después.

## Lo que muestran los datos

**Amatitlán** muestra un salto claro en la extensión de área con
cianobacteria alta hacia el final del período: el 28 de abril de 2026 el
36.3 % del área válida del lago supera el umbral, y el 19 de junio de 2026
sube a 54.4 % (más de la mitad del lago). En el resto de sus fechas, el
porcentaje se mantiene bajo 8 %. Estas dos fechas son justamente las que
ya se habían identificado como "pico" en el análisis temporal del
ejercicio 4: este ejercicio confirma que ese pico no es un valor aislado
en un punto del lago, sino que corresponde a una porción sustancial de su
superficie.

**Atitlán** se mantiene con una extensión de área alta mínima durante
todo el período: nunca supera el 0.11 % de su superficie válida. Esto es
consistente con los valores de cianobacteria mucho más bajos que ya se
habían observado en Atitlán en los ejercicios 3 y 4.

## Qué tan confiables son estos números (limitaciones)

- El porcentaje se calcula solo sobre el área con datos utilizables de
  cada imagen (excluyendo nubes, sombras y píxeles fuera del contorno real
  del lago); se reporta junto a ese porcentaje la cobertura válida total,
  para que una imagen con menos área utilizable no aparente
  automáticamente una floración menor.
- La fecha de cobertura parcial de Amatitlán (7 de febrero de 2026, ~57 %
  de cobertura) conserva su advertencia en la tabla de resultados.
- El umbral usado (10 µg/L) es el mismo en ambos lagos y en las 22 fechas;
  no se ajustó por lago ni se cambió después de ver los resultados.
- Como en el resto del laboratorio, el índice de cianobacteria es un
  indicador relativo (proxy), no una medición de laboratorio; "área alta"
  significa área por encima de un umbral de referencia de salud pública
  aplicado a ese indicador, no una medición directa de toxinas.

## Qué queda documentado en el repositorio

`results/tables/extension_floracion.csv` contiene, para las 22
combinaciones lago-fecha, el porcentaje de área alta, el área válida
total, el umbral usado y la cobertura/calidad heredada del ejercicio 3.
`results/figures/atitlan_extension_floracion.png` y
`results/figures/amatitlan_extension_floracion.png` grafican esa
extensión a lo largo del tiempo. El cuaderno
`notebooks/08_1_extension_floracion.ipynb` genera ambos productos y la
comparación directa entre los dos lagos.
