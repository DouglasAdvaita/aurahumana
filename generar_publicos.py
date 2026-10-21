"""Genera datos_publicos.xlsx desde personas_publicas.csv y parejas_publicas.csv.

Formato igual a datos_privados.xlsx para Cargarlo indistintamente:
- datos:    personas publicas con hora (13 con + 13 incon por persona, nombre_base)
- vinculos: una fila por persona (fecha/hora/lugar + edad calculada), una por
            pareja (tipo 'pareja') y una por hijo reconstruido (tipo 'hijo')
- test:     cabecera vacia (sin autoconocimiento publico)
- clan:     reconstruido: pareja_1/2... y menor_1/2... desde parejas_publicas
Hojas extra de revision (la app solo usaria las 4 de arriba):
- fichas:   ficha completa de cada persona con hora
- parejas:  registros crudos de parejas_publicas.csv
- sin_hora: personas sin hora (candidatos para el proximo cuestionario)

Uso:  python generar_publicos.py
"""
import csv
import re
from collections import defaultdict
from datetime import date
from pathlib import Path

import openpyxl
from openpyxl.styles import Font

BASE = Path(__file__).resolve().parent

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


def _rows(nombre_csv):
    return list(csv.DictReader(open(BASE / nombre_csv, encoding='utf-8-sig'),
                               delimiter=';'))


def _norm(s):
    return (s or '').strip().lower()


def _lista(v):
    return [x.strip() for x in (v or '').split(',') if x.strip()]


def _fotos():
    """nombre_base normalizado -> 'Publicos/<archivo>.jpg' (o {} si no existe)."""
    mapa = {}
    try:
        for r in _rows('fotos_publicas.csv'):
            k = _norm(r.get('nombre_base'))
            f = (r.get('foto') or '').strip()
            if k and f:
                mapa[k] = f
    except FileNotFoundError:
        pass
    return mapa


def _edad(fecha, hoy=None):
    """Edad en años desde fecha dd/mm/aaaa (o aaaa-mm-dd) hasta hoy."""
    f = str(fecha or '').strip()
    try:
        if '/' in f:
            d, m, a = (int(x) for x in f.split('/')[:3])
        elif len(f) >= 10 and f[4] == '-' and f[7] == '-':
            a, m, d = int(f[0:4]), int(f[5:7]), int(f[8:10])
        else:
            return ''
    except (ValueError, TypeError):
        return ''
    hoy = hoy or date.today()
    return str(hoy.year - a - ((hoy.month, hoy.day) < (m, d)))


_SIN_NOMBRE = {'0', 'nd', 'no', 'ninguno', 'ningun', 'ninguna', 'vigente',
               '0 juntos', '0 sin hijos', 'sin hijos', 'sin hijo',
               'sin hijos juntos', 'no tuvo hijos', 'no tuvieron hijos',
               '0 en comun', '0 en común'}


def _parse_hijos(raw):
    """Extrae nombres de hijos de la columna 'hijos'. Best-effort: [] si solo
    hay conteos del tipo '2 hijos', '0', 'ND'. Los nombres compuestos sin
    separadores se conservan como un unico nombre."""
    s = re.sub(r'\s+', ' ', str(raw or '').strip())
    if not s:
        return []
    low = s.lower()
    if low in _SIN_NOMBRE or low.startswith('0 en com') or low.startswith('nd'):
        return []
    if re.fullmatch(r'\d+\s*(hij[oa]s?|en com[úu]n|previos|juntos|mas|más)?\s*', low):
        return []
    # quitar conteo inicial: "3 hijos: X", "2 Jaden y Willow", "1 adoptada: Maria", "4: X"
    s2 = re.sub(r'^\s*\d+\s*(hij[oa]s?|hijastr[oa]s?|adoptad[oa]s?|en com[úu]n'
                r'|juntos|previos)?\s*[:.\-]?\s*', '', s)
    # numeros que separan hijos entre medias -> coma
    s2 = re.sub(r'\s+\d+\s*[:.\-]?\s*', ' , ', s2)
    partes = re.split(r'\s*[;,]\s*|\s+(?:y|e|mas|más)\s+|\s*,\s*', s2)
    out = []
    for p in partes:
        p = p.strip().strip('.,').strip()
        if not p:
            continue
        if p.lower() in ('y', 'e', 'o', 'mas', 'más') or re.fullmatch(r'\d+', p):
            continue
        p = re.sub(r'^(adoptad[oa]s?|hijastr[oa]s?)\s*', '', p, flags=re.I)
        p = re.sub(r'\s*(adoptad[oa]s?|hijastr[oa]s?)$', '', p, flags=re.I).strip()
        if len(p) >= 3 and re.search(r'[A-Za-zÁÉÍÓÚáéíóúñÑ]', p):
            out.append(p)
    return out


