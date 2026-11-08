# -*- coding: utf-8 -*-
"""Carga bios_publicas.csv en la columna nueva `bio_larga` de la hoja
`vinculos` de cada planilla xlsx.

- No toca la columna `bio` (bio corta) ni ninguna otra.
- Empareja la fila propia de cada persona (Referente vacio) por nombre:
  exacto; si no, por tokens (p. ej. "Beauvoir" -> "Simone de Beauvoir").
- Solo escribe celdas vacias salvo --refrescar.
- Informa las personas sin bio y los emparejamientos dudosos (no adivina).

Uso:  python cargar_bios_xlsx.py [--refrescar] [--dry]
"""
import argparse
import csv
import re
import unicodedata
from pathlib import Path

import openpyxl

BASE = Path(__file__).resolve().parent
BIOS = BASE / 'bios_publicas.csv'
XLSX = [
    'actores_hollywood.xlsx',
    'datos_publicos.xlsx',
    'politicos_uy.xlsx',
    'influyentes_historia.xlsx',
    'historia_destacados.xlsx',
    'publicos_hoy.xlsx',
]
CAMPOS = ['bio', 'bio_larga']
MAX_CELDA = 32000

# alias manuales para nombres cortos que chocan con otra persona de la planilla
ALIAS = {
    'gandhi': 'Mohandas Gandhi',
}


def _norm(s):
    s = unicodedata.normalize('NFKD', str(s or ''))
    s = ''.join(c for c in s if not unicodedata.combining(c))
    return re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9 ]', ' ', s.lower())).strip()


def _tokens(s):
    return [t for t in _norm(s).split() if len(t) > 2]


def leer_bios():
    if not BIOS.exists():
        raise SystemExit(f'Falta {BIOS.name}; corre primero bajar_bios_publicas.py')
    with open(BIOS, encoding='utf-8-sig', newline='') as fh:
        filas = list(csv.DictReader(fh, delimiter=';'))
    return {r['nombre']: r for r in filas if r.get('nombre') and (r.get('bio_larga') or '').strip()}


def construir_indice(bios):
    exacto, por_token = {}, {}
    for nombre in bios:
        exacto[_norm(nombre)] = nombre
        toks = set(_tokens(nombre))
        for t in toks:
            por_token.setdefault(t, []).append(nombre)
    return exacto, por_token


def nombres_fichas():
    """nombres de la hoja fichas (para desempatar homonimos como Gandhi)."""
    out = set()
    for f in XLSX:
        p = BASE / f
        if not p.exists():
            continue
        wb = openpyxl.load_workbook(p, read_only=True)
        if 'fichas' in wb.sheetnames:
            for fila in wb['fichas'].iter_rows(min_row=2, values_only=True):
                for idx in (0, 5):
                    if len(fila) > idx and fila[idx]:
                        out.add(_norm(fila[idx]))
        wb.close()
    return out


def emparejar(nombre, exacto, por_token, bios, fichas):
    n = _norm(nombre)
    if n in exacto:
        return exacto[n], 'exacto'
    row_toks = set(_tokens(nombre))
    cands = set()
    for t in row_toks:
        cands.update(por_token.get(t, []))
    validos = [c for c in cands if row_toks and (row_toks <= set(_tokens(c)) or set(_tokens(c)) <= row_toks)]
    if len(validos) > 1 and fichas:
        preferidos = [c for c in validos if _norm(c) in fichas]
        if len(preferidos) == 1:
            return preferidos[0], 'tokens'
    if len(validos) == 1:
        return validos[0], 'tokens'
    if len(validos) > 1:
        # si uno contiene a todos los demas, es el bueno
        mejor = max(validos, key=lambda c: len(_tokens(c)))
        if all(set(_tokens(v)) <= set(_tokens(mejor)) for v in validos):
            return mejor, 'tokens'
        return None, 'ambiguo: ' + ' / '.join(sorted(validos)[:4])
    return None, 'sin match'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--refrescar', action='store_true', help='reescribe celdas ya cargadas')
    ap.add_argument('--dry', action='store_true', help='solo informa, no guarda')
    args = ap.parse_args()

    bios = leer_bios()
    exacto, por_token = construir_indice(bios)
    fichas = nombres_fichas()
    print(f'Bios disponibles: {len(bios)}')

    por_archivo = {}
    for f in XLSX:
        p = BASE / f
        if not p.exists():
            print(f'(falta {f})')
            continue
        wb = openpyxl.load_workbook(p)
        if 'vinculos' not in wb.sheetnames:
            print(f'{f}: sin hoja vinculos')
            continue
        ws = wb['vinculos']
        head = [str(ws.cell(row=1, column=c).value or '').strip().lower()
                for c in range(1, ws.max_column + 1)]
        c_nom = head.index('nombre') + 1 if 'nombre' in head else None
        c_ref = head.index('referente') + 1 if 'referente' in head else None
        if c_nom is None:
            print(f'{f}: vinculos sin columna Nombre')
            continue
        if 'bio_larga' in head:
            c_larga = head.index('bio_larga') + 1
        else:
            c_larga = ws.max_column + 1
            ws.cell(row=1, column=c_larga, value='bio_larga')
            ws.column_dimensions[openpyxl.utils.get_column_letter(c_larga)].width = 120

        escritas = sin_bio = ambiguas = 0
        faltan, dudas = [], []
        for r in range(2, ws.max_row + 1):
            nombre = str(ws.cell(row=r, column=c_nom).value or '').strip()
            if not nombre:
                continue
            ref = str(ws.cell(row=r, column=c_ref).value or '').strip() if c_ref else ''
            if ref:
                continue  # fila de familiar/vinculo, no es la persona
            actual = str(ws.cell(row=r, column=c_larga).value or '').strip()
            if actual and not args.refrescar:
                continue
            real, modo = emparejar(nombre, exacto, por_token, bios, fichas)
            if not real and _norm(nombre) in ALIAS:
                real, modo = ALIAS[_norm(nombre)], 'alias'
            if modo.startswith('ambiguo'):
                ambiguas += 1
                dudas.append(f'{nombre} [{modo}]')
                continue
            if not real:
                sin_bio += 1
                faltan.append(nombre)
                continue
            texto = str(bios[real].get('bio_larga') or '').strip()[:MAX_CELDA]
            if not texto:
                sin_bio += 1
                faltan.append(nombre)
                continue
            if not args.dry:
                ws.cell(row=r, column=c_larga, value=texto)
            escritas += 1
        if not args.dry and (escritas or 'bio_larga' not in head):
            wb.save(p)
        wb.close()
        por_archivo[f] = (escritas, sin_bio, ambiguas)
        print(f'{f}: {escritas} cargadas, {sin_bio} sin bio, {ambiguas} ambiguas')
        if faltan:
            print('   sin bio:', ', '.join(sorted(faltan)[:25]) + ('...' if len(faltan) > 25 else ''))
        if dudas:
            print('   revisar:', '; '.join(dudas[:15]) + ('...' if len(dudas) > 15 else ''))

    print('Total cargadas:', sum(v[0] for v in por_archivo.values()),
          '| sin bio:', sum(v[1] for v in por_archivo.values()),
          '| ambiguas:', sum(v[2] for v in por_archivo.values()))


if __name__ == '__main__':
    main()
