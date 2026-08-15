# 6. Correlación con NDVI y NDWI

Se comparó el proxy de concentración de cianobacteria con NDVI y NDWI para
cada lago y fecha. Antes de calcular los coeficientes se verificó que los tres
raster de cada escena compartieran CRS, resolución, dimensiones y
transformación. Los pares se formaron únicamente con píxeles válidos de ambos
índices dentro de la geometría real del lago. Se calcularon Pearson, para la
relación lineal, y Spearman, para la relación monótona menos sensible a valores
extremos. Además del resultado por fecha se construyó una muestra agrupada
equilibrada, con el mismo máximo de pares por escena.

En Amatitlán se observó una asociación positiva consistente entre
cianobacteria y NDVI: la mediana de los coeficientes por fecha fue 0.67 para
Pearson y 0.63 para Spearman, con signo positivo en 10 de 11 fechas. Con NDWI
la relación fue predominantemente inversa: medianas de -0.59 y -0.51,
respectivamente. La señal más fuerte ocurrió el 28 de abril de 2026, cuando
NDVI alcanzó 0.91 y NDWI cerca de -0.90 con ambos métodos. Estos resultados
describen una coincidencia espacial clara en ese lago, pero no identifican por
sí solos una causa ambiental.

En Atitlán, las medianas por fecha fueron débiles: 0.03 (Pearson) y 0.13
(Spearman) para NDVI, y aproximadamente 0.00 y -0.07 para NDWI. Aunque el
Spearman agrupado de cianobacteria-NDWI fue -0.53, ese valor mezcla escenas con
niveles y distribuciones temporales diferentes; por ello no sustituye la
evidencia por fecha y no se interpreta como una relación espacial fuerte y
estable.

Los valores p se reportan como referencia exploratoria. La autocorrelación
espacial hace que los píxeles vecinos no sean observaciones completamente
independientes, de modo que un valor p pequeño no demuestra relevancia
ambiental ni causalidad. Los resultados completos están en
`results/tables/correlaciones_por_fecha.csv` y
`results/tables/correlaciones_por_lago.csv`; las figuras comparativas están en
`results/figures/`.
