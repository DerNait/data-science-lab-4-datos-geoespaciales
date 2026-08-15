from __future__ import annotations

import unittest

from src.comparacion_lagos import (
    assign_season,
    build_comparison_table,
    build_seasonal_summary,
    lake_summary_row,
)


def _temporal_row(lago, fecha, promedio, quality_flag="calculado"):
    return {
        "lago": lago,
        "fecha": fecha,
        "cyano_promedio": str(promedio),
        "cyano_mediana": str(promedio),
        "cyano_std": "0.1",
        "pixeles_validos": "100",
        "cobertura_valida_pct": "50.0",
        "quality_flag": quality_flag,
    }


def _extension_row(lago, fecha, porcentaje_alto):
    return {
        "lago": lago,
        "fecha": fecha,
        "porcentaje_alto": str(porcentaje_alto),
        "quality_flag": "calculado",
    }


def _correlation_row(lago, indice, metodo, mediana):
    return {
        "lago": lago,
        "indice": indice,
        "metodo": metodo,
        "coeficiente_mediano_fechas": str(mediana),
    }


class LakeSummaryRowTest(unittest.TestCase):
    def test_computes_expected_indicators(self) -> None:
        temporal = [
            _temporal_row("amatitlan", "2025-01-01", 2.0),
            _temporal_row("amatitlan", "2025-06-01", 12.0),
            _temporal_row("amatitlan", "2025-12-01", 8.0, quality_flag="revisar_valores_atipicos"),
        ]
        extension = [
            _extension_row("amatitlan", "2025-01-01", 1.0),
            _extension_row("amatitlan", "2025-06-01", 40.0),
            _extension_row("amatitlan", "2025-12-01", 20.0),
        ]
        correlation = [
            _correlation_row("amatitlan", "ndvi", "pearson", 0.5),
            _correlation_row("amatitlan", "ndwi", "pearson", -0.4),
        ]
        row = lake_summary_row(
            "amatitlan",
            temporal_rows=temporal,
            extension_rows=extension,
            correlation_rows=correlation,
            umbral=10.0,
        )
        self.assertEqual(row["n_fechas_total"], 3)
        self.assertEqual(row["n_fechas_calculado"], 2)
        self.assertEqual(row["frecuencia_fechas_sobre_umbral"], 1)
        self.assertAlmostEqual(row["cyano_promedio_general"], (2 + 12 + 8) / 3, places=4)
        self.assertEqual(row["fecha_porcentaje_alto_maximo"], "2025-06-01")
        self.assertEqual(row["correlacion_ndvi_pearson_mediana"], "0.5")

    def test_invalid_lake_raises(self) -> None:
        with self.assertRaises(ValueError):
            lake_summary_row("peten", temporal_rows=[], extension_rows=[], correlation_rows=[])

    def test_missing_temporal_rows_raises(self) -> None:
        from src.indices import InputDataError

        with self.assertRaises(InputDataError):
            lake_summary_row(
                "amatitlan", temporal_rows=[], extension_rows=[], correlation_rows=[]
            )


class BuildComparisonTableTest(unittest.TestCase):
    def test_builds_one_row_per_lake_sorted(self) -> None:
        temporal = [
            _temporal_row("atitlan", "2025-01-01", 1.0),
            _temporal_row("amatitlan", "2025-01-01", 5.0),
        ]
        extension = [
            _extension_row("atitlan", "2025-01-01", 0.5),
            _extension_row("amatitlan", "2025-01-01", 10.0),
        ]
        correlation = [
            _correlation_row("atitlan", "ndvi", "pearson", 0.1),
            _correlation_row("amatitlan", "ndvi", "pearson", 0.2),
        ]
        table = build_comparison_table(
            temporal_rows=temporal, extension_rows=extension, correlation_rows=correlation
        )
        self.assertEqual([row["lago"] for row in table], ["amatitlan", "atitlan"])


class AssignSeasonTest(unittest.TestCase):
    def test_dry_season_months(self) -> None:
        for fecha in ("2025-01-15", "2025-11-30", "2025-04-01", "2025-12-31"):
            self.assertEqual(assign_season(fecha), "seca")

    def test_wet_season_months(self) -> None:
        for fecha in ("2025-05-01", "2025-06-19", "2025-10-31"):
            self.assertEqual(assign_season(fecha), "lluviosa")


class BuildSeasonalSummaryTest(unittest.TestCase):
    def test_groups_by_lake_and_season(self) -> None:
        temporal = [
            _temporal_row("amatitlan", "2025-01-10", 2.0),
            _temporal_row("amatitlan", "2025-02-10", 4.0),
            _temporal_row("amatitlan", "2025-06-10", 10.0),
        ]
        result = build_seasonal_summary(temporal)
        seca = next(r for r in result if r["lago"] == "amatitlan" and r["estacion"] == "seca")
        lluviosa = next(
            r for r in result if r["lago"] == "amatitlan" and r["estacion"] == "lluviosa"
        )
        self.assertEqual(seca["n_fechas"], 2)
        self.assertAlmostEqual(seca["cyano_promedio"], 3.0)
        self.assertEqual(lluviosa["n_fechas"], 1)
        self.assertEqual(set(r["lago"] for r in result), {"amatitlan"})

    def test_skips_empty_lake_season_combinations(self) -> None:
        temporal = [_temporal_row("amatitlan", "2025-01-10", 2.0)]
        result = build_seasonal_summary(temporal)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["estacion"], "seca")


if __name__ == "__main__":
    unittest.main()
