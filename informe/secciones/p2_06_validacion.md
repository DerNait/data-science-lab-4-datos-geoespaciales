# Parte 2, Ejercicio 6: validación espacial y temporal

> **Sección pendiente de redactar.** Este archivo es el esqueleto acordado para
> el informe de la Parte 2. Al escribirla, borre esta nota y las listas de
> control, y siga el estilo de las secciones de la Parte 1: prosa explicativa,
> sin jerga innecesaria, con los números concretos del laboratorio.

## ¿Qué se hizo?

Describa la cuadrícula de bloques, la estrategia de validación por grupos
y la validación temporal.

## Lo que muestran los datos

Número de bloques por lago, observaciones por bloque, y la comparación
contra la división aleatoria.

## Incisos que esta sección debe cubrir

- Cuadrícula de aproximadamente 1 km y evaluación de si el tamaño alcanza
- Asignación de observaciones a bloques y mapa de los bloques
- Validación que mantiene cada bloque dentro de un solo grupo
- Reentrenamiento de los tres modelos con validación espacial
- Estrategia de validación temporal
- Comparación contra la división aleatoria y explicación de la diferencia

## Insumos disponibles

- Partición compartida en `data/processed/ml/particion_70_30.parquet`,
  que ya trae `lago` y `fecha` para agrupar
- Métricas de referencia en `results/tables/metricas_modelos.csv`
- Medido de antemano: a 1 km, Amatitlán da 35 bloques y Atitlán 164.
  Los 35 de Amatitlán tienen algún positivo; de los 164 de Atitlán, solo 3.
- Tres fechas de Amatitlán tienen cero positivos, así que habrá pliegues
  temporales con métricas indefinidas
