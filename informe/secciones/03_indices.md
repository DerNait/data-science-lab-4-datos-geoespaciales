# Ejercicio 3: vegetación, agua y cianobacteria vistas desde satélite

## ¿Qué se midió y para qué sirve?

Para cada una de las 22 fechas oficiales (11 en el lago de Amatitlán y 11 en
el lago de Atitlán) se calcularon tres indicadores a partir de imágenes del
satélite Sentinel-2:

- **Índice de vegetación (NDVI):** indica qué tan presente está la
  vegetación o material vegetal (algas incluidas) en cada punto de la
  imagen. Sobre agua abierta y limpia se espera un valor bajo o negativo;
  valores más altos pueden señalar vegetación acuática, algas superficiales
  o sedimentos.
- **Índice de agua (NDWI):** confirma qué zonas de la imagen corresponden
  realmente a agua superficial. Sirve como control de calidad: si el NDWI
  es alto donde se espera lago, la ubicación y la máscara de agua usada son
  confiables.
- **Índice de cianobacteria:** un indicador más específico, pensado para
  estimar la concentración de clorofila asociada a floraciones de
  cianobacterias (el problema central de este laboratorio). Su cálculo
  requiere un procesamiento especializado que se explica más abajo.

## Cómo se obtuvieron los datos

Las imágenes se descargaron directamente desde la plataforma oficial de
Copernicus (el programa europeo que opera los satélites Sentinel), limitando
la descarga al área de cada lago y a las bandas de color estrictamente
necesarias para estos cálculos, para no descargar información innecesaria.

Para el índice de cianobacteria se decidió usar un método ya publicado y
documentado (CyanoLakes, desarrollado por investigadores especializados en
monitoreo de floraciones algales desde satélite) en lugar de inventar una
fórmula propia. Este método necesita un tipo de imagen distinto al que se
usa para vegetación y agua, por lo que se pide directamente al servicio de
procesamiento de Copernicus en vez de calcularse a mano; ese servicio
requiere una cuenta y un permiso de acceso independientes, que el equipo
está tramitando. En cuanto ese acceso esté disponible, el mismo proceso ya
construido calculará automáticamente la cianobacteria de las 22 fechas sin
tener que rehacer nada de lo demás.

## Resultados obtenidos hasta ahora

**Vegetación y agua (NDVI y NDWI): completos para las 22 fechas.**

En ambos lagos, el índice de agua (NDWI) dio valores positivos de forma
consistente sobre las zonas analizadas, confirmando que la ubicación y el
área usada corresponden efectivamente a la superficie de los lagos. El
índice de vegetación (NDVI), como se esperaba sobre agua abierta, se
mantuvo en general bajo o negativo en la mayoría de las fechas, sin mostrar
un patrón evidente de vegetación densa o floraciones extendidas de forma
sostenida a lo largo del período.

**Cianobacteria: pendiente.** Los 22 valores todavía no están disponibles;
el método y el procesamiento ya están listos y probados, solo falta que el
equipo reciba el acceso al servicio de Copernicus mencionado arriba para
obtener los números reales.

## Una advertencia importante sobre la calidad del dato

En tres fechas del lago de Atitlán (18 de enero de 2025, 21 de noviembre de
2025 y 12 de febrero de 2026), una parte inusualmente grande de la imagen
mostró valores de vegetación fuera de lo físicamente posible. Se investigó
el origen y se confirmó que se trata de un problema conocido de las
imágenes satelitales sobre aguas muy profundas y oscuras (el sensor capta
una señal casi nula que, al convertirla en índice, se vuelve inestable),
no de una señal ambiental real. Estas tres fechas quedaron marcadas
explícitamente como "revisar con cautela" en los datos, para que no se
interpreten sus promedios de la misma forma que los de una fecha con datos
limpios. Además, la fecha del 7 de febrero de 2026 en Amatitlán, ya
identificada como de cobertura parcial en el enunciado del laboratorio, se
mantiene marcada con esa misma advertencia en todos los productos
derivados de ella.

## Limitación pendiente

El laboratorio menciona que se entregaría el contorno exacto del agua de
cada lago (un polígono geográfico oficial). Ese archivo no ha llegado
todavía, así que mientras tanto se usa una clasificación automática de "qué
píxel es agua" que hace el propio satélite en cada imagen. Es una solución
razonable y ya validada, pero en cuanto se obtenga el contorno oficial del
lago debe usarse para afinar los resultados, sobre todo en las orillas.
