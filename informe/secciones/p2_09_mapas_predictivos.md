# Parte 2, Ejercicio 9: generación de mapas predictivos

> **Sección pendiente de redactar.** Este archivo es el esqueleto acordado para
> el informe de la Parte 2. Al escribirla, borre esta nota y las listas de
> control, y siga el estilo de las secciones de la Parte 1: prosa explicativa,
> sin jerga innecesaria, con los números concretos del laboratorio.

## ¿Qué se hizo?

Describa cómo se reconstruyeron espacialmente las probabilidades y qué
escala se usó.

## Lo que muestran los datos

Zonas correctamente detectadas, falsos positivos, falsos negativos y
patrones espaciales de error.

## Incisos que esta sección debe cubrir

- Probabilidad de alta presencia para cada observación
- Reconstrucción espacial y mapa de probabilidad
- Al menos un mapa por lago
- Escala que distinga probabilidad muy baja, baja, alta y muy alta
- Comparación con los mapas de cianobacteria de la Parte 1
- Identificación de aciertos, falsos positivos y falsos negativos
- Regiones donde el modelo falla de forma sistemática

## Insumos disponibles

- Maquinaria de mapas ya existente en `src/analisis_espacial.py`:
  `plot_cyano_map`, `save_cyano_map_png`, `comparison_scale`
- Mapas de la Parte 1 en `results/maps/<lago>_<fecha>_cianobacteria.png`
- Cada fila del conjunto de datos trae `x_utm` e `y_utm`, que son el
  centroide de su celda de 50 metros
