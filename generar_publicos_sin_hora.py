"""Genera publicos_sin_hora.xlsx a partir de personas_publicas.csv.

Para cada persona publica SIN hora de nacimiento, calcula el Tipo y Perfil de
las 24 horas del dia en su fecha y lugar, agrupa las horas contiguas con el
mismo Tipo y Perfil y se queda con el periodo mas largo (el mas probable).
La hora que se guarda es la version muestreada mas cercana al centro de ese
periodo; si ninguna version cae dentro, se usa el centro del periodo.

Salida: publicos_sin_hora.xlsx con la hoja 'sin_hora' (nombre y hora) y las
cuatro hojas que exige la app para aceptarla como fuente (datos, vinculos,
test y clan), vacias con su cabecera.

Uso:  python generar_publicos_sin_hora.py
"""
import collections
import csv
import re
import unicodedata
from pathlib import Path

import openpyxl
from openpyxl.styles import Font

import app as A

BASE = Path(__file__).resolve().parent
ENTRADA = BASE / 'personas_publicas.csv'
SALIDA = BASE / 'publicos_sin_hora.xlsx'

# Hojas que la app exige para aceptar un xlsx como fuente (vacias, con cabecera).
HOJAS_VACIAS = [
    ('datos', ['Nombre', 'Puerta', 'Linea', 'C/I']),
    ('vinculos', ['fecha', 'hora', 'Edad', 'Lugar', 'Nombre',
                  'vinculo con el referente', 'Referente', 'bio']),
    ('test', ['nombre', 'fecha', 'hora', 'lugar', 'triada', 'modo', 'foco',
              'sensorial', 'rutina', 'social', 'cuerpo', 'diges', 'sueno',
              'busco', 'eneatipo', 'dosha_dom', 'vida', 'destino', 'solar',
              'luna', 'asc', 'informe']),
    ('clan', ['P1', 'rol', 'familiar']),
]


def _split_variante(nombre):
    """'Mark Zuckerberg 2/3' -> ('Mark Zuckerberg', 2, 3); sin sufijo -> (nombre, None, None)."""
    m = re.match(r'^(.*?)\s+(\d+)/(\d+)$', (nombre or '').strip())
    if m:
        return m.group(1).strip(), int(m.group(2)), int(m.group(3))
    return (nombre or '').strip(), None, None


def _minutos(hora):
    try:
        h, m = str(hora).split(':')
        return int(h) * 60 + int(m)
    except (ValueError, AttributeError):
        return None


def _periodos(serie):
    """[(hora, tipo, perfil)] -> periodos contiguos [(tipo, perfil, [horas])],
    uniendo el primero con el ultimo si comparten Tipo y Perfil (cruza medianoche)."""
    runs = []
    for h, tipo, perfil in serie:
        if runs and runs[-1][0] == tipo and runs[-1][1] == perfil:
            runs[-1][2].append(h)
        else:
            runs.append([tipo, perfil, [h]])
    if len(runs) > 1 and runs[0][0] == runs[-1][0] and runs[0][1] == runs[-1][1]:
        ultimo = runs.pop()
        runs[0][2] = ultimo[2] + runs[0][2]
    return runs


def _clave_orden(nombre):
    s = unicodedata.normalize('NFKD', nombre).encode('ascii', 'ignore').decode()
    return s.lower()


def calcular():
    with open(ENTRADA, encoding='utf-8-sig', newline='') as f:
        filas = list(csv.DictReader(f, delimiter=';'))

    grupos = collections.defaultdict(dict)
    for r in filas:
        if (r.get('hora') or '').strip():
            continue
        base, indice, _ = _split_variante(r.get('nombre'))
        nombre = (r.get('nombre_base') or base).strip() or base
        clave = (nombre, (r.get('fecha') or '').strip())
        variantes = grupos[clave]
        # Una misma persona puede venir repetida en dos categorias: se
        # conserva una version por indice/hora.
        k = (indice, (r.get('hora_usada') or '').strip())
        variantes.setdefault(k, r)

    salida = []
    sin_variante = []
    for (nombre, _), variantes in grupos.items():
        r0 = next(iter(variantes.values()))
        datos = {'fecha': r0['fecha'], 'lugar': r0['lugar'], 'lat': r0['lat'],
                 'lon': r0['lon'], 'tz': r0['tz']}
        serie = []
        for h in range(24):
            datos['hora'] = f'{h:02d}:00'
            jd, _, _, err = A._parse_nacimiento(datos)
            if err:
                serie = []
                break
            tipo, _, perfil, _ = A._tipo_perfil_en_jd(jd)
            serie.append((h, tipo, perfil))
        if not serie:
            sin_variante.append((nombre, 'sin datos de fecha/lugar'))
            continue

        runs = _periodos(serie)
        muestras = []
        for (_, hora_txt), r in variantes.items():
            m = _minutos(hora_txt)
            if m is not None:
                muestras.append((m, hora_txt))

        def dentro(run, m):
            return (m // 60) in run[2]

        def largo(run):
            return len(run[2])

        runs.sort(key=lambda r: (-largo(r),
                                 -sum(1 for m, _ in muestras if dentro(r, m)),
                                 r[2][0]))
        mejor = runs[0]
        horas = mejor[2]
        centro = 12 if len(horas) == 24 else (horas[0] + len(horas) // 2) % 24

        candidatas = [(m, txt) for m, txt in muestras if dentro(mejor, m)]
        if candidatas:
            def distancia(item):
                h = item[0] // 60
                d = abs(h - centro)
                return min(d, 24 - d)
            candidatas.sort(key=lambda item: (distancia(item), item[0]))
            hora = candidatas[0][1]
        else:
            hora = f'{centro:02d}:00'
            sin_variante.append((nombre, hora))

        salida.append((nombre, hora))

    salida.sort(key=lambda x: _clave_orden(x[0]))
    return salida, sin_variante


def escribir(filas, path=SALIDA):
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for titulo, cabecera in HOJAS_VACIAS:
        ws = wb.create_sheet(titulo)
        ws.append(cabecera)
        for c in ws[1]:
            c.font = Font(bold=True)
        ws.freeze_panes = 'A2'
    ws = wb.create_sheet('sin_hora')
    ws.append(['nombre', 'hora'])
    for nombre, hora in filas:
        ws.append([nombre, hora])
    for c in ws[1]:
        c.font = Font(bold=True)
    ws.freeze_panes = 'A2'
    ws.column_dimensions['A'].width = 34
    ws.column_dimensions['B'].width = 8
    wb.save(path)


def main():
    filas, avisos = calcular()
    escribir(filas)
    print(f'{SALIDA.name}: {len(filas)} personas sin hora')
    if avisos:
        print(f'  {len(avisos)} sin version dentro del periodo (se uso el centro):')
        for nombre, hora in avisos[:10]:
            print(f'    {nombre}: {hora}')


if __name__ == '__main__':
    main()
