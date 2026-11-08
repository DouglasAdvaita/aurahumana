# -*- coding: utf-8 -*-
"""Completa las biografias que quedaron vacias usando titulos conocidos de
Wikipedia para los nombres de un solo apellido (Mozart, Chopin...) y
verificando que el anio de nacimiento de la planilla figure en la introduccion.

Uso: python completar_bios.py [--aplicar]
"""
import argparse
import csv
import re

import requests
from datetime import date

import depurar_bios as D
import verificar_bios as V

# nombre en la planilla -> titulo exacto en Wikipedia
CONOCIDOS = {
    'Mozart': 'Wolfgang Amadeus Mozart',
    'Chopin': 'Frédéric Chopin',
    'Beethoven': 'Ludwig van Beethoven',
    'Wagner': 'Richard Wagner',
    'Schumann': 'Robert Schumann',
    'Schonberg': 'Arnold Schönberg',
    'Chaikovski': 'Piotr Ilich Chaikovski',
    'Johann Sebastian Bach': 'Johann Sebastian Bach',
    'Gutenberg': 'Johannes Gutenberg',
    'Euclides': 'Euclides',
    'Arquimedes': 'Arquímedes',
    'Ataturk': 'Mustafa Kemal Atatürk',
    'Arendt': 'Hannah Arendt',
    'Brecht': 'Bertolt Brecht',
    'Dunant': 'Henry Dunant',
    'Emerson': 'Ralph Waldo Emerson',
    'Frost': 'Robert Frost',
    'Kenyatta': 'Jomo Kenyatta',
    'Lindbergh': 'Charles Lindbergh',
    'Marquez': 'Gabriel García Márquez',
    'Meloni': 'Giorgia Meloni',
    'Miguel Angel Buonarroti': 'Miguel Ángel',
    'Oersted': 'Hans Christian Ørsted',
    'Ohm': 'Georg Simon Ohm',
    'Papa Francisco': 'Papa Francisco',
    'Rockefeller': 'John D. Rockefeller',
    'Rosa Luxemburg': 'Rosa Luxemburgo',
    'Sheinbaum': 'Claudia Sheinbaum',
    'Snowden': 'Edward Snowden',
    'Stevenson': 'Robert Louis Stevenson',
    'Thich Quang Duc': 'Thích Quảng Đức',
    'Vitalik Buterin': 'Vitalik Buterin',
    'William Shakespeare': 'William Shakespeare',
    'Yunus': 'Muhammad Yunus',
    'Zach King': 'Zach King',
    'Zamenhof': 'L. L. Zamenhof',
    'Larry Page': 'Larry Page',
    'Lech Walesa': 'Lech Wałęsa',
    'Daddy Yankee': 'Daddy Yankee',
    'Auronplay': 'AuronPlay',
    'Harvey': 'William Harvey',
    'Berta Caceres': 'Berta Cáceres',
    'Luis Alberto Lacalle Herrera': 'Luis Alberto Lacalle',
    'Joan Crawford': 'Joan Crawford',
    'Harriet Tubman': 'Harriet Tubman',
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--aplicar', action='store_true')
    args = ap.parse_args()

    personas = V.leer_personas()
    filas = D.leer_bios()
    vacias = [n for n, r in filas.items() if not (r.get('bio_larga') or '').strip()]
    print(f'Sin bio: {len(vacias)} | titulos conocidos disponibles: {len(CONOCIDOS)}')

    intros = V.intros('es', sorted({t for n, t in CONOCIDOS.items() if n in vacias}))
    resueltas, revisar = [], []
    for n in vacias:
        titulo = CONOCIDOS.get(n)
        if not titulo:
            continue
        dato = intros.get(('es', V._norm(titulo)))
        if not dato:
            revisar.append((n, titulo, 'sin articulo'))
            continue
        fecha = D.fecha_planilla(personas.get(n, {}).get('fecha'))
        ok, motivo = D.valida(n, titulo, dato[1], fecha)
        if not ok and fecha:
            # segundo criterio: el anio de la planilla aparece en el arranque
            if re.search(r'(?<!\d)' + str(fecha[2]) + r'(?!\d)', V._norm(dato[1][:1200])):
                ok, motivo = True, ''
            elif ' A. C' in V._norm(dato[1][:400]).upper() and fecha[2] < 1000:
                ok, motivo = True, ''
        if ok:
            resueltas.append((n, dato[0], dato[1]))
        else:
            revisar.append((n, titulo, motivo))

    print(f'Verificadas: {len(resueltas)} | a revisar: {len(revisar)}')
    for n, t, m in revisar:
        print(f'  {n} -> {t}: {m}')

    if not args.aplicar:
        print('(sin --aplicar no se guarda nada)')
        return

    import concurrent.futures as cf

    def full(item):
        n, titulo, intro = item
        try:
            d = V._api('es', {'action': 'query', 'prop': 'extracts', 'explaintext': 1,
                              'redirects': 1, 'titles': titulo})
            for pg in (d.get('query') or {}).get('pages', {}).values():
                texto = V._limpiar(pg.get('extract'))
                if len(texto) > len(intro):
                    return n, titulo, texto
        except Exception:
            pass
        return n, titulo, intro

    with cf.ThreadPoolExecutor(max_workers=3) as ex:
        for n, titulo, texto in ex.map(full, resueltas):
            texto = texto[:V.MAX_CHARS]
            filas[n] = {
                'nombre': n, 'titulo': titulo, 'idioma': 'es',
                'url': 'https://es.wikipedia.org/wiki/' + requests.utils.quote(titulo.replace(' ', '_')),
                'caracteres': len(texto), 'fecha': date.today().isoformat(),
                'bio_larga': texto,
            }
            print(f'  OK {n} -> {titulo} ({len(texto)} c.)')

    D.guardar(filas)
    con = sum(1 for r in filas.values() if (r.get('bio_larga') or '').strip())
    print(f'Guardado. Con bio: {con}/{len(filas)}')


if __name__ == '__main__':
    main()
