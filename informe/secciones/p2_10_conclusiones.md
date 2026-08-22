# Parte 2, Ejercicio 10: análisis y conclusiones

## ¿Tiene el modelo capacidad suficiente para apoyar el monitoreo?

Con matices, sí, pero solo dentro de las condiciones en las que fue evaluado. El Gradient
Boosting alcanza un F2 de 0.958 bajo partición aleatoria, que baja a un todavía sólido 0.925
bajo validación espacial agrupada por bloque —es decir, mantiene un desempeño alto al
predecir celdas geográficamente nuevas dentro del mismo período—. Su recall se mantiene por
encima de 0.97 en casi todos los escenarios evaluados salvo la generalización entre lagos, lo
cual es justamente la propiedad que más importa para un sistema de alerta temprana: detectar
la floración real, aunque cueste algunas inspecciones de campo de más. El análisis de
interpretabilidad (ejercicio 8) confirma que esa capacidad predictiva descansa en su mayoría
sobre señal espectral y espacial genuina —reflectancia del infrarrojo cercano, NDWI de la
celda y su vecindad, distancia a la orilla— y no únicamente en un atajo geográfico, lo cual
da cierta confianza en que el modelo generaliza razonablemente **dentro** de un mismo lago.

Esa confianza no se extiende a los dos escenarios más exigentes que se probaron: bajo
validación temporal, el F2 cae a un rango de 0.32–0.36, y bajo generalización entre lagos, el
modelo directamente no sirve (recall 0 en un sentido, precisión menor a 0.06 % en el otro).
Un modelo así, hoy, es útil como herramienta de apoyo al monitoreo **dentro de Amatitlán, en
condiciones similares a las ya observadas**, pero no como sustituto de un monitoreo continuo
que incorpore fechas nuevas, y mucho menos como una herramienta que se pueda entrenar en un
lago y desplegar directamente en el otro.

## Limitaciones principales

- **Escasez extrema de positivos en Atitlán.** De 432,035 observaciones, solo 7 son
  positivas. Esto no es una limitación de modelado que se resuelva con mejor ingeniería de
  características: es una limitación de los datos disponibles, y es la causa directa de que
  el experimento A de generalización entre lagos (ejercicio 7) no tenga de dónde aprender.
- **Solo 11 fechas por lago.** La validación temporal (ejercicio 6) mostró que la señal de
  alta presencia se concentra en 2 de las 20 fechas distintas del conjunto de datos (56.3 % y
  34.6 % de los positivos de Amatitlán). Con tan pocos momentos de floración observados, es
  difícil separar un patrón temporal generalizable de una coincidencia de esas dos fechas
  particulares.
- **Pérdida de observaciones por nubosidad y por reflectancia casi nula en agua profunda.**
  El mismo problema que la Parte I ya había detectado en Atitlán (aguas profundas y oscuras
  que producen valores inestables en los índices) se traduce aquí en fechas con muchas menos
  celdas válidas —de 8,994 a 48,683 en las 11 fechas de Atitlán—, lo cual reduce
  efectivamente la cantidad de información disponible para entrenar y evaluar en ese lago.
- **La agregación de 10 a 50 metros suaviza los extremos.** Promediar 25 píxeles de 10 m en
  una sola celda de 50 m reduce el ruido, pero también atenúa los valores más extremos de
  cianobacteria, lo cual puede hacer que floraciones muy localizadas (menores a una celda de
  50 m) queden subrepresentadas en la variable respuesta.
- **La banda roja (B04) y el NDVI quedaron vetados como predictores por fuga de datos**
  (ejercicio 2), lo cual estrecha el espacio espectral disponible para el modelo a solo dos
  bandas (B03, B08) más los índices y variables derivadas que no dependen de B04.
- **La variable respuesta viene de un índice satelital calibrado sobre datos simulados
  (CyanoLakes), no de un muestreo físico de clorofila-a o de conteo de cianobacterias.** El
  modelo, en última instancia, aprende a reproducir ese proxy, no una medición directa de
  cianobacteria tomada del agua.

## Qué datos adicionales mejorarían el modelo

- **Precipitación y temperatura** de estaciones cercanas a cada lago; el propio enunciado
  sugiere los registros de WeatherSpark para Amatitlán y Santiago Atitlán, que permitirían
  probar de forma directa la hipótesis estacional que en este laboratorio solo se pudo
  aproximar con `mes` y la codificación cíclica del día del año.
- **Mediciones in situ de clorofila-a y conteo de cianobacterias**, para calibrar y validar
  el proxy satelital contra una medición de referencia tomada directamente del agua, en vez
  de depender exclusivamente del índice CyanoLakes.
- **Datos de nutrientes (nitrógeno y fósforo) y de descargas de aguas residuales** en ambas
  cuencas, que permitirían relacionar directamente la presión urbana con las floraciones
  observadas, en vez de solo citarla como contexto documentado por las autoridades de cuenca.
- **Más fechas de Atitlán, en particular con presencia de floraciones reales**, que es la
  única forma de resolver de raíz la escasez de positivos que impide entrenar un modelo
  útil específicamente para ese lago o generalizar hacia él desde Amatitlán.
- **Datos batimétricos (profundidad) por celda**, ya que la profundidad es la explicación
  ambiental más citada en este laboratorio para las diferencias entre lagos, pero nunca se
  incorporó como variable medible al modelo.

## Sobre la dimensión espacial de los datos

Este laboratorio, en conjunto, es un buen ejemplo de por qué la dimensión espacial (y
temporal) de los datos geoespaciales no se puede ignorar al evaluar un modelo. La partición
aleatoria 70/30 del ejercicio 4 dio resultados casi perfectos, en parte porque los datos son
espacialmente autocorrelacionados: dos celdas vecinas de la misma fecha comparten
prácticamente la misma señal, así que una partición que no lo tiene en cuenta filtra
información del conjunto de prueba hacia el de entrenamiento sin que ninguna métrica lo deje
ver. Solo al agrupar por bloque espacial y por fecha —ejercicio 6— aparece la magnitud real
de esa fuga, y solo con la generalización entre lagos —ejercicio 7— aparece el límite más
duro de todos: ni siquiera el mejor modelo, evaluado con la validación más favorable,
sobrevive el salto a un lago con condiciones espectrales y ambientales distintas. Cualquier
uso futuro de un modelo como este para apoyar el monitoreo real de los lagos debe evaluarse
con esta misma jerarquía de validaciones, de la más optimista a la más exigente, y no
quedarse solo con la primera.
