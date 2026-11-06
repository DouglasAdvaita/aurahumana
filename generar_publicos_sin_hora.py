"""Genera publicos_sin_hora.xlsx a partir de personas_publicas.csv.

Para cada persona publica SIN hora de nacimiento, calcula el Tipo y Perfil de
las 24 horas del dia en su fecha y lugar, agrupa las horas contiguas con el
mismo Tipo y Perfil y se queda con el periodo mas largo (el mas probable).
La hora asignada es la version muestreada mas cercana al centro de ese
periodo; si ninguna version cae dentro, se usa el centro del periodo.

El xlsx queda con la misma estructura que las otras planillas publicas:
- datos, vinculos y fichas: las 460 personas calculadas a su hora asignada
- test, clan y parejas: vacias con cabecera
- sin_hora: solo nombre y hora (el resumen pedido)

Uso:  python generar_publicos_sin_hora.py
"""
import collections
import csv
import re
import unicodedata
from datetime import date
from pathlib import Path

import openpyxl
from openpyxl.styles import Font

import app as A

BASE = Path(__file__).resolve().parent
ENTRADA = BASE / 'personas_publicas.csv'
FOTOS = BASE / 'fotos_publicas.csv'
SALIDA = BASE / 'publicos_sin_hora.xlsx'

DATOS_HEAD = ['Nombre', 'Puerta', 'Linea', 'C/I']
VINC_HEAD = ['fecha', 'hora', 'Edad', 'Lugar', 'Nombre',
             'vinculo con el referente', 'Referente', 'bio']
TEST_HEAD = ['nombre', 'fecha', 'hora', 'lugar', 'triada', 'modo', 'foco',
             'sensorial', 'rutina', 'social', 'cuerpo', 'diges', 'sueno',
             'busco', 'eneatipo', 'dosha_dom', 'vida', 'destino', 'solar',
             'luna', 'asc', 'informe']
CLAN_HEAD = ['P1', 'rol', 'familiar']
PUB_HEAD = ['nombre', 'categoria', 'fecha', 'hora', 'lugar', 'nombre_base',
            'copia', 'hora_usada', 'lat', 'lon', 'tz', 'perfil', 'tipo',
            'autoridad', 'definicion', 'puertas_incon', 'puertas_con',
            'lineas_incon', 'lineas_con', 'canales', 'centros', 'warnings',
            'descripcion', 'foto']
PAREJA_HEAD = ['nombre', 'categoria', 'fecha', 'hora', 'lugar', 'pareja_de',
               'dinamica', 'duracion', 'ruptura', 'hijos']


def _norm(s):
    return (s or '').strip().lower()


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


def _edad(fecha):
    try:
        d, m, a = [int(x) for x in str(fecha).split('/')[:3]]
    except (ValueError, TypeError):
        return ''
    hoy = date.today()
    return str(hoy.year - a - ((hoy.month, hoy.day) < (m, d)))


def _fotos():
    """nombre_base normalizado -> 'Publicos/<archivo>.jpg'."""
    mapa = {}
    try:
        with open(FOTOS, encoding='utf-8-sig', newline='') as f:
            for r in csv.DictReader(f, delimiter=';'):
                k = _norm(r.get('nombre_base'))
                foto = (r.get('foto') or '').strip()
                if k and foto:
                    mapa[k] = foto
    except FileNotFoundError:
        pass
    return mapa


def _clave_orden(nombre):
    s = unicodedata.normalize('NFKD', nombre).encode('ascii', 'ignore').decode()
    return s.lower()


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


def _diseno(fecha, lugar, lat, lon, tz, hora):
    """Tipo/perfil/puertas/canales/centros completos para fecha+hora(local)."""
    datos = {'fecha': fecha, 'lugar': lugar, 'lat': lat, 'lon': lon, 'tz': tz,
             'hora': hora}
    jd, _, _, err = A._parse_nacimiento(datos)
    if err:
        return None
    personalidad = A._puertas_momento(jd, topocentrico=False)
    diseno = A._puertas_momento(A._jd_diseno(jd), topocentrico=False)
    perfil = A._perfil_de_lineas(personalidad[0]['linea'], diseno[0]['linea'])
    puertas = set(d['puerta'] for d in personalidad) | set(d['puerta'] for d in diseno)
    canales = A._hd_canales_de_puertas(puertas)
    centros = A._hd_centros_definidos(canales)
    tipo, autoridad = A._hd_tipo_autoridad(centros, canales)
    definicion = A._hd_definicion(centros, canales)
    return {
        'perfil': perfil, 'tipo': tipo, 'autoridad': autoridad,
        'definicion': definicion,
        'puertas_incon': [d['puerta'] for d in diseno],
        'puertas_con': [d['puerta'] for d in personalidad],
        'lineas_incon': [d['linea'] for d in diseno],
        'lineas_con': [d['linea'] for d in personalidad],
        'canales': canales, 'centros': centros,
    }


