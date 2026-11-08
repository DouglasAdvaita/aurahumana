# -*- coding: utf-8 -*-
"""Verifica y corrige las biografias bajadas comparando la fecha de nacimiento
de la planilla RAVE con la que figura en la introduccion del articulo.

- Lee bios_publicas.csv y la fecha de las hojas fichas/sin_hora de los xlsx.
- Pide en lotes de 20 la introduccion del articulo elegido (exintro permite
  varios por peticion) y busca el anio de nacimiento.
- Si coincide: queda como valida.
- Si no coincide o no hay bio: busca candidatos (nombre completo, apellido,
  sin acentos) y elige el que tenga el anio de nacimiento correcto.
- Guarda bios_publicas.csv corregido y bios_faltantes.txt con lo que no pudo
  resolver.

Uso:  python verificar_bios.py [--refrescar]
"""
import argparse
import concurrent.futures as cf
import csv
import re
import sys
import threading
import time
import unicodedata
from datetime import date
from pathlib import Path

import openpyxl
import requests

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

BASE = Path(__file__).resolve().parent
XLSX = [
    'actores_hollywood.xlsx',
    'datos_publicos.xlsx',
    'politicos_uy.xlsx',
    'influyentes_historia.xlsx',
    'historia_destacados.xlsx',
    'publicos_hoy.xlsx',
]
BIOS = BASE / 'bios_publicas.csv'
REVISION = BASE / 'bios_faltantes.txt'
CAMPOS = ['nombre', 'titulo', 'idioma', 'url', 'caracteres', 'fecha', 'bio_larga']
MAX_CHARS = 30000
LOTE = 20
PAUSA = 0.4
HILOS = 3

_tl = threading.local()


def _s():
    if not hasattr(_tl, 's'):
        s = requests.Session()
        s.headers.update({
            'User-Agent': 'RAVE-BiosEstudio/1.0 (https://rave-archetypes.onrender.com; estudio local)',
            'Accept-Encoding': 'gzip',
        })
        _tl.s = s
    return _tl.s


def _norm(s):
    s = unicodedata.normalize('NFKD', str(s or ''))
    s = ''.join(c for c in s if not unicodedata.combining(c))
    s = (s.replace('ł', 'l').replace('Ł', 'L').replace('ø', 'o').replace('Ø', 'O')
          .replace('đ', 'd').replace('Đ', 'D').replace('ß', 'ss')
          .replace('æ', 'ae').replace('œ', 'oe'))
    return re.sub(r'[^a-z0-9 ]', ' ', s.lower()).strip()


def _tokens(s):
    return [t for t in _norm(s).split() if len(t) > 2]


def _api(lang, params, tries=8):
    url = f'https://{lang}.wikipedia.org/w/api.php'
    for intento in range(tries):
        try:
            r = _s().get(url, params=dict(params, format='json', maxlag=5), timeout=60)
            if r.status_code == 200 and r.text.lstrip().startswith('{'):
                d = r.json()
                if str((d.get('error') or {}).get('code', '')).startswith('maxlag'):
                    time.sleep(5)
                    continue
                return d
            if r.status_code in (429, 503):
                espera = int(r.headers.get('Retry-After') or 0) or 20
                print(f'    limite ({r.status_code}); espero {espera}s', flush=True)
                time.sleep(espera)
                continue
            time.sleep(2 * (intento + 1))
        except Exception:
            time.sleep(2 * (intento + 1))
    raise RuntimeError('API de Wikipedia sin respuesta util')


def _limpiar(txt):
    txt = re.sub(r'\[\d+\]', '', txt or '')
    txt = re.sub(r'[ \t]+', ' ', txt)
    return re.sub(r'\n{3,}', '\n\n', txt).strip()


# ---------- datos de la planilla ----------