def construir(pub, par, categoria=None):
    """Arma las hojas de la app. Si categoria no es None, filtra personas y
    parejas de ese grupo. Devuelve (hojas, info)."""
    if categoria is not None:
        pub = [p for p in pub if (p.get('categoria') or '').strip() == categoria]
        par = [r for r in par if (r.get('categoria') or '').strip() == categoria]
    fotos = _fotos()
    for p in pub:
        p['foto'] = fotos.get(_norm(p.get('nombre_base')), '')
    con_hora = [p for p in pub if (p.get('hora') or '').strip()]
    sin_hora = [p for p in pub if not (p.get('hora') or '').strip()]
    por_nombre = {}
    for p in con_hora:
        clave = _norm(p.get('nombre_base') or p.get('nombre'))
        if clave:
            por_nombre.setdefault(clave, p)

    # --- hoja datos: 13 con + 13 incon por persona con hora ---
    datos = []
    for p in con_hora:
        nombre = (p.get('nombre_base') or p.get('nombre') or '').strip()
        pin = _lista(p.get('puertas_incon'))
        pco = _lista(p.get('puertas_con'))
        lin = _lista(p.get('lineas_incon'))
        lco = _lista(p.get('lineas_con'))
        for i, pu in enumerate(pin):
            datos.append([nombre, pu, lin[i] if i < len(lin) else '', 'Inconsciente'])
        for i, pu in enumerate(pco):
            datos.append([nombre, pu, lco[i] if i < len(lco) else '', 'Consciente'])

    # --- hoja vinculos: 1 fila por persona + parejas + hijos ---
    vinculos = []
    for p in con_hora:
        nombre = (p.get('nombre_base') or p.get('nombre') or '').strip()
        if nombre:
            vinculos.append([(p.get('fecha') or ''), (p.get('hora') or ''),
                             _edad(p.get('fecha')), (p.get('lugar') or ''),
                             nombre, '', '', (p.get('descripcion') or '').strip()])
    vistos_pareja = set()
    vistos_hijo = set()
    clan = set()
    pareja_idx = defaultdict(int)
    menor_idx = defaultdict(int)
    parejas_con_nombre = 0
    hijos_con_nombre = 0
    for r in par:
        nom = (r.get('nombre') or '').strip()
        ref = (r.get('pareja_de') or '').strip()
        if not nom or not ref:
            continue
        pn = por_nombre.get(_norm(nom))
        pr = por_nombre.get(_norm(ref))
        if pn is None and pr is None:
            continue
        hijos = _parse_hijos(r.get('hijos'))
        if hijos:
            parejas_con_nombre += 1
            hijos_con_nombre += len(hijos)
        lado = pn or pr
        clave = tuple(sorted([_norm(nom), _norm(ref)]))
        if clave not in vistos_pareja:
            vistos_pareja.add(clave)
            vinculos.append([(lado.get('fecha') or ''), (lado.get('hora') or ''),
                             _edad(lado.get('fecha')), (lado.get('lugar') or ''),
                             nom, 'pareja', ref, ''])
        for who in (pn, pr):
            if who is None:
                continue
            p1 = (who.get('nombre_base') or who.get('nombre') or '').strip()
            pareja_idx[p1] += 1
            clan.add((p1, f'pareja_{pareja_idx[p1]}', ref if who is pn else nom))
            for ch in hijos:
                menor_idx[p1] += 1
                clan.add((p1, f'menor_{menor_idx[p1]}', ch))
                clave_h = (_norm(ch), _norm(p1))
                if clave_h not in vistos_hijo:
                    vistos_hijo.add(clave_h)
                    vinculos.append(['', '', '', '', ch, 'hijo', p1, ''])

    clan_rows = sorted(list(clan), key=lambda x: (x[0].lower(), x[1]))

    # --- hojas extra de revision ---
    fichas = [[p.get(k, '') or '' for k in PUB_HEAD] for p in con_hora]
    sin_hora_rows = [[p.get(k, '') or '' for k in PUB_HEAD] for p in sin_hora]
    parejas_rows = [[r.get(k, '') or '' for k in PAREJA_HEAD] for r in par]

    hojas = [
        ('datos', DATOS_HEAD, datos),
        ('vinculos', VINC_HEAD, vinculos),
        ('test', TEST_HEAD, []),
        ('clan', CLAN_HEAD, clan_rows),
        ('fichas', PUB_HEAD, fichas),
        ('parejas', PAREJA_HEAD, parejas_rows),
        ('sin_hora', PUB_HEAD, sin_hora_rows),
    ]
    info = {'con_hora': len(con_hora), 'sin_hora': len(sin_hora),
            'datos': len(datos), 'v_personas': len(con_hora),
            'v_parejas': len(vistos_pareja), 'v_hijos': len(vistos_hijo),
            'parejas_hijos': (parejas_con_nombre, hijos_con_nombre),
            'clan': len(clan_rows), 'fichas': len(fichas),
            'parejas': len(parejas_rows)}
    return hojas, info


