from __future__ import annotations

try:
    from .adquisicion import prepare_repository, validate_manifest
except ImportError:  # pragma: no cover - ejecución como archivo
    from adquisicion import prepare_repository, validate_manifest  # type: ignore


def main() -> int:
    summary = prepare_repository()
    rows = validate_manifest()
    print("#" * 64)
    print("# EJERCICIOS 1 Y 2: PREPARACIÓN LOCAL COMPLETA")
    print("#" * 64)
    print(f"Escenas oficiales: {len(rows)}")
    print(f"Bandas mínimas: {', '.join(summary['bands'])}")
    print(f"Manifiesto: {summary['manifest']}")
    print("No se realizó autenticación ni descarga.")
    print("Siguiente prueba: python src/adquisicion.py check-connection")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