def calcular():
    with open(ENTRADA, encoding='utf-8-sig', newline='') as f:
        filas = list(csv.DictReader(f, delimiter=';'))
    fotos = _fotos()

    grupos = collections.defaultdict(dict)
    for r in filas:
        if (r.get('hora') or '').strip():
            continue
        base, indice, _ = _split_variante(r.get('nombre'))
        nombre = (r.get('nombre_base') or base).strip() or base
        clave = (nombre, (r.get('fecha') or '').strip())
        # Una misma persona puede venir repetida en dos categorias: se
        # conserva una version por indice/hora.
        grupos[clave].setdefault((indice, (r.get('hora_usada') or '').strip()), r)

    personas = []
    avisos = []
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
            avisos.append((nombre, 'sin datos de fecha/lugar, omitida'))
            continue

        runs = _periodos(serie)
        muestras = []
        for (indice, hora_txt), _r in variantes.items():
            m = _minutos(hora_txt)
            if m is not None:
                muestras.append((m, hora_txt, indice))

        def dentro(run, m):
            return (m // 60) in run[2]

        def largo(run):
            return len(run[2])

        runs.sort(key=lambda r: (-largo(r),
                                 -sum(1 for m, _, _ in muestras if dentro(r, m)),
                                 r[2][0]))
        mejor = runs[0]
        horas = mejor[2]
        centro = 12 if len(horas) == 24 else (horas[0] + len(horas) // 2) % 24

        candidatas = [(m, txt, indice) for m, txt, indice in muestras if dentro(mejor, m)]
        if candidatas:
            def distancia(item):
                h = item[0] // 60
                d = abs(h - centro)
                return min(d, 24 - d)
            candidatas.sort(key=lambda item: (distancia(item), item[0]))
            hora = candidatas[0][1]
            copia = f'{candidatas[0][2]}/{len(variantes)}' if candidatas[0][2] else ''
        else:
            hora = f'{centro:02d}:00'
            copia = ''
            avisos.append((nombre, hora))

        dis = _diseno(r0['fecha'], r0['lugar'], r0['lat'], r0['lon'], r0['tz'], hora)
        if not dis:
            avisos.append((nombre, 'sin diseno, omitida'))
            continue

        personas.append({
            'nombre': nombre,
            'categoria': (r0.get('categoria') or '').strip(),
            'fecha': (r0.get('fecha') or '').strip(),
            'hora': hora,
            'copia': copia,
            'lugar': (r0.get('lugar') or '').strip(),
            'lat': (r0.get('lat') or '').strip(),
            'lon': (r0.get('lon') or '').strip(),
            'tz': (r0.get('tz') or '').strip(),
            'descripcion': (r0.get('descripcion') or '').strip(),
            'foto': fotos.get(_norm(nombre), ''),
            **dis,
        })

    personas.sort(key=lambda p: _clave_orden(p['nombre']))
    return personas, avisos


def _filas_hojas(personas):
    datos, vinculos, fichas, sin_hora = [], [], [], []
    for p in personas:
        for puerta, linea in zip(p['puertas_incon'], p['lineas_incon']):
            datos.append([p['nombre'], puerta, linea, 'Inconsciente'])
        for puerta, linea in zip(p['puertas_con'], p['lineas_con']):
            datos.append([p['nombre'], puerta, linea, 'Consciente'])
        vinculos.append([p['fecha'], p['hora'], _edad(p['fecha']), p['lugar'],
                         p['nombre'], '', '', p['descripcion']])
        fichas.append([p['nombre'], p['categoria'], p['fecha'], '', p['lugar'],
                       p['nombre'], p['copia'], p['hora'], p['lat'], p['lon'],
                       p['tz'], p['perfil'], p['tipo'], p['autoridad'],
                       p['definicion'],
                       ','.join(str(x) for x in p['puertas_incon']),
                       ','.join(str(x) for x in p['puertas_con']),
                       ','.join(str(x) for x in p['lineas_incon']),
                       ','.join(str(x) for x in p['lineas_con']),
                       '|'.join(p['canales']),
                       '|'.join(sorted(p['centros'])),
                       '', p['descripcion'], p['foto']])
        sin_hora.append([p['nombre'], p['hora']])
    hojas = [
        ('datos', DATOS_HEAD, datos),
        ('vinculos', VINC_HEAD, vinculos),
        ('test', TEST_HEAD, []),
        ('clan', CLAN_HEAD, []),
        ('fichas', PUB_HEAD, fichas),
        ('parejas', PAREJA_HEAD, []),
        ('sin_hora', ['nombre', 'hora'], sin_hora),
    ]
    return hojas


def escribir(hojas, path=SALIDA):
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for titulo, cabecera, cuerpo in hojas:
        ws = wb.create_sheet(titulo)
        ws.append(cabecera)
        for fila in cuerpo:
            ws.append(fila)
        for c in ws[1]:
            c.font = Font(bold=True)
        ws.freeze_panes = 'A2'
        for col, ancho in zip('ABC', (34, 12, 10)):
            ws.column_dimensions[col].width = ancho
    wb.save(path)


def main():
    personas, avisos = calcular()
    escribir(_filas_hojas(personas))
    print(f'{SALIDA.name}: {len(personas)} personas sin hora')
    print(f'  datos: {len(personas) * 26} filas | vinculos: {len(personas)} | fichas: {len(personas)}')
    if avisos:
        print(f'  avisos: {len(avisos)}')
        for nombre, detalle in avisos[:10]:
            print(f'    {nombre}: {detalle}')


if __name__ == '__main__':
    main()
