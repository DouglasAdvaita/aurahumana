# -*- coding: utf-8 -*-
"""Baja una foto publica (Wikipedia / Wikidata) de cada persona publica.

- Recorre los `nombre_base` unicos de personas_publicas.csv.
- Busca la imagen en Wikipedia ES -> EN (generator=search + pageimages) y, si
  falla, en Wikidata (propiedad P18).
- Guarda la imagen achicada (JPEG <= 100 KB) en Publicos/<slug>.jpg.
- Escribe/actualiza fotos_publicas.csv (nombre_base;foto;fuente;bytes).
  `foto` queda como 'Publicos/<slug>.jpg' (link para la columna del xlsx).

Reanudable: si una persona ya tiene fila valida, se saltea.
Uso:  python bajar_fotos_publicas.py [--limite N]
"""
import csv
import io
import sys
import time
import unicodedata
from pathlib import Path
from urllib.parse import quote

import requests
from PIL import Image, ImageOps

BASE = Path(__file__).resolve().parent
PUB = BASE / 'personas_publicas.csv'
DEST = BASE / 'Publicos'
CSV_OUT = BASE / 'fotos_publicas.csv'
MAX_BYTES = 100 * 1024

S = requests.Session()
S.headers.update({'User-Agent': 'RAVE-fotos-publicas/1.0 (uso local, no comercial)'})


def _api(url, params, tries=4):
    for intento in range(tries):
        try:
            r = S.get(url, params=params, timeout=25)
            if r.status_code == 200:
                return r.json()
            time.sleep(1.5 * (intento + 1))
        except Exception:
            time.sleep(1.5 * (intento + 1))
    return {}


def _slug(s):
    s = unicodedata.normalize('NFKD', str(s))
    s = ''.join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    out = []
    for c in s:
        out.append(c if c.isalnum() else '_')
    t = ''.join(out).strip('_')
    while '__' in t:
        t = t.replace('__', '_')
    return t or 'persona'


def _wiki_thumb(query, lang):
    """Primer resultado de busqueda en Wikipedia con su thumbnail (o '')."""
    d = _api(f'https://{lang}.wikipedia.org/w/api.php', {
        'action': 'query', 'format': 'json', 'generator': 'search',
        'gsrsearch': query, 'gsrlimit': 1, 'gsrnamespace': 0,
        'prop': 'pageimages', 'piprop': 'thumbnail', 'pithumbsize': 400})
    pages = (d.get('query') or {}).get('pages') or {}
    for _, pg in pages.items():
        th = (pg.get('thumbnail') or {}).get('source')
        if th:
            return th
    return ''


def _wikidata_thumb(nombre):
    d = _api('https://www.wikidata.org/w/api.php', {
        'action': 'wbsearchentities', 'format': 'json', 'language': 'es',
        'uselang': 'es', 'search': nombre, 'limit': 3})
    for hit in (d.get('search') or []):
        qid = hit.get('id')
        if not qid:
            continue
        e = _api('https://www.wikidata.org/w/api.php', {
            'action': 'wbgetentities', 'format': 'json', 'ids': qid,
            'props': 'claims'})
        ent = (e.get('entities') or {}).get(qid) or {}
        for cl in ((ent.get('claims') or {}).get('P18') or []):
            try:
                fn = cl['mainsnak']['datavalue']['value']
            except Exception:
                continue
            if fn:
                return ('https://commons.wikimedia.org/wiki/Special:FilePath/'
                        + quote(str(fn)) + '?width=400')
    return ''


def _buscar_foto(nombre, desc):
    """URL de imagen para una persona (o '')."""
    for lang in ('es', 'en'):
        u = _wiki_thumb(nombre, lang)
        if u:
            return u, f'wikipedia_{lang}'
    q = (nombre + ' ' + ' '.join((desc or '').split()[:6])).strip()
    if q != nombre:
        for lang in ('es', 'en'):
            u = _wiki_thumb(q, lang)
            if u:
                return u, f'wikipedia_{lang}'
    u = _wikidata_thumb(nombre)
    if u:
        return u, 'wikidata'
    return '', ''