def escribir_xlsx(path, hojas):
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for titulo, head, cuerpo in hojas:
        ws = wb.create_sheet(titulo)
        ws.append(head)
        for f in cuerpo:
            ws.append(f)
    for titulo in wb.sheetnames:
        for c in wb[titulo][1]:
            c.font = Font(bold=True)
        wb[titulo].freeze_panes = 'A2'
    wb.save(path)


def main():
    pub = _rows('personas_publicas.csv')
    par = _rows('parejas_publicas.csv')

    hojas, info = construir(pub, par)
    try:
        escribir_xlsx(BASE / 'datos_publicos.xlsx', hojas)
        print('datos_publicos.xlsx (global): con hora %d, datos %d, '
              'parejas %d, hijos %d, clan %d'
              % (info['con_hora'], info['datos'], info['v_parejas'],
                 info['v_hijos'], info['clan']))
    except PermissionError:
        print('datos_publicos.xlsx ABIERTO en Excel -> cerralo y reintentá '
              '(omitido)')

    categorias = sorted({(p.get('categoria') or '').strip()
                         for p in pub if (p.get('categoria') or '').strip()})
    for cat in categorias:
        hojas, info = construir(pub, par, categoria=cat)
        if not info['con_hora']:
            print('  %-24s sin personas con hora -> omitido' % cat)
            continue
        try:
            escribir_xlsx(BASE / (cat + '.xlsx'), hojas)
        except PermissionError:
            print('  %-24s ABIERTO en Excel -> omitido' % cat)
            continue
        print('  %-24s.xlsx -> con hora %d, datos %d, parejas %d, hijos %d'
              % (cat, info['con_hora'], info['datos'], info['v_parejas'],
                 info['v_hijos']))
    print('-> %d grupos + datos_publicos.xlsx' % len(categorias))


if __name__ == '__main__':
    main()