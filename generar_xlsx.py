"""Genera los xlsx de intercambio desde los CSV actuales, sin tocar la app.

- datos_privados.xlsx: hojas datos, vinculos, test, clan (los 4 que la app
  escribe/lee). Todas las celdas como texto para que Excel no convierta
  fechas, horas ni puertas tipo '41.1'. Sin fórmulas.
- diccionario.xlsx: hojas con los diccionarios y autoconocimiento
  (centros, canales, puertas, lineas_popup, tipos, autoridades, perfiles,
  definiciones, cruces, eneatipos, doshas, numerologia, natal, natal_planetas).

Uso:  python generar_xlsx.py
"""
import csv
import io
from pathlib import Path

import openpyxl
from openpyxl.styles import Font

BASE = Path(__file__).resolve().parent


def _decodificar(raw):
    """Elige el mejor encoding para el byte buffer (orden similar al que usa app.py)."""
    for enc in ('utf-8-sig', 'utf-8', 'cp1252', 'latin-1'):
        try:
            return raw.decode(enc), enc
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode('latin-1', errors='replace'), 'latin-1+replace'


def _leer_tabla(nombre_csv, separadores=(';', '\t')):
    """Devuelve (filas, separador usado, encoding usado). Tolera ; o tab."""
    texto, enc = _decodificar((BASE / nombre_csv).read_bytes())
    filas = None
    sep_usado = separadores[0]
    for sep in separadores:
        leidas = list(csv.reader(io.StringIO(texto), delimiter=sep))
        if len(leidas) >= 2 and len(leidas[0]) >= 2:
            filas, sep_usado = leidas, sep
            break
    if filas is None:
        filas = list(csv.reader(io.StringIO(texto), delimiter=separadores[0]))
    filas = [f for f in filas if any((c or '').strip() for c in f)]
    return filas, sep_usado, enc


def _volcar(wb, titulo, filas):
    ws = wb.create_sheet(titulo)
    for fila in filas:
        ws.append([c if c is not None else '' for c in fila])
    for celda in ws[1]:
        celda.font = Font(bold=True)
    ws.freeze_panes = 'A2'


def _guardar(nombre, hojas):
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for titulo, csvs in hojas:
        filas, sep, enc = _leer_tabla(csvs)
        _volcar(wb, titulo, filas)
        print(f"{titulo:15} <- {csvs:22} sep={sep!r} enc={enc:12} filas={len(filas)}")
    wb.save(BASE / nombre)
    print(f"-> {nombre}  ({len(hojas)} hojas)\n")


if __name__ == '__main__':
    print("== datos_privados.xlsx ==")
    _guardar('datos_privados.xlsx', [
        ('datos', 'datos.csv'),
        ('vinculos', 'vinculos.csv'),
        ('test', 'test.csv'),
        ('clan', 'clan.csv'),
    ])
    print("== diccionario.xlsx ==")
    _guardar('diccionario.xlsx', [
        ('centros', 'centros.csv'),
        ('canales', 'canales.csv'),
        ('puertas', 'puertas.csv'),
        ('lineas_popup', 'lineas_popup.csv'),
        ('tipos', 'tipos.csv'),
        ('autoridades', 'autoridades.csv'),
        ('perfiles', 'perfiles.csv'),
        ('definiciones', 'definiciones.csv'),
        ('cruces', 'cruces.csv'),
        ('eneatipos', 'eneatipos.csv'),
        ('doshas', 'doshas.csv'),
        ('numerologia', 'numerologia.csv'),
        ('natal', 'natal.csv'),
        ('natal_planetas', 'natal_planetas.csv'),
    ])
    print("Listo.")