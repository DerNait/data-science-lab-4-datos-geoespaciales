# Ejercicio 8.4: ¿hay un patrón según la época del año?

## ¿Qué se hizo?

Guatemala tiene dos épocas climáticas bien diferenciadas: una **seca**
(aproximadamente de noviembre a abril) y una **lluviosa** (de mayo a
octubre). Se agruparon las 11 fechas oficiales de cada lago según en cuál
de las dos épocas cae su fecha de calendario, y se comparó el promedio de
cianobacteria entre ambos grupos.

**Esto no es un modelo de estacionalidad ni una serie de tiempo formal.**
Son solo 11 observaciones irregulares por lago a lo largo de
aproximadamente año y medio —no un muestreo mensual sistemático—, así que
el resultado debe leerse como un indicio exploratorio, no como una
conclusión firme.

## Lo que muestran los datos

| Lago | Época seca | Época lluviosa |
|---|---:|---:|
| Amatitlán | 5.77 µg/L (10 fechas) | 11.49 µg/L (**1 fecha**) |
| Atitlán | 1.14 µg/L (8 fechas) | 1.18 µg/L (3 fechas) |

**Atitlán** no muestra ninguna diferencia relevante entre épocas: 1.14
frente a 1.18 µg/L son prácticamente el mismo valor. No hay indicio de
patrón estacional en este lago durante el período observado.

**Amatitlán** sí muestra un valor más alto en la única fecha de época
lluviosa disponible (19 de junio de 2026), pero esa fecha es también la
más reciente y la de mayor cianobacteria de toda la serie del lago (ver
ejercicio 4). Con una sola observación en época lluviosa, **no se puede
distinguir si ese valor alto ocurrió por ser época lluviosa, o simplemente
porque coincide con el aumento reciente que ya se había identificado**
independientemente de la estación del año.

## Por qué no se puede concluir más que esto

- Una sola fecha no permite calcular ninguna variabilidad dentro de la
  época lluviosa de Amatitlán; cualquier afirmación sobre "la época
  lluviosa causa más cianobacteria en Amatitlán" iría más allá de lo que
  estos datos pueden sostener.
- Las fechas oficiales no siguen un calendario mensual fijo: hay meses sin
  ninguna observación y otros con varias, lo que impide comparar
  "abril contra abril" de años distintos o construir un ciclo anual
  completo.
- Confirmar o descartar un patrón estacional real requeriría más fechas
  —en particular más observaciones de Amatitlán en época lluviosa— y,
  preferiblemente, cruzarlas con registros de lluvia y temperatura de
  estaciones meteorológicas cercanas a cada lago (por ejemplo, del
  INSIVUMEH), que no forman parte de los datos de este laboratorio.
