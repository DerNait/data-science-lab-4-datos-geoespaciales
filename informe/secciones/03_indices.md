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
requiere una cuenta y un permiso de acceso independientes. Ese acceso ya
está configurado y el mismo proceso construido calculó automáticamente la
cianobacteria de las 22 fechas sin tener que rehacer nada de lo demás.

## Resultados obtenidos

**Vegetación, agua y cianobacteria: completos para las 22 fechas (66 de 66
combinaciones lago-fecha-índice).**

En ambos lagos, el índice de agua (NDWI) dio valores positivos de forma
consistente sobre las zonas analizadas, confirmando que la ubicación y el
área usada corresponden efectivamente a la superficie de los lagos. El
índice de vegetación (NDVI), como se esperaba sobre agua abierta, se
mantuvo en general bajo o negativo en la mayoría de las fechas, sin mostrar
un patrón evidente de vegetación densa o floraciones extendidas de forma
sostenida a lo largo del período.

El índice de cianobacteria muestra una diferencia clara entre los dos
lagos: Amatitlán se mueve en valores notablemente más altos que Atitlán a
lo largo de toda la serie, y sube de forma marcada en las últimas fechas
disponibles (abril y junio de 2026). Atitlán se mantiene en valores mucho
más bajos y estables durante todo el período. El detalle fecha por fecha y
su interpretación ambiental están en la sección del ejercicio 4.

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
limpios.

El índice de cianobacteria tiene su propio conjunto de fechas atípicas en
Atitlán, más amplio que el de NDVI/NDWI: además de las tres fechas
anteriores, también el 17 de julio de 2025, el 29 de diciembre de 2025 y el
22 de julio de 2026 quedaron marcados "revisar con cautela" (más del 10 %
de los píxeles fuera del rango de referencia del método, 0 a 500 µg/L,
casi siempre por valores negativos del polinomio sobre agua muy clara). En
total 6 de las 11 fechas de Atitlán llevan esta advertencia en
cianobacteria; ninguna fecha de Amatitlán la tiene. Además, la fecha del 7
de febrero de 2026 en Amatitlán, ya identificada como de cobertura parcial
en el enunciado del laboratorio, se mantiene marcada con esa misma
advertencia en los tres índices derivados de ella.

Por último, la caja de consulta de Atitlán es más grande que la de
Amatitlán y, a la resolución de 10 metros que usa este laboratorio, supera
el límite de 2500 píxeles por lado que acepta de forma síncrona el
servicio de Copernicus usado para cianobacteria. Para esas 11 escenas la
imagen se pidió a una resolución ligeramente más gruesa (manteniendo la
proporción del área) y luego se realineó a la misma rejilla de 10 metros
que el resto de los productos, así que el archivo final entregado no
cambia de resolución; solo cambió el insumo intermedio.

## Nota sobre el contorno del lago

En esta etapa (ejercicio 3) los promedios usan una clasificación automática
de "qué píxel es agua" que hace el propio satélite en cada imagen, porque
todavía no se contaba con el contorno exacto del lago. Es una solución
razonable y ya validada. El ejercicio 5 obtuvo después el contorno real de
ambos lagos (de OpenStreetMap) y lo combina con esta misma clasificación
para afinar los resultados en las orillas; ver esa sección para el
detalle.
