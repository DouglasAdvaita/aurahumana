# -*- coding: utf-8 -*-
"""Baja la biografia larga (articulo completo de Wikipedia) de cada persona
publica de las planillas RAVE.

Estrategia (pocas peticiones, respetando el limite de Wikimedia):

1. Lote de titulos exactos: pide en grupos de 20 el articulo cuyo titulo es
   igual al nombre (con su descripcion de Wikidata). Cubre la mayoria.
2. Solo para los que no existen, son desambiguaciones o listas: busca
   candidatos (generator=search + descripcion), descarta los que no son
   personas y elige por coincidencia de nombre y pista de la planilla de
   origen (p. ej. "uruguayo" en politicos_uy). Si hay homonimos claros, NO
   adivina: lo deja en bios_faltantes.txt para revisar a mano.
3. Baja el texto plano completo del articulo elegido y lo recorta a MAX_CHARS
   (limite practico de una celda de Excel: 32767).

Escribe bios_publicas.csv:
    nombre;titulo;idioma;url;caracteres;fecha;bio_larga

Reanudable: las personas que ya tienen bio_larga no se vuelven a pedir.
No modifica ninguna planilla.

Uso:
    python bajar_bios_publicas.py [--limite N] [--solo NOMBRE] [--refrescar]
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
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
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
SALIDA = BASE / 'bios_publicas.csv'
TITULOS = BASE / 'bios_titulos.csv'
REVISION = BASE / 'bios_faltantes.txt'
CAMPOS = ['nombre', 'titulo', 'idioma', 'url', 'caracteres', 'fecha', 'bio_larga']
MAX_CHARS = 30000
LOTE = 20
PAUSA = 0.4
HILOS = 3

_tl = threading.local()


def _s():
    """Sesion requests por hilo (requests.Session no es thread-safe)."""
    if not hasattr(_tl, 's'):
        s = requests.Session()
        s.headers.update({
            'User-Agent': 'RAVE-BiosEstudio/1.0 (https://rave-archetypes.onrender.com; estudio local)',
            'Accept-Encoding': 'gzip',
        })
        _tl.s = s
    return _tl.s

# descripciones que no son personas (limites de palabra para no confundir
# "veterinario" con "rio" ni "secretario" con "rio")
NO_PERSONA = re.compile(
    r'\bdesambiguaci|\bp[aá]gina de desambiguaci|\bunidad\b|\bley\b|\bmuseo\b|'
    r'\bpel[ií]cula\b|\bserie de\b|\bsistema monta|\bedici[oó]n de\b|'
    r'\bgalard[oó]n\b|\bcampeonato\b|\bempresa\b|\bclub\b|\br[ií]o\b|\bciudad\b|'
    r'\blocalidad\b|\bmunicipio\b|\bprovincia\b|\bdepartamento\b|\bbarrio\b|'
    r'\bestaci[oó]n\b|\bl[ií]nea de\b|\bmarca\b|\bproducto\b|\bvideojuego\b|'
    r'\bpersonaje\b|\bbanda\b|\bgrupo (musical|de)\b|\bequipo\b|\bestadio\b|'
    r'\baeropuerto\b|\bhospital\b|\buniversidad\b|\bescuela\b|\bcolegio\b|'
    r'\bperi[oó]dico\b|\brevista\b|\bdiario\b|\btratado\b|\bacuerdo\b|\bmoneda\b|'
    r'\benfermedad\b|\bplaneta\b|\basteroide\b|\b[aá]lbum\b|\bcanci[oó]n\b|'
    r'\bsencillo\b|\blibro\b|\bnovela\b|\bobra\b|\bpoema\b|\bdisco\b|\bfestival\b|'
    r'\bconcurso\b|\btorneo\b|\btemporada\b|\baerol[ií]nea\b|\bbanco\b|'
    r'\bpartido pol[ií]tico\b|\bsindicato\b|\bfundaci[oó]n\b|\basociaci[oó]n\b|'
    r'\binstituto\b|\bministerio\b|\biglesia\b|\bcatedral\b|\bedificio\b|'
    r'\bmonumento\b|\bcalle\b|\bplaza\b|\bpuente\b|\btemplo\b|\bpalacio\b|'
    r'\bcastillo\b|\bapellido\b|\bnombre propio\b|\bt[eé]rmino\b|\bconcepto\b|'
    r'\bdisciplina\b|\bdeporte\b|\bdocumental\b|\bcortometraje\b|'
    r'\bhipocor|\bantrop[oó]nimo|\btop[oó]nimo|\bprenombre\b', re.I)

# titulos que hablan DE la persona o de algo suyo, no de la persona
TITULO_DERIVADO = re.compile(
    r'\bvestido\b|\btraje\b|\bpremios?\b|\bfundaci[oó]n\b|\bcasa\b|\bmuseo\b|'
    r'\bsinfon[ií]a\b|\bconcierto\b|\bestudios\b|\bd[ií]a de\b|\bmar de\b|'
    r'\blos perros\b|\bfotograf[ií]a\b|\brivalidad\b|\binvestidura\b|\bproceso\b|'
    r'\bintento\b|\bprimera\b|\bsegunda\b|\btercera\b|\bjr\.?\b|\bsr\.?\b|'
    r'\bhijo\b|\bhija\b|\bpadre\b|\bmadre\b|\besposa\b|\besposo\b|\bhermano\b|'
    r'\bhermana\b|\bviuda\b|\bfamilia\b|\bcorrespondencia\b|\bcr[ií]tica\b|'
    r'\bprograma\b|\bcanci[oó]n\b|\b[aá]lbum\b|\bpel[ií]cula\b|\bserie\b|'
    r'\bdocumental\b|\blibro\b|\bobra\b|\bdisco\b|\bcanal\b|\baeropuerto\b|'
    r'\bdistrito\b|\bciudad\b|\bpuente\b|\bcalle\b|\bplaza\b|\bbarrio\b|'
    r'\bedificio\b|\btemplo\b|\bestatua\b|\bmonumento\b|\buniversidad\b|'
    r'\bescuela\b|\bcolegio\b|\bhospital\b|\bteatro\b|\bestadio\b|\bequipo\b|'
    r'\bclub\b|\bselecci[oó]n\b|\btorneo\b|\bcopa\b|\bmedalla\b|\bbeca\b|'
    r'\bbarco\b|\bavi[oó]n\b|\bespecie\b|\bmemorial\b|\bparque\b|\bplaza\b|'
    r'\bmansión\b|\bmansi[oó]n\b|\bresidencia\b|\bcondecoraci[oó]n\b', re.I)

ES_PERSONA = re.compile(
    r'actor|actriz|cantante|cantautor|m[uú]sico|compositor|rapero|futbolista|'
    r'pol[ií]tic|escritor|escritora|poeta|poetisa|periodista|empresari|'
    r'presentador|presentadora|modelo|director|directora|productor|guionista|'
    r'comediante|humorista|tenista|baloncestista|boxeador|deportista|'
    r'entrenador|fil[oó]sofo|fil[oó]sofa|cient[ií]fico|f[ií]sico|qu[ií]mico|'
    r'matem[aá]tico|m[eé]dico|cirujano|psic[oó]logo|psiquiatra|abogado|juez|'
    r'economista|arquitecto|ingeniero|inventor|astronauta|pintor|escultor|'
    r'fot[oó]grafo|dise[ñn]ador|chef|cocinero|banquero|magnate|activista|'
    r'sindicalista|sacerdote|monja|papa|obispo|santo|santa|monarca|rey|reina|'
    r'pr[ií]ncipe|emperador|general|militar|revolucionario|guerrillero|'
    r'navegante|explorador|historiador|soci[oó]logo|antrop[oó]logo|bi[oó]logo|'
    r'astr[oó]nomo|ge[oó]grafo|ling[uü]ista|traductor|editor|ilustrador|'
    r'historietista|animador|youtuber|influencer|streamer|celebridad|'
    r'socialite|heredero|arist[oó]crata|noble|diplom[aá]tico|embajador|'
    r'senador|diputado|ministro|presidente|vicepresidente|gobernador|alcalde|'
    r'intendente|legislador|fiscal|funcionario|directivo|fundador|cofundador|'
    r'l[ií]der|caudillo|dictador|secretario|ajedrecista|piloto|golfista|'
    r'nadador|atleta|jugador|artista|bailar[ií]n|core[oó]grafo|locutor|'
    r'ensayista|novelista|dramaturgo|columnista|docente|profesor|profesora|'
    r'investigador|acad[eé]mico|humanista|te[oó]logo|fil[aá]ntropo|'
    r'sufragista|feminista|ecologista|empresaria|veterinario|enfermera|'
    r'empresario|estrella|princesa|duque|duquesa|marqu[eé]s|conde|bar[oó]n|'
    r'embajadora|ministra|senadora|diputada|gobernadora|alcaldesa|locutora|'
    r'autor\b|autora\b|diarista|v[ií]ctima|sobreviviente|m[aá]rtir|'
    r'historiadora|cient[ií]fica|marino|soldado|aviador|esp[ií]a|exploradora|'
    r'revolucionaria|monje|monja|sacerdotisa|pastor|rabino|im[aá]n|'
    r'deportiv|tenista|golfista|ajedrecista|ciclista|motociclista|'
    r'automovilista|remero|velerista|esgrimista|yudoca|luchador|'
    r'halter[oó]filo|gimnasta|patinador|esquiador|surfista|arquera|'
    r'futbol|balompi|beisbolista|jugadora|medallista|ol[ií]mpic', re.I)


def _norm(s):
    s = unicodedata.normalize('NFKD', str(s or ''))
    s = ''.join(c for c in s if not unicodedata.combining(c))
    return re.sub(r'[^a-z0-9 ]', ' ', s.lower()).strip()


def _tokens(s):
    return [t for t in _norm(s).split() if len(t) > 2]


def _api(lang, params, tries=8):
    """GET a la API. Respeta 429/Retry-After. Lanza RuntimeError si no hay salida."""
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
                print(f'    limite de Wikipedia ({r.status_code}); espero {espera}s', flush=True)
                time.sleep(espera)
                continue
            time.sleep(2 * (intento + 1))
        except Exception:
            time.sleep(2 * (intento + 1))
    raise RuntimeError('API de Wikipedia sin respuesta util')


def _limpiar(txt):
    txt = re.sub(r'\[\d+\]', '', txt or '')
    txt = re.sub(r'[ \t]+', ' ', txt)
    txt = re.sub(r'\n{3,}', '\n\n', txt)
    return txt.strip()


def _es_desambiguacion(texto):
    ini = _norm(texto[:300])
    return ('puede referirse a' in ini or 'pueden referirse a' in ini
            or 'desambiguacion' in ini or 'es el nombre de' in ini)


# ---------- fase 1: titulos exactos en lotes ----------

def lote_exactos(nombres):
    """dict nombre -> (titulo, desc, texto) para los titulos que existen tal cual."""
    out = {}
    for i in range(0, len(nombres), LOTE):
        trozo = nombres[i:i + LOTE]
        d = _api('es', {'action': 'query', 'prop': 'description|extracts',
                        'explaintext': 1, 'exlimit': LOTE, 'redirects': 1,
                        'titles': '|'.join(trozo)})
        q = d.get('query') or {}
        redir = {}
        for rd in q.get('redirects') or []:
            redir[_norm(rd.get('from'))] = _norm(rd.get('to'))
        pags = {}
        for pg in (q.get('pages') or {}).values():
            if 'missing' in pg or 'invalid' in pg:
                continue
            pags[_norm(pg.get('title'))] = pg
        for nombre in trozo:
            k = _norm(nombre)
            pg = pags.get(k) or pags.get(redir.get(k, ''))
            if not pg:
                continue
            texto = _limpiar(pg.get('extract'))
            desc = str(pg.get('description') or '')
            titulo = pg.get('title') or nombre
            if len(texto) < 250 or _es_desambiguacion(texto):
                continue
            if 'desambiguaci' in _norm(desc) or 'desambiguaci' in _norm(titulo):
                continue
            if re.search(r'\b(apellido|nombre propio|hipocor|antrop[oó]nimo)\b',
                         desc, re.I):
                continue
            out[nombre] = (titulo, desc, texto)
        print(f'  exactos {min(i + LOTE, len(nombres))}/{len(nombres)}: '
              f'{len(out)} resueltos', flush=True)
        time.sleep(PAUSA)
    return out


# ---------- fase 2: busqueda para los que faltan ----------

def _candidatos(lang, nombre):
    d = _api(lang, {'action': 'query', 'generator': 'search', 'gsrsearch': nombre,
                    'gsrlimit': 8, 'gsrnamespace': 0, 'prop': 'description',
                    'redirects': 1})
    pags = list(((d.get('query') or {}).get('pages') or {}).values())
    pags.sort(key=lambda p: p.get('index', 99))
    return [(p.get('title') or '', str(p.get('description') or '')) for p in pags]


def _candidato_valido(nombre, titulo, desc, pos, ctx=None):
    tn = _norm(titulo)
    if not tn or 'desambiguaci' in tn:
        return None
    toks = _tokens(nombre)
    ttoks = _tokens(titulo)
    if not toks:
        return None
    cubre = sum(1 for t in toks if t in ttoks)
    exacto = tn == _norm(nombre)
    if desc and NO_PERSONA.search(desc) and not exacto:
        return None
    # titulos derivados de la persona (obras, vestidos, hijos, lugares...)
    if not exacto and TITULO_DERIVADO.search(titulo):
        return None
    # el titulo es un fragmento del nombre buscado (p. ej. "Pepe" para
    # "Pepe Mujica"): no es la persona
    if set(ttoks) and set(ttoks) <= set(toks) and len(ttoks) < len(toks):
        return None
    if exacto:
        puntos = 6
    elif cubre == len(toks):
        puntos = 4
    elif toks == toks[-1:] and cubre == 1:
        puntos = 1  # solo apellido: puede ser homonimo
    elif cubre >= len(toks) - 1 and len(toks) > 2:
        puntos = 1
    else:
        return None
    if desc and ES_PERSONA.search(desc):
        puntos += 5
    elif not desc and not exacto:
        return None
    puntos += max(0, 2 - pos * 0.25)
    if ctx and desc:
        d = _norm(desc)
        if 'politicos_uy' in ctx and 'uruguay' in d:
            puntos += 2
        if 'actores_hollywood' in ctx and re.search(r'actor|actriz|cine|televisi', d):
            puntos += 1.5
    return puntos


def elegir(nombre, lang='es', ctx=None):
    """(titulo, dudas, ambiguo, siguientes)"""
    cands = _candidatos(lang, nombre)
    validos = []
    for pos, (titulo, desc) in enumerate(cands):
        p = _candidato_valido(nombre, titulo, desc, pos, ctx)
        if p is not None:
            validos.append((p, titulo, desc))
    if not validos:
        return None, [], False, []
    validos.sort(key=lambda x: -x[0])
    mejor_p = validos[0][0]
    empatados = [v for v in validos if abs(v[0] - mejor_p) < 0.75]
    if len(_tokens(nombre)) == 1 and len(empatados) > 1:
        return None, [f'{t} ({d})' for _, t, d in empatados], True, []
    dudas = [f'{t} ({d})' for _, t, d in empatados[1:3]]
    return validos[0][1], dudas, False, [v[1] for v in validos[1:4]]


def extractos_lote(destinos):
    """destinos: lista de (lang, titulo). Devuelve {(lang, titulo_norm): texto}."""
    out = {}
    por_idioma = {}
    for lang, titulo in destinos:
        por_idioma.setdefault(lang, []).append(titulo)
    for lang, titulos in por_idioma.items():
        for i in range(0, len(titulos), LOTE):
            trozo = titulos[i:i + LOTE]
            d = _api(lang, {'action': 'query', 'prop': 'extracts', 'explaintext': 1,
                            'exlimit': LOTE, 'redirects': 1,
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
                if not pg:
                    continue
                texto = _limpiar(pg.get('extract'))
                if len(texto) >= 250 and not _es_desambiguacion(texto):
                    out[(lang, k)] = (pg.get('title') or t, texto)
            print(f'  textos {lang} {min(i + LOTE, len(titulos))}/{len(titulos)}',
                  flush=True)
            time.sleep(PAUSA)
    return out


def _extracto(lang, titulo):
    d = _api(lang, {'action': 'query', 'prop': 'extracts', 'explaintext': 1,
                    'redirects': 1, 'titles': titulo})
    for pg in (d.get('query') or {}).get('pages', {}).values():
        if 'missing' in pg or 'invalid' in pg:
            continue
        texto = _limpiar(pg.get('extract'))
        if texto:
            return pg.get('title') or titulo, texto
    return None


# ---------- utilidades ----------

def leer_nombres():
    """(dict nombre -> categorias, lista ordenada de nombres)"""
    ctx, vistos = {}, []
    for f in XLSX:
        p = BASE / f
        if not p.exists():
            print(f'  (falta {f})')
            continue
        wb = openpyxl.load_workbook(p, read_only=True)
        for hoja in ('fichas', 'sin_hora'):
            if hoja not in wb.sheetnames:
                continue
            for fila in wb[hoja].iter_rows(min_row=2, values_only=True):
                nb = str(fila[5] or '').strip() if len(fila) > 5 else ''
                if not nb:
                    continue
                cat = str(fila[1] or '').strip() if len(fila) > 1 else ''
                ctx.setdefault(nb, set())
                if cat:
                    ctx[nb].add(cat)
                if nb not in vistos:
                    vistos.append(nb)
        wb.close()
    return ctx, sorted(vistos, key=_norm)


def leer_previo():
    if not SALIDA.exists():
        return {}
    with open(SALIDA, encoding='utf-8-sig', newline='') as fh:
        return {r.get('nombre', ''): r for r in csv.DictReader(fh, delimiter=';')
                if r.get('nombre')}


def leer_titulos():
    out = {}
    if not TITULOS.exists():
        return out
    with open(TITULOS, encoding='utf-8-sig', newline='') as fh:
        for r in csv.DictReader(fh, delimiter=';'):
            n = (r.get('nombre') or '').strip()
            if n:
                out[n] = {'nombre': n, 'idioma': r.get('idioma') or '',
                          'titulo': r.get('titulo') or '',
                          'dudas': r.get('dudas') or '',
                          'ambiguo': (r.get('ambiguo') or '').lower() == 'true'}
    return out


def guardar_titulos(d):
    tmp = TITULOS.with_suffix('.csv.tmp')
    with open(tmp, 'w', encoding='utf-8-sig', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=['nombre', 'idioma', 'titulo', 'dudas', 'ambiguo'],
                           delimiter=';')
        w.writeheader()
        for n in sorted(d, key=_norm):
            w.writerow(d[n])
    tmp.replace(TITULOS)


def fila(nombre, titulo, lang, texto):
    texto = texto[:MAX_CHARS]
    return {
        'nombre': nombre, 'titulo': titulo, 'idioma': lang,
        'url': f'https://{lang}.wikipedia.org/wiki/' + requests.utils.quote(titulo.replace(' ', '_')),
        'caracteres': len(texto), 'fecha': date.today().isoformat(),
        'bio_larga': texto,
    }


def guardar(filas):
    tmp = SALIDA.with_suffix('.csv.tmp')
    with open(tmp, 'w', encoding='utf-8-sig', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=CAMPOS, delimiter=';')
        w.writeheader()
        for nombre in sorted(filas, key=_norm):
            w.writerow(filas[nombre])
    tmp.replace(SALIDA)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limite', type=int, default=0)
    ap.add_argument('--solo', default='')
    ap.add_argument('--refrescar', action='store_true',
                    help='rehace tambien las filas que ya tienen bio')
    args = ap.parse_args()

    previo = leer_previo()
    ctx, nombres = leer_nombres()
    if args.solo:
        nombres = [n for n in nombres if _norm(args.solo) in _norm(n)]

    pendientes = [n for n in nombres
                  if args.refrescar or not (previo.get(n) or {}).get('bio_larga')]
    print(f'Personas totales: {len(nombres)} | ya con bio: {len(nombres) - len(pendientes)} '
          f'| a bajar: {len(pendientes)}', flush=True)
    if args.limite:
        pendientes = pendientes[:args.limite]

    # fase 1: titulos exactos
    print('Fase 1: titulos exactos en lotes...', flush=True)
    exactos = lote_exactos(pendientes)
    for nombre, (titulo, _desc, texto) in exactos.items():
        previo[nombre] = fila(nombre, titulo, 'es', texto)
    guardar(previo)
    print(f'  resueltos por titulo exacto: {len(exactos)}', flush=True)

    # fase 2: busqueda en paralelo (1 peticion por persona e idioma)
    resto = [n for n in pendientes if n not in exactos]
    titulos_previos = leer_titulos()
    faltan_buscar = [n for n in resto if n not in titulos_previos]
    print(f'Fase 2: busqueda para {len(resto)} ({len(faltan_buscar)} nuevas, '
          f'{len(resto) - len(faltan_buscar)} ya elegidas)...', flush=True)

    def _buscar(nombre):
        dudas = []
        for lang in ('es', 'en'):
            try:
                titulo, dudas, ambiguo, _sig = elegir(nombre, lang, ctx.get(nombre))
            except Exception as e:
                return nombre, ('error', str(e))
            if titulo:
                return nombre, (lang, titulo, dudas, False)
            if ambiguo:
                return nombre, (None, dudas, True)
        return nombre, (None, dudas, False)

    elegidos = {}
    for nombre, dato in titulos_previos.items():
        if dato['titulo']:
            dudas = [x for x in (dato['dudas'] or '').split(' | ') if x]
            elegidos[nombre] = (dato['idioma'], dato['titulo'], dudas, True)
    ambiguos, sin_nada = {}, {}
    for nombre, dato in titulos_previos.items():
        if not dato['titulo']:
            (ambiguos if dato['ambiguo'] else sin_nada)[nombre] = dato['dudas']

    hechos = 0
    with cf.ThreadPoolExecutor(max_workers=HILOS) as ex:
        futuros = {ex.submit(_buscar, n): n for n in faltan_buscar}
        for fut in cf.as_completed(futuros):
            nombre, res = fut.result()
            hechos += 1
            if res[0] == 'error':
                sin_nada[nombre] = [res[1]]
            elif res[0]:
                lang, titulo, dudas, _ = res
                elegidos[nombre] = (lang, titulo, dudas, False)
                titulos_previos[nombre] = {'nombre': nombre, 'idioma': lang,
                                           'titulo': titulo, 'dudas': ' | '.join(dudas),
                                           'ambiguo': False}
            elif res[2]:
                ambiguos[nombre] = res[1]
                titulos_previos[nombre] = {'nombre': nombre, 'idioma': '',
                                           'titulo': '', 'dudas': ' | '.join(res[1]),
                                           'ambiguo': True}
            else:
                sin_nada[nombre] = res[1]
                titulos_previos[nombre] = {'nombre': nombre, 'idioma': '',
                                           'titulo': '', 'dudas': ' | '.join(res[1]),
                                           'ambiguo': False}
            if hechos % 20 == 0:
                guardar_titulos(titulos_previos)
                print(f'  busqueda {hechos}/{len(faltan_buscar)}', flush=True)
            time.sleep(PAUSA)
    guardar_titulos(titulos_previos)

    # fase 3: textos en paralelo (Wikipedia devuelve el texto completo de a uno)
    print(f'Fase 3: bajando textos de {len(elegidos)} articulos...', flush=True)

    def _bajar(item):
        nombre, (lang, titulo, dudas, _ya) = item
        try:
            r = _extracto(lang, titulo)
        except Exception as e:
            return nombre, lang, titulo, dudas, None, str(e)
        if r and len(r[1]) >= 250 and not _es_desambiguacion(r[1]):
            return nombre, lang, r[0], dudas, r[1], ''
        return nombre, lang, titulo, dudas, None, 'articulo no util'

    ok = 0
    revision = []
    hechos = 0
    with cf.ThreadPoolExecutor(max_workers=HILOS) as ex:
        futuros = {ex.submit(_bajar, it): it[0] for it in elegidos.items()}
        for fut in cf.as_completed(futuros):
            nombre, lang, titulo, dudas, texto, err = fut.result()
            hechos += 1
            if texto:
                previo[nombre] = fila(nombre, titulo, lang, texto)
                ok += 1
                print(f'[{hechos}/{len(elegidos)}] OK  {nombre} -> {titulo} ({lang}, '
                      f'{previo[nombre]["caracteres"]} c.)', flush=True)
            else:
                detalle = ' | '.join(dudas[:3]) if dudas else err
                revision.append(f'{nombre}\t{detalle}')
                previo[nombre] = {
                    'nombre': nombre, 'titulo': '', 'idioma': '', 'url': '',
                    'caracteres': 0, 'fecha': date.today().isoformat(), 'bio_larga': '',
                }
                print(f'[{hechos}/{len(elegidos)}] REVISAR  {nombre}  ({detalle})',
                      flush=True)
            if hechos % 5 == 0:
                guardar(previo)
            time.sleep(PAUSA)

    for nombre, dudas in ambiguos.items():
        if isinstance(dudas, str):
            dudas = [x for x in dudas.split(' | ') if x]
        revision.append(f'{nombre}\thomonimos: ' + (' | '.join(dudas[:3]) or 'varios'))
        previo[nombre] = {
            'nombre': nombre, 'titulo': '', 'idioma': '', 'url': '',
            'caracteres': 0, 'fecha': date.today().isoformat(), 'bio_larga': '',
        }
        print(f'REVISAR  {nombre}  (homonimos)', flush=True)
    for nombre in sin_nada:
        revision.append(f'{nombre}\tsin resultados')
        previo[nombre] = {
            'nombre': nombre, 'titulo': '', 'idioma': '', 'url': '',
            'caracteres': 0, 'fecha': date.today().isoformat(), 'bio_larga': '',
        }
        print(f'REVISAR  {nombre}  (sin resultados)', flush=True)

    guardar(previo)
    anteriores = []
    if REVISION.exists():
        with open(REVISION, encoding='utf-8') as fh:
            anteriores = [l for l in fh.read().splitlines()[1:] if l.strip()]
    todos = sorted(set(anteriores) | set(revision))
    with open(REVISION, 'w', encoding='utf-8') as fh:
        fh.write('nombre\tdetalle\n')
        fh.write('\n'.join(todos))
    con_bio = sum(1 for r in previo.values() if (r.get('bio_larga') or '').strip())
    print(f'Fin: {ok} por busqueda + {len(exactos)} exactas | con bio: {con_bio} '
          f'| a revisar: {len(todos)}. Archivo: {SALIDA}', flush=True)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except RuntimeError as e:
        print(f'CORTADO: {e}. Se puede retomar con el mismo comando.', flush=True)
        sys.exit(2)