def leer_personas():
    """nombre -> {'fecha': 'dd/mm/aaaa', 'categoria': set, 'lugar': str}"""
    out = {}
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
                if not nb:
                    continue
                d = out.setdefault(nb, {'fecha': '', 'categoria': set(), 'lugar': ''})
                if len(fila) > 2 and fila[2] and not d['fecha']:
                    d['fecha'] = str(fila[2]).strip()
                if len(fila) > 1 and fila[1]:
                    d['categoria'].add(str(fila[1]).strip())
                if len(fila) > 4 and fila[4] and not d['lugar']:
                    d['lugar'] = str(fila[4]).strip()
        wb.close()
    return out


def anio_de(fecha):
    m = re.search(r'(\d{4})', str(fecha or ''))
    return int(m.group(1)) if m else None


def anios_en_texto(texto):
    return {int(a) for a in re.findall(r'\b(1[0-9]{3}|20[0-2][0-9])\b', texto or '')}


def pista_nacimiento(texto):
    """Primeros 700 caracteres: suele estar (lugar, fecha) o 'nació el ...'."""
    return _norm(texto[:700])


# ---------- intros en lote ----------

def intros(lang, titulos):
    """{titulo_normalizado: (titulo, intro)} en lotes de 20."""
    out = {}
    for i in range(0, len(titulos), LOTE):
        trozo = titulos[i:i + LOTE]
        d = _api(lang, {'action': 'query', 'prop': 'extracts', 'exintro': 1,
                        'explaintext': 1, 'exlimit': LOTE, 'redirects': 1,
                        'titles': '|'.join(trozo)})
        q = d.get('query') or {}
        redir = {_norm(rd.get('from')): _norm(rd.get('to'))
                 for rd in (q.get('redirects') or [])}
        pags = {}
        for pg in (q.get('pages') or {}).values():
            if 'missing' in pg or 'invalid' in pg:
                continue
            pags[_norm(pg.get('title'))] = pg
        for t in trozo:
            k = _norm(t)
            pg = pags.get(k) or pags.get(redir.get(k, ''))
            if pg:
                out[(lang, k)] = (pg.get('title') or t, _limpiar(pg.get('extract')))
        print(f'  intros {lang} {min(i + LOTE, len(titulos))}/{len(titulos)}', flush=True)
    return out


# ---------- busqueda de candidatos ----------

ES_PERSONA = re.compile(
    r'actor|actriz|cantante|m[uú]sico|futbolista|pol[ií]tic|escritor|periodista|'
    r'empresari|presentador|modelo|director|productor|deportista|fil[oó]sofo|'
    r'cient[ií]fico|f[ií]sico|qu[ií]mico|matem[aá]tico|m[eé]dico|abogado|juez|'
    r'economista|arquitecto|ingeniero|inventor|pintor|escultor|activista|'
    r'sacerdote|monja|papa|obispo|santo|monarca|rey|reina|emperador|militar|'
    r'revolucionario|navegante|explorador|historiador|bi[oó]logo|astr[oó]nomo|'
    r'diplom[aá]tico|embajador|senador|diputado|ministro|presidente|'
    r'gobernador|alcalde|intendente|fundador|dictador|piloto|tenista|'
    r'baloncestista|boxeador|jugador|artista|bailar|autor\b|autora\b|'
    r'v[ií]ctima|monje|rabino|im[aá]n|ciclista|ajedrecista|golfista|atleta', re.I)

NO_PERSONA = re.compile(
    r'desambiguaci|\bpel[ií]cula\b|\bserie\b|\blibro\b|\bnovela\b|\bobra\b|'
    r'\b[aá]lbum\b|\bcanci[oó]n\b|\bempresa\b|\bclub\b|\bequipo\b|\bciudad\b|'
    r'\bmunicipio\b|\bprovincia\b|\br[ií]o\b|\bmuseo\b|\bfundaci[oó]n\b|'
    r'\bapellido\b|\bnombre propio\b|\bunidad\b|\bley\b|\bcasa\b|\bcanal\b|'
    r'\bdistrito\b|\bpartido\b|\bcolegio\b|\buniversidad\b|\bhospital\b|'
    r'\bestadio\b|\baeropuerto\b|\bpremio\b|\bpremios\b|\bvestido\b|\bviaje\b|'
    r'\bcaminos\b|\bautorretrato\b|\bfotograf[ií]a\b|\bprograma\b|\bdocumental\b|'
    r'\bhipocor|\bantrop[oó]nimo|\btop[oó]nimo', re.I)

