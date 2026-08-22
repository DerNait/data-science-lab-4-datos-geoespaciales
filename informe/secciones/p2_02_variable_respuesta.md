# Parte 2, Ejercicio 2: construcción de la variable respuesta

## ¿Qué se hizo?

Se binarizó `cianobacteria_ugl` en una nueva columna, `cyano_alta`: 1 si el promedio de la
celda es mayor o igual a 10 µg/L, 0 en caso contrario. Es el mismo umbral que ya se usó en
los ejercicios 8.1 y 8.2 de la Parte I, no uno nuevo elegido para esta parte.

El punto de corte se justifica con dos fuentes independientes:

- **OECD (1982), *Eutrophication of waters: Monitoring, assessment and control*.** Su
  clasificación trófica por clorofila-a media anual sitúa el rango **eutrófico** entre 8 y
  25 µg/L (oligotrófico ≤2.5, mesotrófico 2.5–8, hipereutrófico ≥25). 10 µg/L cae dentro de
  ese rango eutrófico.
- **World Health Organization (2003), *Guidelines for safe recreational water environments,
  Volume 1: Coastal and fresh waters*.** Su marco de niveles de alerta para cianobacterias
  por clorofila-a sitúa el nivel de vigilancia en ~1–12 µg/L y el Alert Level 1 en ~12–24
  µg/L. 10 µg/L cae en el **extremo superior del nivel de vigilancia**, justo antes de
  cruzar a Alert Level 1 —no "es" Alert Level 1, una imprecisión que llegó a figurar en una
  versión anterior de la documentación interna del proyecto y que se corrigió al verificar
  la tabla original de la OMS.

En conjunto, ambas referencias señalan 10 µg/L como un punto de corte razonable: cae en la
zona donde un cuerpo de agua deja de considerarse limpio y empieza a acercarse a niveles que
ameritan vigilancia sanitaria activa, sin llegar todavía al nivel de alerta más alto.

## Distribución y desbalance

| Corte | n total | n positivos | % positivos | negativos por positivo |
| --- | ---: | ---: | ---: | ---: |
| Global | 492,677 | 6,365 | 1.29 % | 76.4 |
| Amatitlán | 60,642 | 6,358 | 10.48 % | 8.5 |
| Atitlán | 432,035 | 7 | 0.0016 % | 61,718 |

**El 99.9 % de las observaciones positivas de todo el conjunto de datos vienen de
Amatitlán.** Atitlán aporta apenas 7 celdas positivas en sus 432,035 observaciones, y esas 7
se concentran en solo 3 fechas (2025-07-17: 2, 2025-11-21: 3, 2025-12-29: 2); las otras 8
fechas de Atitlán no tienen ni una sola celda de alta presencia. Amatitlán, en cambio, pasa
de 0 % de celdas altas en tres de sus fechas más tempranas a 34.6 % el 2026-04-28 y 56.3 %
el 2026-06-19 —las mismas dos fechas que la Parte I ya había identificado como picos.

Este desbalance tiene tres consecuencias directas para el resto del laboratorio: (1) la
exactitud deja de ser una métrica útil, porque predecir siempre "ausencia" ya acierta 98.7 %
de las veces sin haber aprendido nada; (2) los modelos necesitan algún mecanismo explícito
para no colapsar hacia la clase mayoritaria (pesos de clase, ver ejercicio 4); y (3) con
solo 7 positivos en total, cualquier modelo entrenado exclusivamente con datos de Atitlán
tiene una base de aprendizaje demasiado pequeña para generalizar —una limitación que se
confirma de forma directa en el ejercicio 7.

## Variables excluidas por fuga de datos

El índice de cianobacteria de este laboratorio se calcula con el script CyanoLakes, que
construye un índice de clorofila (`NDCI = (B05 − B04) / (B05 + B04)`) y estima `chl` a
partir de él. Como la banda B05 nunca se descargó (no forma parte de las cuatro bandas
elegidas en el ejercicio 1 y 2 de la Parte I), la fuga hacia la variable respuesta entra por
B04:

| Variable | Motivo de exclusión |
| --- | --- |
| `cianobacteria_ugl` | Es la variable de la que se deriva directamente `cyano_alta` |
| `B04` | Interviene directamente en el NDCI que usa el script de cianobacteria para calcular `chl` |
| `ndvi` | Se calcula como `(B08 − B04) / (B08 + B04)`: usa B04, fuga indirecta |

`B03` y `B08` sí se conservan como predictores válidos: en el script de cianobacteria solo
participan en la máscara de agua, no en el valor numérico de `chl`, así que no transmiten
información directa sobre la variable respuesta.

**Tabla y figuras de esta sección** (`src/respuesta.py`, notebook
`10_variable_respuesta.ipynb`): `results/tables/distribucion_respuesta.csv` (distribución
global, por lago y por fecha); `results/figures/eda_cyano_alta_por_fecha_amatitlan.png` y
`results/figures/eda_cyano_alta_por_fecha_atitlan.png` (barras de proporción de `cyano_alta`
por fecha, un panel por lago).
