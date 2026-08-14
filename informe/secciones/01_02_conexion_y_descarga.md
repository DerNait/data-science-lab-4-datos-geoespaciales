# Ejercicios 1 y 2: conexión y adquisición de las imágenes satelitales

## ¿Qué se hizo?

Para poder analizar los lagos de Amatitlán y Atitlán con imágenes del
satélite Sentinel-2, primero hubo que conectarse a la plataforma oficial
que las distribuye (Copernicus Data Space, el programa europeo que opera
estos satélites) y descargar únicamente las 22 escenas oficiales del
laboratorio: 11 fechas de Amatitlán y 11 de Atitlán, definidas de antemano
en el enunciado.

La conexión se hace con la cuenta personal de cada integrante (inicio de
sesión estándar del proveedor, sin guardar usuarios ni contraseñas en el
código) y la descarga se limita, para cada fecha, al área de cada lago y a
las cuatro bandas de color estrictamente necesarias para los cálculos
posteriores (verde, rojo, infrarrojo cercano y una banda de control de
calidad que identifica nubes, sombras y agua). No se descargó ninguna
banda ni área adicional.

## Resultados obtenidos

**Las 22 escenas están descargadas y validadas: 11/11 en cada lago, sin
duplicados ni fechas faltantes.** Para cada una se comprobó que el archivo
recibido tenga un sistema de coordenadas válido (UTM zona 15N,
`EPSG:32615`) y una resolución de 10×10 metros por píxel, tal como se
esperaba.

La cobertura numéricamente válida (porcentaje de píxeles sin datos
faltantes dentro de cada imagen descargada) resultó prácticamente completa
en las 22 fechas, entre 99.99 % y 100 %. La única excepción esperada es la
fecha del 7 de febrero de 2026 en Amatitlán, que el propio enunciado del
laboratorio ya advertía como una escena de cobertura parcial (~57.1 % de
área realmente utilizable dentro del lago, distinto del porcentaje de
píxeles sin error del archivo descargado). Esa advertencia se mantiene
visible en el inventario de escenas y se hereda automáticamente en todos
los productos que se calculan a partir de esa fecha en los ejercicios
siguientes, para que nunca se compare como si fuera una escena completa.

## Qué queda documentado en el repositorio

`data/raw/manifest_escenas.csv` es el inventario auditable de las 22
escenas: fecha, lago, satélite, nubosidad oficial, cobertura válida medida,
sistema de coordenadas, resolución y cualquier advertencia de calidad. Es
el punto de partida único para el resto del laboratorio: el ejercicio 3
(vegetación, agua y cianobacteria) lee directamente estas 22 escenas, sin
volver a descargar ni a decidir qué fechas usar.