def _achicar(data):
    """JPEG <= MAX_BYTES. Devuelve (bytes, calidad) o (b'', 0)."""
    try:
        im = Image.open(io.BytesIO(data))
        im = ImageOps.exif_transpose(im).convert('RGB')
    except Exception:
        return b'', 0
    im.thumbnail((300, 420))
    ultimo = b''
    for q in (82, 75, 68, 60, 52, 45, 38, 30):
        buf = io.BytesIO()
        im.save(buf, 'JPEG', quality=q, optimize=True)
        ultimo = buf.getvalue()
        if len(ultimo) <= MAX_BYTES:
            return ultimo, q
    return ultimo, 30


def _descargar(url):
    try:
        r = S.get(url, timeout=40)
        if r.status_code == 200 and r.content:
            return r.content
    except Exception:
        pass
    return b''


def _nombres():
    """[(nombre_base, descripcion)] en orden de aparicion."""
    rows = list(csv.DictReader(open(PUB, encoding='utf-8-sig'), delimiter=';'))
    vistos, out = set(), []
    for r in rows:
        b = (r.get('nombre_base') or r.get('nombre') or '').strip()
        if not b or b.lower() in vistos:
            continue
        vistos.add(b.lower())
        out.append((b, (r.get('descripcion') or '').strip()))
    return out


def _leer_previo():
    if not CSV_OUT.exists():
        return {}
    prev = {}
    for r in csv.DictReader(open(CSV_OUT, encoding='utf-8-sig'), delimiter=';'):
        prev[(r.get('nombre_base') or '').strip().lower()] = r
    return prev


def _guardar(registros):
    with open(CSV_OUT, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f, delimiter=';')
        w.writerow(['nombre_base', 'foto', 'fuente', 'bytes'])
        for r in registros:
            w.writerow([r['nombre_base'], r['foto'], r['fuente'], r['bytes']])


def main():
    limite = None
    if '--limite' in sys.argv:
        try:
            limite = int(sys.argv[sys.argv.index('--limite') + 1])
        except Exception:
            limite = None
    DEST.mkdir(exist_ok=True)
    nombres = _nombres()
    prev = _leer_previo()
    con_foto = {k for k, r in prev.items() if r.get('foto')}
    registros = [prev[k] for k in con_foto]
    slugs = {Path(r['foto']).stem for r in registros if r.get('foto')}
    pendientes = [(n, d) for n, d in nombres if n.lower() not in con_foto]
    if limite:
        pendientes = pendientes[:limite]
    print(f'{len(nombres)} personas unicas · {len(con_foto)} con foto · '
          f'{len(pendientes)} a intentar')
    ok = con = 0
    for i, (nombre, desc) in enumerate(pendientes, 1):
        url, fuente = _buscar_foto(nombre, desc)
        foto = ''
        if url:
            raw = _descargar(url)
            jpg, _q = _achicar(raw) if raw else (b'', 0)
            if jpg:
                sl = _slug(nombre)
                base_sl, k = sl, 2
                while base_sl in slugs:
                    base_sl = f'{sl}_{k}'
                    k += 1
                slugs.add(base_sl)
                (DEST / f'{base_sl}.jpg').write_bytes(jpg)
                foto = f'Publicos/{base_sl}.jpg'
                con += 1
        registros.append({'nombre_base': nombre, 'foto': foto,
                          'fuente': fuente or '', 'bytes': len(jpg) if foto else 0})
        ok += 1
        if i % 25 == 0 or i == len(pendientes):
            _guardar(registros)
            print(f'  {i}/{len(pendientes)} -> con foto {con}')
        time.sleep(0.4)
    _guardar(registros)
    con_total = sum(1 for r in registros if r.get('foto'))
    print(f'LISTO: {con_total}/{len(registros)} con foto. CSV: {CSV_OUT.name}, '
          f'imagenes en {DEST.name}/')


if __name__ == '__main__':
    main()