# titulos que son cosas, no personas (se comparan con el titulo del articulo)
NO_PERSONA_TITULO = re.compile(
    r'\bembalse\b|\btumba\b|\bmonumento\b|\bestatua\b|\bmuseo\b|\bcasa\b|'
    r'\bpalacio\b|\bcastillo\b|\bparque\b|\bplaza\b|\bcalle\b|\bavenida\b|'
    r'\bpuente\b|\baeropuerto\b|\bestaci[oó]n\b|\bhospital\b|\bescuela\b|'
    r'\bcolegio\b|\buniversidad\b|\biglesia\b|\bcatedral\b|\btemplo\b|'
    r'\bcementerio\b|\bbiblioteca\b|\bteatro\b|\bestadio\b|\bclub\b|\bequipo\b|'
    r'\bselecci[oó]n\b|\bcopa\b|\btorneo\b|\bpremio\b|\bmedalla\b|\bbeca\b|'
    r'\bpel[ií]cula\b|\bserie\b|\blibro\b|\bnovela\b|\b[aá]lbum\b|\bcanci[oó]n\b|'
    r'\bdisco\b|\bdocumental\b|\bprograma\b|\bcanal\b|\bpartido\b|\bfundaci[oó]n\b|'
    r'\bempresa\b|\bbanco\b|\bbarco\b|\bavi[oó]n\b|\btren\b|\bauto\b|\bmodelo\b|'
    r'\bmarca\b|\bproducto\b|\bvideojuego\b|\bpersonaje\b|\bbanda\b|\bgrupo\b|'
    r'\borquesta\b|\bsinfon[ií]a\b|\bconcierto\b|\b[oó]pera\b|\bobra\b|'
    r'\bcuadro\b|\bretrato\b|\bfotograf[ií]a\b|\bvestido\b|\btraje\b|\bcorona\b|'
    r'\bjoya\b|\bmoneda\b|\bsello\b|\basteroide\b|\bcr[aá]ter\b|\bmonta[ñn]a\b|'
    r'\br[ií]o\b|\blago\b|\bisla\b|\bvolc[aá]n\b|\bprovincia\b|\bdepartamento\b|'
    r'\bmunicipio\b|\bciudad\b|\bbarrio\b|\bdistrito\b|\bregi[oó]n\b|\bpa[ií]s\b|'
    r'\breino\b|\bimperio\b|\bdinast[ií]a\b|\bviaje\b|\bcaminos\b|\baerol[ií]nea\b|'
    r'\bautopista\b|\bruta\b|\bcarretera\b|\bfaro\b|\bmolino\b|\bfuerte\b|'
    r'\bbatalla\b|\bguerra\b|\btratado\b|\bley\b|\bconstituci[oó]n\b|\bplan\b|'
    r'\bpostulado\b|\bteorema\b|\baxioma\b|\blist of\b|\blista de\b|\bobras de\b|'
    r'\bworks by\b|\bbibliograf[ií]a\b|\bfilmograf[ií]a\b|\bdiscograf[ií]a\b|'
    r'\bcronolog[ií]a\b|\banexo\b|\bcategor[ií]a\b|\bportal\b|\bindice\b|'
    r'\blife of\b|\bobra de\b', re.I)


