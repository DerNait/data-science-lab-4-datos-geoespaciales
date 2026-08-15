# 8.3. Comparación de distribuciones

Las fechas se eligieron con reglas establecidas antes de comparar las
distribuciones: primera escena completa como referencia, pico del resumen
temporal, mayor extensión por encima de 10 µg/L y una fecha común entre ambos
lagos. Se usó la misma máscara combinada de geometría real, agua y validez
simultánea de los tres índices. Los histogramas y boxplots comparten unidades,
límites de visualización y tratamiento de extremos; la tabla conserva todos
los valores válidos y sus percentiles.

Amatitlán muestra un desplazamiento marcado de toda la distribución. La
mediana pasó de 4.49 µg/L en la referencia del 28 de enero de 2025 a 6.44
µg/L en la fecha común del 13 de abril de 2026 y 10.73 µg/L en la fecha de
mayor extensión, el 19 de junio de 2026. En esa última escena el percentil 95
alcanzó 21.34 µg/L. El cambio no se limita al promedio: aumentaron tanto el
centro como la cola superior, lo que es compatible con una expansión espacial
de valores altos.

Atitlán presentó distribuciones mucho más bajas: mediana de 1.75 µg/L en la
referencia del 13 de abril de 2025 y 2.20 µg/L en la fecha común del 13 de
abril de 2026. La escena final seleccionada por mayor extensión, 22 de julio
de 2026, tuvo mediana de 1.12 µg/L y conserva la advertencia
`revisar_valores_atipicos`; por tanto, su diferencia temporal debe leerse con
cautela y no como una tendencia definitiva.

Los mapas restan `fecha_final - fecha_inicial` únicamente después de confirmar
rejillas idénticas y usan una escala divergente centrada en cero. Son mapas de
cambio del proxy satelital, no mediciones directas de laboratorio. Las
estadísticas están en `results/tables/distribuciones_por_fecha.csv`, las
comparaciones en `results/figures/` y los mapas de diferencia en
`results/maps/`.
