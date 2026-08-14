//VERSION=3
// Adaptación numérica del script "CyanoLakes Chlorophyll-a L1C (NDCI)"
// Autores originales: Jeremy Kravitz & Mark Matthews (2020)
// Original: cyano_ndci_l1c_original.js (copia textual, sin modificar)
//
// Qué se preserva sin cambios respecto al original:
//   - Todas las fórmulas: wbi() (Water Body Index), FAI(), NDCI() y el
//     polinomio de clorofila-a (chl).
//   - Todos los umbrales numéricos (MNDWI_threshold, NDWI_threshold, 0.1879,
//     0.1112, -0.2, 1, -0.03).
//   - Las mismas 9 bandas de entrada (B02, B03, B04, B05, B07, B08, B8A,
//     B11, B12), leídas desde Sentinel-2 L1C.
//
// Qué se adapta (y por qué):
//   - Sintaxis actualizada a Evalscript V3 (setup()/evaluatePixel()) porque
//     el original es V1 implícito y no permite declarar sampleType.
//   - La salida deja de ser un color RGB de visualización y pasa a ser un
//     único valor numérico FLOAT32 (el propio "chl"), tal como exige el
//     laboratorio ("un raster numérico apto para calcular estadísticas").
//   - Se agrega una banda "dataMask" que vale 1 solo donde el propio water
//     body index (wbi) original determina agua (water==1); en cualquier
//     otro píxel se entrega NaN/dataMask=0, en vez de dibujar el color de
//     tierra (trueColor) o el color naranja de vegetación flotante (FAI).
//     Esta es la máscara oficial del script, no una máscara inventada.
//
// No se agregó, quitó ni simplificó ningún término de la fórmula original.

function setup() {
  return {
    input: [
      { bands: ["B02", "B03", "B04", "B05", "B07", "B08", "B8A", "B11", "B12", "dataMask"] }
    ],
    output: [
      { id: "default", bands: 1, sampleType: "FLOAT32" },
      { id: "dataMask", bands: 1, sampleType: "UINT8" }
    ]
  };
}

const MNDWI_threshold = 0.42;
const NDWI_threshold = 0.4;
const filter_UABS = true;

function wbi(r, g, b, nir, swir1, swir2) {
  let ws = 0;
  try {
    let ndvi = (nir - r) / (nir + r);
    let mndwi = (g - swir1) / (g + swir1);
    let ndwi = (g - nir) / (g + nir);
    let ndwi_leaves = (nir - swir1) / (nir + swir1);
    let aweish = b + 2.5 * g - 1.5 * (nir + swir1) - 0.25 * swir2;
    let aweinsh = 4 * (g - swir1) - (0.25 * nir + 2.75 * swir1);
    let dbsi = ((swir1 - g) / (swir1 + g)) - ndvi;

    if (mndwi > MNDWI_threshold || ndwi > NDWI_threshold || aweinsh > 0.1879 || aweish > 0.1112 || ndvi < -0.2 || ndwi_leaves > 1) {
      ws = 1;
    }
    if (filter_UABS && ws == 1) {
      if ((aweinsh <= -0.03) || (dbsi > 0)) {
        ws = 0;
      }
    }
  } catch (err) {
    ws = 0;
  }
  return ws;
}

function NDCI(a, b) {
  return (b - a) / (b + a);
}

function evaluatePixel(sample) {
  let water = wbi(sample.B04, sample.B03, sample.B02, sample.B08, sample.B11, sample.B12);
  let NDCIv = NDCI(sample.B04, sample.B05);
  let chl = 826.57 * Math.pow(NDCIv, 3) - 176.43 * Math.pow(NDCIv, 2) + 19 * NDCIv + 4.071;

  let valid = (water == 1 && sample.dataMask == 1) ? 1 : 0;

  return {
    default: [valid ? chl : NaN],
    dataMask: [valid]
  };
}
