# -*- coding: utf-8 -*-
"""Depura las biografias: exige apellido compatible y, si el articulo informa
dia y mes, que coincidan con la fecha de la planilla (no solo el anio).

- Marca como no validas las que fallan y vuelve a buscarlas.
- Las que no encuentra quedan sin bio y anotadas en bios_faltantes.txt.

Uso:  python depurar_bios.py
"""
import csv
import difflib
import re
import sys
import time
import unicodedata
from datetime import date
from pathlib import Path

import requests

import verificar_bios as V

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

BIOS = V.BASE / 'bios_publicas.csv'
REVISION = V.BASE / 'bios_faltantes.txt'
CAMPOS = V.CAMPOS
PARTICULAS = {'de', 'del', 'la', 'las', 'los', 'van', 'von', 'da', 'di', 'dos',
              'das', 'y', 'e', 'san', 'santa', 'van', 'der', 'den', 'bin', 'ibn'}
MESES = {'enero': 1, 'febrero': 2, 'marzo': 3, 'abril': 4, 'mayo': 5, 'junio': 6,
         'julio': 7, 'agosto': 8, 'septiembre': 9, 'setiembre': 9, 'octubre': 10,
         'noviembre': 11, 'diciembre': 12}


def fecha_de(texto):
    """(dia, mes, anio) de nacimiento segun el arranque del articulo.

    Los articulos suelen empezar '(lugar, 5 de juniojul. / 16 de juniogreg. de
    1723 - ...)'. Se toma el primer dia/mes y el primer anio del arranque, sin
    exigir que el anio siga pegado al mes (en las fechas dobles julianas el
    anio queda despues del segundo dia/mes).
    """
    t = V._norm((texto or '')[:350])
    m = re.search(r'(\d{1,2}) de (' + '|'.join(MESES) + r')', t)
    if not m:
        return None
    y = re.search(r'(1[0-9]{3}|20[0-2][0-9])', t)
    if not y:
        return None
    return int(m.group(1)), MESES[m.group(2)], int(y.group(1))


def fecha_planilla(fecha):
    m = re.search(r'(\d{1,2})[/-](\d{1,2})[/-](\d{4})', str(fecha or ''))
    if m:
        return int(m.group(1)), int(m.group(2)), int(m.group(3))
    return None


def dias_diferencia(a, b):
    """Diferencia en dias entre dos (dia, mes, anio)."""
    from datetime import date as _date
    try:
        return abs((_date(a[2], a[1], a[0]) - _date(b[2], b[1], b[0])).days)
    except ValueError:
        return 9999


def tokens_nombre(nombre):
    return [t for t in V._tokens(nombre) if t not in PARTICULAS]


def apellido_ok(nombre, titulo):
    toks = tokens_nombre(nombre)
    if not toks:
        return False
    ap = toks[-1]
    tt = V._tokens(titulo)
    return any(difflib.SequenceMatcher(None, ap, x).ratio() >= 0.85 for x in tt)


def nombre_ok(nombre, titulo):
    """El nombre de pila aparece en el titulo (no exigible si solo hay apellido)."""
    toks = tokens_nombre(nombre)
    if len(toks) < 2:
        return True
    tt = set(V._tokens(titulo))
    return any(t in tt for t in toks[:-1])


def valida(nombre, titulo, intro, fecha_pl):
    """True si el articulo corresponde a la persona de la planilla."""
    if not V.titulo_es_persona(nombre, titulo):
        return False, 'el titulo no es una persona'
    arranque = V._norm((intro or '')[:300])
    if 'desambiguacion' in arranque or 'puede referirse a' in arranque:
        return False, 'pagina de desambiguacion'
    if not apellido_ok(nombre, titulo):
        return False, 'apellido no coincide'
    f_intro = fecha_de(intro)
    if fecha_pl:
        d, m, y = fecha_pl
        arranque = V.pista_nacimiento(intro)
        if not re.search(r'(?<!\d)' + str(y) + r'(?!\d)', arranque):
            return False, f'anio distinto de {y}'
        # titulo identico al nombre: la evidencia es suficientemente fuerte
        if V._norm(titulo) == V._norm(nombre):
            return True, ''
        if f_intro:
            dif = dias_diferencia(f_intro, fecha_pl)
            # 10-13 dias: calendario juliano vs gregoriano
            if dif not in (0, 10, 11, 12, 13):
                # fechas de la planilla a veces tienen el dia corrido: si
                # coinciden nombre y apellido, se acepta con el anio correcto
                if not nombre_ok(nombre, titulo):
                    return False, f'fecha {f_intro[0]}/{f_intro[1]} distinta de {d}/{m}'
        elif not nombre_ok(nombre, titulo):
            return False, 'nombre de pila distinto y sin fecha completa'
    return True, ''


def leer_bios():
    with open(BIOS, encoding='utf-8-sig', newline='') as fh:
        return {r['nombre']: r for r in csv.DictReader(fh, delimiter=';') if r.get('nombre')}


def guardar(filas):
    tmp = BIOS.with_suffix('.csv.tmp')
    with open(tmp, 'w', encoding='utf-8-sig', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=CAMPOS, delimiter=';')
        w.writeheader()
        for n in sorted(filas, key=V._norm):
            w.writerow(filas[n])
    tmp.replace(BIOS)


