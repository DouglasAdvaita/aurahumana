"""Crea los CSV personales vacios (solo cabecera) si no existen.

Se ejecuta al iniciar (INICIAR.cmd) para que un clon nuevo funcione.
No toca archivos existentes.
"""
from pathlib import Path
import shutil


BASE = Path(__file__).resolve().parent
PLANT = BASE / "plantillas"


def main():
    if not PLANT.is_dir():
        print("Aviso: no existe la carpeta plantillas/.")
        return
    creados = []
    for src in sorted(PLANT.glob("*.csv")):
        dst = BASE / src.name
        if not dst.exists():
            shutil.copy2(src, dst)
            creados.append(src.name)
    if creados:
        print("Creados (vacios):", ", ".join(creados))
    else:
        print("Datos ya presentes; no se toco nada.")


if __name__ == "__main__":
    main()
