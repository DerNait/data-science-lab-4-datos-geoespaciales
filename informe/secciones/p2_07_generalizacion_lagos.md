# Parte 2, Ejercicio 7: generalización entre lagos

> **Sección pendiente de redactar.** Este archivo es el esqueleto acordado para
> el informe de la Parte 2. Al escribirla, borre esta nota y las listas de
> control, y siga el estilo de las secciones de la Parte 1: prosa explicativa,
> sin jerga innecesaria, con los números concretos del laboratorio.

## ¿Qué se hizo?

Describa los dos experimentos cruzados y qué conjunto de predictores se
usó en ellos.

## Lo que muestran los datos

Métricas de ambos experimentos junto a los conteos de positivos, y
comparación contra el caso en que ambos lagos están en entrenamiento y prueba.

## Incisos que esta sección debe cubrir

- Experimento que entrena con Atitlán y evalúa con Amatitlán
- Experimento que entrena con Amatitlán y evalúa con Atitlán
- Métricas de ambos y comparación con el caso del mismo lago
- Respuesta a si un modelo entrenado en un lago generaliza al otro
- Discusión de las diferencias geográficas, ambientales y espectrales

## Insumos disponibles

- Constante `modelos.COLUMNAS_IDENTIDAD_LAGO`, que lista las cuatro
  columnas que hay que retirar en estos experimentos. Dejarlas convierte
  al modelo en un detector de lago, porque los dos lagos ocupan rangos de
  coordenadas disjuntos.
- Atitlán aporta 7 celdas positivas de 432,035, así que ninguno de los dos
  experimentos dará una estimación estable. Eso es el hallazgo, no un
  error: repórtelo con los conteos y explique por qué ocurre.
