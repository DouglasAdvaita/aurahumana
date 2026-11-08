# -*- coding: utf-8 -*-
"""Ultimo filtro: descarta articulos cuyo titulo es claramente una cosa
(embalse, tumba, monumento, pelicula, equipo...) y no una persona.

Uso: python filtrar_bios.py [--aplicar]
Sin --aplicar solo informa.
"""
import argparse
import csv
import re
from datetime import date

import depurar_bios as D
import verificar_bios as V

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
    r'\bbatalla\b|\bguerra\b|\btratado\b|\bley\b|\bconstituci[oó]n\b|\bplan\b', re.I)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--aplicar', action='store_true')
    args = ap.parse_args()

    filas = D.leer_bios()
    malas = []
    for n, r in filas.items():
        t = r.get('titulo') or ''
        if (r.get('bio_larga') or '').strip() and not V.titulo_es_persona(n, t):
            malas.append((n, t))
    print(f'Con bio: {sum(1 for r in filas.values() if (r.get("bio_larga") or "").strip())}')
    print(f'Titulos que no son personas: {len(malas)}')
    for n, t in malas:
        print(f'  {n} -> {t}')

    if args.aplicar and malas:
        for n, _t in malas:
            filas[n] = {'nombre': n, 'titulo': '', 'idioma': '', 'url': '',
                        'caracteres': 0, 'fecha': date.today().isoformat(),
                        'bio_larga': ''}
        D.guardar(filas)
        print(f'Limpiadas {len(malas)}. Con bio ahora: '
              f'{sum(1 for r in filas.values() if (r.get("bio_larga") or "").strip())}')


if __name__ == '__main__':
    main()
