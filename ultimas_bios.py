# -*- coding: utf-8 -*-
"""Ultimo intento para las biografias vacias: acepta el articulo cuyo titulo
coincide exactamente con el nombre y cuya descripcion es de persona, aunque la
fecha de nacimiento de la planilla no coincida (las planillas tienen fechas
dudosas en varios casos).

Uso: python ultimas_bios.py [--aplicar]
"""
import argparse
import concurrent.futures as cf
from datetime import date

import requests

import depurar_bios as D
import verificar_bios as V


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--aplicar', action='store_true')
    args = ap.parse_args()

    filas = D.leer_bios()
    vacias = [n for n, r in filas.items() if not (r.get('bio_larga') or '').strip()]
    print(f'Sin bio: {len(vacias)}')

    def buscar(nombre):
        for lang in ('es', 'en'):
            try:
                for t, d in V.candidatos(lang, nombre):
                    if V._norm(t) != V._norm(nombre):
                        continue
                    if d and V.NO_PERSONA.search(d):
                        continue
                    if d and not V.ES_PERSONA.search(d):
                        continue
                    return nombre, lang, t
            except Exception:
                pass
        return nombre, None, None

    encontrados = []
    with cf.ThreadPoolExecutor(max_workers=3) as ex:
        for nombre, lang, titulo in ex.map(buscar, vacias):
            if titulo:
                encontrados.append((nombre, lang, titulo))
                print(f'  {nombre} -> {titulo} ({lang})')
    print(f'Encontrados por titulo exacto: {len(encontrados)}')

    if not args.aplicar or not encontrados:
        if encontrados:
            print('(sin --aplicar no se guarda nada)')
        return

    def full(item):
        n, lang, titulo = item
        try:
            d = V._api(lang, {'action': 'query', 'prop': 'extracts', 'explaintext': 1,
                              'redirects': 1, 'titles': titulo})
            for pg in (d.get('query') or {}).get('pages', {}).values():
                texto = V._limpiar(pg.get('extract'))
                if len(texto) >= 250:
                    return n, lang, titulo, texto
        except Exception:
            pass
        return n, lang, titulo, ''

    with cf.ThreadPoolExecutor(max_workers=3) as ex:
        for n, lang, titulo, texto in ex.map(full, encontrados):
            if not texto:
                continue
            texto = texto[:V.MAX_CHARS]
            filas[n] = {
                'nombre': n, 'titulo': titulo, 'idioma': lang,
                'url': f'https://{lang}.wikipedia.org/wiki/'
                       + requests.utils.quote(titulo.replace(' ', '_')),
                'caracteres': len(texto), 'fecha': date.today().isoformat(),
                'bio_larga': texto,
            }

    D.guardar(filas)
    con = sum(1 for r in filas.values() if (r.get('bio_larga') or '').strip())
    print(f'Guardado. Con bio: {con}/{len(filas)}')


if __name__ == '__main__':
    main()
