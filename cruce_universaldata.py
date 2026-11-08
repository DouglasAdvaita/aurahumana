# -*- coding: utf-8 -*-
"""Cruza las personas de las planillas RAVE con los personajes de
UniversalData (Personas.mdb) y arma la lista de altas.

Entrada:
  --ud     CSV exportado de la tabla Personaje (cod;nombre;tablaasoc;nro)
  --bios   bios_publicas.csv (opcional; para las altas)
Salida:
  ud_cruce.csv   nombre_rave;nombre_ud;estado  (exacto | nombre_completo | dudoso | falta)
  ud_altas.csv   nombre;bio  (solo faltantes con biografia, sin ';' ni saltos)

Uso:
  python cruce_universaldata.py --ud ud_personajes.csv
"""
import argparse
import csv
import re
import unicodedata
from pathlib import Path

import openpyxl

BASE = Path(__file__).resolve().parent
XLSX = [
    'actores_hollywood.xlsx',
    'datos_publicos.xlsx',
    'politicos_uy.xlsx',
    'influyentes_historia.xlsx',
    'historia_destacados.xlsx',
    'publicos_hoy.xlsx',
]


def _norm(s):
    s = unicodedata.normalize('NFKD', str(s or ''))
    s = ''.join(c for c in s if not unicodedata.combining(c))
    return re.sub(r'[^a-z0-9 ]', ' ', s.lower()).strip()


def _tokens(s):
    return [t for t in _norm(s).split() if len(t) > 2]


def nombres_rave():
    vistos = set()
    for f in XLSX:
        p = BASE / f
        if not p.exists():
            continue
        wb = openpyxl.load_workbook(p, read_only=True)
        for hoja in ('fichas', 'sin_hora'):
            if hoja not in wb.sheetnames:
                continue
            for fila in wb[hoja].iter_rows(min_row=2, values_only=True):
                nb = str(fila[5] or '').strip() if len(fila) > 5 else ''
                if nb:
                    vistos.add(nb)
        wb.close()
    return sorted(vistos, key=_norm)


def leer_ud(path):
    nombres = []
    with open(path, encoding='utf-8-sig', newline='') as fh:
        for r in csv.DictReader(fh, delimiter=';'):
            n = (r.get('nombre') or '').strip()
            if n:
                nombres.append(n)
    return nombres


def leer_bios(path):
    if not path.exists():
        return {}
    with open(path, encoding='utf-8-sig', newline='') as fh:
        return {r['nombre']: r for r in csv.DictReader(fh, delimiter=';')
                if r.get('nombre') and (r.get('bio_larga') or '').strip()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--ud', default='ud_personajes.csv')
    ap.add_argument('--bios', default='bios_publicas.csv')
    ap.add_argument('--cruce', default='ud_cruce.csv')
    ap.add_argument('--altas', default='ud_altas.csv')
    args = ap.parse_args()

    ud = leer_ud(Path(args.ud))
    if not ud:
        raise SystemExit('El CSV de UniversalData esta vacio')
    exacto, por_token = {}, {}
    for n in ud:
        exacto[_norm(n)] = n
        for t in set(_tokens(n)):
            por_token.setdefault(t, []).append(n)

    bios = leer_bios(Path(args.bios))
    filas, altas, resumen = [], [], {'exacto': 0, 'nombre_completo': 0, 'dudoso': 0, 'falta': 0}
    for nombre in nombres_rave():
        k = _norm(nombre)
        tk = set(_tokens(nombre))
        if k in exacto:
            filas.append((nombre, exacto[k], 'exacto'))
            resumen['exacto'] += 1
            continue
        cands = set()
        for t in tk:
            cands.update(por_token.get(t, []))
        completos = [c for c in cands if tk and tk <= set(_tokens(c))]
        if len(completos) == 1:
            filas.append((nombre, completos[0], 'nombre_completo'))
            resumen['nombre_completo'] += 1
            continue
        if len(completos) > 1:
            filas.append((nombre, ' / '.join(sorted(completos)[:3]), 'dudoso'))
            resumen['dudoso'] += 1
            continue
        filas.append((nombre, '', 'falta'))
        resumen['falta'] += 1
        b = bios.get(nombre)
        if b:
            texto = re.sub(r'\s+', ' ', str(b.get('bio_larga') or '')).strip()
            texto = texto.replace(';', ',')
            altas.append((nombre, texto))

    with open(args.cruce, 'w', encoding='utf-8-sig', newline='') as fh:
        w = csv.writer(fh, delimiter=';')
        w.writerow(['nombre_rave', 'nombre_ud', 'estado'])
        w.writerows(filas)

    with open(args.altas, 'w', encoding='utf-8-sig', newline='') as fh:
        w = csv.writer(fh, delimiter=';', quoting=csv.QUOTE_MINIMAL)
        w.writerow(['nombre', 'bio'])
        w.writerows(altas)

    print(f'UniversalData: {len(ud)} personajes | RAVE: {len(nombres_rave())} personas')
    print(f"exacto: {resumen['exacto']} | nombre completo: {resumen['nombre_completo']} "
          f"| dudoso: {resumen['dudoso']} | falta: {resumen['falta']}")
    print(f'Altas preparadas (faltantes con bio): {len(altas)} -> {args.altas}')
    print(f'Detalle del cruce: {args.cruce}')


if __name__ == '__main__':
    main()