def titulo_es_persona(nombre, titulo):
    """True si el titulo no es claramente una cosa (o es el nombre exacto)."""
    if _norm(titulo) == _norm(nombre):
        return True
    return not NO_PERSONA_TITULO.search(titulo or '')


def candidatos(lang, consulta):
    d = _api(lang, {'action': 'query', 'generator': 'search', 'gsrsearch': consulta,
                    'gsrlimit': 8, 'gsrnamespace': 0, 'prop': 'description',
                    'redirects': 1})
    pags = list(((d.get('query') or {}).get('pages') or {}).values())
    pags.sort(key=lambda p: p.get('index', 99))
    return [(p.get('title') or '', str(p.get('description') or '')) for p in pags]


def consultas(nombre):
    """Variantes de busqueda: nombre, apellido, sin acentos, primera+ultima."""
    toks = _tokens(nombre)
    out = [nombre]
    if len(toks) > 1:
        out.append(toks[-1])
        out.append(toks[0] + ' ' + toks[-1])
    out.append(_norm(nombre))
    vistos, limpias = set(), []
    for c in out:
        k = _norm(c)
        if c and k not in vistos:
            vistos.add(k)
            limpias.append(c)
    return limpias


# ---------- principal ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--refrescar', action='store_true')
    args = ap.parse_args()

    personas = leer_personas()
    with open(BIOS, encoding='utf-8-sig', newline='') as fh:
        filas = {r['nombre']: r for r in csv.DictReader(fh, delimiter=';') if r.get('nombre')}
    print(f'Bios en CSV: {len(filas)} | personas en planillas: {len(personas)}')

    # 1) verificar las que tienen bio
    con_bio = {n: r for n, r in filas.items() if (r.get('bio_larga') or '').strip()}
    destinos = {}
    for n, r in con_bio.items():
        destinos.setdefault((r.get('idioma') or 'es'), []).append(r.get('titulo') or n)
    lecturas = {}
    for (lang, titulos) in destinos.items():
        lecturas.update(intros(lang, titulos))

    malas, ok, sin_fecha = [], 0, []
    for n, r in con_bio.items():
        lang = r.get('idioma') or 'es'
        dato = lecturas.get((lang, _norm(r.get('titulo') or n)))
        anio = anio_de(personas.get(n, {}).get('fecha'))
        if not anio:
            sin_fecha.append(n)   # no se puede verificar: se deja como esta
            continue
        if not dato:
            malas.append(n)
            continue
        texto = pista_nacimiento(dato[1])
        if anio in anios_en_texto(texto):
            ok += 1
        else:
            malas.append(n)
    print(f'Verificadas por fecha: {ok} OK | {len(malas)} con fecha distinta '
          f'| {len(sin_fecha)} sin fecha en la planilla (se dejan)', flush=True)

    # 2) resolver las dudosas y las vacias por fecha de nacimiento
    pendientes = sorted(set(malas) | {n for n, r in filas.items()
                                      if not (r.get('bio_larga') or '').strip()})
    print(f'A resolver por fecha de nacimiento: {len(pendientes)}', flush=True)

    # 2a. recolectar candidatos (una pasada, 3 hilos)
    cand_por_nombre = {}

    def _cands(nombre):
        salida = []
        for lang in ('es', 'en'):
            for q in consultas(nombre):
                try:
                    for t, d in candidatos(lang, q):
                        salida.append((lang, t, d))
                except Exception:
                    pass
                if len(salida) >= 24:
                    break
            if len(salida) >= 24:
                break
        return nombre, salida

    with cf.ThreadPoolExecutor(max_workers=HILOS) as ex:
        for nombre, lista in ex.map(_cands, pendientes):
            cand_por_nombre[nombre] = lista
            time.sleep(PAUSA)

    # 2b. intros de todos los candidatos
    titulos_por_idioma = {}
    for nombre, lista in cand_por_nombre.items():
        for lang, t, d in lista:
            key = (lang, t)
            titulos_por_idioma.setdefault(lang, set()).add(t)
    intros_cand = {}
    for lang, ts in titulos_por_idioma.items():
        intros_cand.update(intros(lang, sorted(ts)))

    # 2c. elegir por anio de nacimiento + descripcion de persona
    resueltas = 0
    revision = []
    for nombre in pendientes:
        anio = anio_de(personas.get(nombre, {}).get('fecha'))
        elegido = None
        for lang, t, d in cand_por_nombre.get(nombre, []):
            if d and NO_PERSONA.search(d):
                continue
            dato = intros_cand.get((lang, _norm(t)))
            if not dato:
                continue
            texto = pista_nacimiento(dato[1])
            if not anio or anio not in anios_en_texto(texto):
                continue
            if d and not ES_PERSONA.search(d):
                continue
            elegido = (lang, dato[0], dato[1])
            break
        if not elegido:
            revision.append(f'{nombre}\tsin articulo con fecha {anio}')
            filas[nombre] = {'nombre': nombre, 'titulo': '', 'idioma': '', 'url': '',
                             'caracteres': 0, 'fecha': date.today().isoformat(),
                             'bio_larga': ''}
            continue
        lang, titulo, intro = elegido
        filas[nombre] = {
            'nombre': nombre, 'titulo': titulo, 'idioma': lang,
            'url': f'https://{lang}.wikipedia.org/wiki/' + requests.utils.quote(titulo.replace(' ', '_')),
            'caracteres': min(len(intro), MAX_CHARS), 'fecha': date.today().isoformat(),
            'bio_larga': intro[:MAX_CHARS],
        }
        resueltas += 1
        print(f'RESUELTA  {nombre} -> {titulo} ({lang}, {anio})', flush=True)
        time.sleep(PAUSA)

    # 3) bajar el texto completo de las resueltas (quedo solo la intro)
    completas = [n for n in pendientes if (filas.get(n) or {}).get('bio_larga')]

    def _full(nombre):
        r = filas[nombre]
        try:
            d = _api(r['idioma'], {'action': 'query', 'prop': 'extracts',
                                   'explaintext': 1, 'redirects': 1,
                                   'titles': r['titulo']})
            for pg in (d.get('query') or {}).get('pages', {}).values():
                texto = _limpiar(pg.get('extract'))
                if len(texto) > len(r['bio_larga']):
                    return nombre, texto
        except Exception:
            pass
        return nombre, r['bio_larga']

    if completas:
        print(f'Bajando texto completo de {len(completas)} resueltas...', flush=True)
        with cf.ThreadPoolExecutor(max_workers=HILOS) as ex:
            for nombre, texto in ex.map(_full, completas):
                filas[nombre]['bio_larga'] = texto[:MAX_CHARS]
                filas[nombre]['caracteres'] = len(filas[nombre]['bio_larga'])
                time.sleep(PAUSA)

    # 4) guardar
    tmp = BIOS.with_suffix('.csv.tmp')
    with open(tmp, 'w', encoding='utf-8-sig', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=CAMPOS, delimiter=';')
        w.writeheader()
        for n in sorted(filas, key=_norm):
            w.writerow(filas[n])
    tmp.replace(BIOS)

    anteriores = []
    if REVISION.exists():
        with open(REVISION, encoding='utf-8') as fh:
            anteriores = [l for l in fh.read().splitlines()[1:] if l.strip()]
    todos = sorted(set(anteriores) | set(revision))
    with open(REVISION, 'w', encoding='utf-8') as fh:
        fh.write('nombre\tdetalle\n')
        fh.write('\n'.join(todos))

    con_bio = sum(1 for r in filas.values() if (r.get('bio_larga') or '').strip())
    print(f'Fin: {ok} verificadas + {resueltas} resueltas | con bio: {con_bio} '
          f'| a revisar: {len(todos)}', flush=True)


if __name__ == '__main__':
    main()
