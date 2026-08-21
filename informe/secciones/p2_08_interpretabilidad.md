# Parte 2, Ejercicio 8: interpretación y explicabilidad del modelo

> **Sección pendiente de redactar.** Este archivo es el esqueleto acordado para
> el informe de la Parte 2. Al escribirla, borre esta nota y las listas de
> control, y siga el estilo de las secciones de la Parte 1: prosa explicativa,
> sin jerga innecesaria, con los números concretos del laboratorio.

## ¿Qué se hizo?

Describa el análisis de importancia de variables y la interpretación con
SHAP del mejor modelo.

## Lo que muestran los datos

Qué variables pesan más y si sus valores altos o bajos empujan hacia alta
presencia, leído en clave ambiental.

## Incisos que esta sección debe cubrir

- Importancia global de las variables del mejor modelo
- Gráfico resumen de SHAP
- Variables más influyentes y dirección de su efecto
- Explicación de los patrones y su significado ambiental

## Insumos disponibles

- Mejor modelo según F2: Gradient Boosting, en
  `data/processed/ml/modelos/gradient_boosting.joblib`
- `correlaciones.deterministic_sample` para muestrear de forma
  reproducible, ya que calcular SHAP sobre 492 mil filas es inviable
- Advertencia: la importancia por ganancia de XGBoost señala las columnas
  de lago y coordenadas como dominantes, pero el diagnóstico de ablación
  en `results/tables/diagnostico_identidad_lago.csv` muestra que quitarlas
  casi no cambia el desempeño. Contraste ambas lecturas antes de concluir.