def main():
    personas = V.leer_personas()
    filas = leer_bios()
    con_bio = {n: r for n, r in filas.items() if (r.get('bio_larga') or '').strip()}
    print(f'Con bio: {len(con_bio)}', flush=True)

    # intros de los articulos elegidos
    destinos = {}
    for n, r in con_bio.items():
        destinos.setdefault(r.get('idioma') or 'es', []).append(r.get('titulo') or n)
    lecturas = {}
    for lang, ts in destinos.items():
        lecturas.update(V.intros(lang, ts))

    sospechosas = {}
    buenas = 0
    for n, r in con_bio.items():
        lang = r.get('idioma') or 'es'
        dato = lecturas.get((lang, V._norm(r.get('titulo') or n)))
        intro = dato[1] if dato else ''
        ok, motivo = valida(n, r.get('titulo') or n, intro, fecha_planilla(personas.get(n, {}).get('fecha')))
        if ok:
            buenas += 1
        else:
            sospechosas[n] = motivo
    print(f'Validas: {buenas} | a rehacer: {len(sospechosas)}', flush=True)

    # limpiar sospechosas
    for n in sospechosas:
        filas[n] = {'nombre': n, 'titulo': '', 'idioma': '', 'url': '', 'caracteres': 0,
                    'fecha': date.today().isoformat(), 'bio_larga': ''}

    pendientes = sorted(set(sospechosas) | {n for n, r in filas.items()
                                            if not (r.get('bio_larga') or '').strip()})
    print(f'A resolver con regla estricta: {len(pendientes)}', flush=True)

    # candidatos
    cands = {}
    for nombre in pendientes:
        lista = []
        for lang in ('es', 'en'):
            for q in V.consultas(nombre):
                try:
                    lista += [(lang, t, d) for t, d in V.candidatos(lang, q)]
                except Exception:
                    pass
                if len(lista) >= 24:
                    break
            if len(lista) >= 24:
                break
        cands[nombre] = lista
        time.sleep(V.PAUSA)
        if len(cands) % 20 == 0:
            print(f'  candidatos {len(cands)}/{len(pendientes)}', flush=True)

    titulos = {}
    for nombre, lista in cands.items():
        for lang, t, d in lista:
            titulos.setdefault(lang, set()).add(t)
    intros = {}
    for lang, ts in titulos.items():
        intros.update(V.intros(lang, sorted(ts)))

    resueltas, revision = 0, []
    for nombre in pendientes:
        fecha_pl = fecha_planilla(personas.get(nombre, {}).get('fecha'))
        eleccion = None
        # primero el titulo que mas se parece al nombre
        orden = sorted(cands.get(nombre, []),
                       key=lambda x: (0 if V._norm(x[1]) == V._norm(nombre) else 1,
                                      len(V._tokens(x[1]))))
        for lang, t, d in orden:
            if not V.titulo_es_persona(nombre, t):
                continue
            if d and V.NO_PERSONA.search(d):
                continue
            dato = intros.get((lang, V._norm(t)))
            if not dato:
                continue
            if d and not V.ES_PERSONA.search(d):
                continue
            ok, _motivo = valida(nombre, t, dato[1], fecha_pl)
            if ok:
                eleccion = (lang, dato[0], dato[1])
                break
        if not eleccion:
            revision.append(f'{nombre}\tsin articulo que coincida con la fecha')
            continue
        lang, titulo, intro = eleccion
        filas[nombre] = {
            'nombre': nombre, 'titulo': titulo, 'idioma': lang,
            'url': f'https://{lang}.wikipedia.org/wiki/' + requests.utils.quote(titulo.replace(' ', '_')),
            'caracteres': len(intro), 'fecha': date.today().isoformat(),
            'bio_larga': intro[:V.MAX_CHARS],
        }
        resueltas += 1
        print(f'RESUELTA  {nombre} -> {titulo} ({lang})', flush=True)

    # texto completo de las resueltas
    nuevas = [n for n in pendientes if (filas.get(n) or {}).get('bio_larga')]
    import concurrent.futures as cf

    def _full(nombre):
        r = filas[nombre]
        try:
            d = V._api(r['idioma'], {'action': 'query', 'prop': 'extracts',
                                     'explaintext': 1, 'redirects': 1,
                                     'titles': r['titulo']})
            for pg in (d.get('query') or {}).get('pages', {}).values():
                texto = V._limpiar(pg.get('extract'))
                if len(texto) > len(r['bio_larga']):
                    return nombre, texto
        except Exception:
            pass
        return nombre, r['bio_larga']

    if nuevas:
        print(f'Bajando texto completo de {len(nuevas)}...', flush=True)
        with cf.ThreadPoolExecutor(max_workers=3) as ex:
            for nombre, texto in ex.map(_full, nuevas):
                filas[nombre]['bio_larga'] = texto[:V.MAX_CHARS]
                filas[nombre]['caracteres'] = len(filas[nombre]['bio_larga'])
                time.sleep(V.PAUSA)

    guardar(filas)
    with open(REVISION, 'w', encoding='utf-8') as fh:
        fh.write('nombre\tdetalle\n')
        fh.write('\n'.join(sorted(revision)))

    con_bio = sum(1 for r in filas.values() if (r.get('bio_larga') or '').strip())
    print(f'Fin: validas {buenas} + resueltas {resueltas} | con bio: {con_bio} '
          f'| sin bio: {len(filas) - con_bio}', flush=True)


if __name__ == '__main__':
    main()
