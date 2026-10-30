"""Briefing diario de Diseño Humano (RAVE).

Calcula, sin IA, qué cambia hoy respecto de ayer y qué implica. Devuelve
texto listo para el panel, para Hermes/WhatsApp o para AuraHumana.

Uso:
  python briefing.py --persona Jorge
  python briefing.py --persona "Victoria Espinaca" --fecha 2026-10-29 --hora 09:00
  python briefing.py --persona Jorge --json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
os.chdir(BASE)
sys.path.insert(0, str(BASE))

import app  # noqa: E402

TZ = timezone(timedelta(hours=-3))  # Montevideo
PASO_MIN = 360  # muestreo grueso; los bordes se refinan con _buscar_limite_tramo
ORDEN_CENTROS = ['Corona', 'Ajna', 'Garganta', 'G', 'Ego', 'Bazo', 'Plexo', 'Sacro', 'Raiz']
# Sensación práctica de los canales que más aparecen en el briefing.
SENSACION = {
    '23-43': 'presión por explicar o convencer',
    '21-45': 'impulso de tomar el control y manejar recursos',
    '35-36': 'ganas de probar algo nuevo',
}


def _ahora_local() -> datetime:
    return datetime.now(TZ).replace(tzinfo=None)


def _jd(dt_local: datetime) -> float:
    utc = dt_local + timedelta(hours=3)
    return app._jd_de_utc(utc.replace(tzinfo=timezone.utc))


def _local(ms: int | None) -> datetime | None:
    if ms is None:
        return None
    return (datetime.fromtimestamp(ms / 1000, timezone.utc) - timedelta(hours=3)).replace(tzinfo=None)


def _hora(dt: datetime | None) -> str:
    if not dt:
        return '?'
    # Redondeo a 5 min: evita "13:36" y da una ventana legible.
    m = ((dt.minute + 2) // 5) * 5
    h = dt.hour
    if m >= 60:
        h = (h + 1) % 24
        m = 0
    return f'{h:02d}:{m:02d}'


def _lista_y(items):
    items = list(items)
    if not items:
        return ''
    if len(items) == 1:
        return items[0]
    return ', '.join(items[:-1]) + ' y ' + items[-1]


def _nombre_centro(c: str) -> str:
    return 'Raíz' if c == 'Raiz' else c


def _primera_oracion(txt: str) -> str:
    s = str(txt or '').strip()
    if not s:
        return ''
    para = re.split(r'\r?\n\s*\r?\n', s)[0]
    linea = next((x.strip() for x in para.splitlines() if x.strip()), para).strip()
    m = re.match(r'^[^.!?]+[.!?]', linea)
    return (m.group(0) if m else linea).strip()


def _implicacion(canal: str) -> str:
    """Primera oración de canales.csv, sin 'Te lleva a' y con 'y' entre dos partes."""
    desc = ''
    try:
        for c in app.cargar_canales():
            if app._hd_norm_canal(str(c.get('elemento', '')).strip()) == canal:
                desc = c.get('descripcion', '')
                break
    except Exception:
        pass
    frase = _primera_oracion(desc).strip().rstrip('.')
    if frase.lower().startswith('te lleva a '):
        frase = frase[10:].strip()
    frase = frase.replace(', como ', ', ').replace(' como, ', ', ').replace(' como ', ', ')
    partes = [p.strip() for p in frase.split(', ') if p.strip()]
    if len(partes) == 2 and len(partes[0]) < 45 and len(partes[1]) < 55:
        frase = partes[0] + ' y ' + partes[1]
    return frase


def _sensacion(canal: str) -> str:
    """Sensación del canal + primera oración, sin repetir."""
    impl = _implicacion(canal)
    sens = SENSACION.get(canal, '')
    if not sens:
        return impl
    if not impl or impl in sens or sens in impl:
        return sens
    return f'{sens}; {impl}'


def _emoji_map() -> dict[int, str]:
    try:
        svg = (BASE / 'mapa.svg').read_text(encoding='utf-8')
        pares = re.findall(r'id="emoji_(\d+)"[^>]*>([^<]+)<title>', svg)
        return {int(g): em.strip() for g, em in pares if em.strip()}
    except Exception:
        return {}


_EMOJI = _emoji_map()
# El SVG no trae emoji para 35 y 45; se completan con el mapa de transitos.html.
_EMOJI.update({35: '🚀', 45: '👑'})


def _fmt_canal(canal: str, natal: set[int]) -> str:
    a, b = [int(x) for x in canal.split('-')]
    ea, eb = _EMOJI.get(a, ''), _EMOJI.get(b, '')
    sa = f'**{a}**' if a in natal else str(a)
    sb = f'**{b}**' if b in natal else str(b)
    return f'{sa}-{sb} {ea}{eb}'.strip()


def _centros_canal(canal: str) -> list[str]:
    # Orden alfabético para el paréntesis: (Ajna/Garganta), (Ego/Garganta).
    return sorted(app._HD_CANAL_CENTROS.get(canal, []))


def _fmt_centros(canal: str) -> str:
    return '/'.join(_nombre_centro(c) for c in _centros_canal(canal))


def _fusionar(ints):
    if not ints:
        return []
    ints = sorted(ints, key=lambda x: (x[0], x[1]))
    out = []
    for ini, fin, pls in ints:
        pls = set(pls) if isinstance(pls, (set, list, tuple)) else {pls}
        if not out or ini > out[-1][1] + timedelta(minutes=1):
            out.append([ini, fin, set(pls)])
        else:
            if fin > out[-1][1]:
                out[-1][1] = fin
            out[-1][2].update(pls)
    return [(a, b, set(c)) for a, b, c in out]


def _intersecar(a, b):
    out = []
    for s1, e1, p1 in a:
        for s2, e2, p2 in b:
            s, e = max(s1, s2), min(e1, e2)
            if e > s:
                out.append((s, e, set(p1) | set(p2)))
    return _fusionar(out)


def _intervalos_puertas(desde: datetime, hasta: datetime):
    """{puerta: [(inicio, fin, {planetas})]} con bordes refinados a ~1 min."""
    actual = {}
    out = {}
    t = desde
    paso = timedelta(minutes=PASO_MIN)
    while t <= hasta:
        det = app._puertas_momento(_jd(t), topocentrico=False)
        for d in det:
            pl, g = d['planeta'], int(d['puerta'])
            if pl not in actual:
                actual[pl] = (g, t)
            elif actual[pl][0] != g:
                g0, ini = actual[pl]
                borde = app._buscar_limite_tramo(_jd(t), pl, 'puerta', -1)
                bt = _local(app._jd_a_ms(borde)) if borde is not None else t
                if bt is None or bt < ini:
                    bt = t
                out.setdefault(g0, []).append((ini, bt, pl))
                actual[pl] = (g, bt)
        t += paso
    for pl, (g, ini) in actual.items():
        out.setdefault(g, []).append((ini, hasta, pl))
    return {g: _fusionar(v) for g, v in out.items()}


def _canales_temporales(ficha, puertas):
    natal = set(int(x) for x in ficha['puertas'])
    abiertos = set(ficha['centros_indefinidos'])
    out = {}
    for item in app._canales_svg_norm():
        if isinstance(item, (tuple, list)):
            x, y = int(item[0]), int(item[1])
            canal = f'{min(x, y)}-{max(x, y)}'
        else:
            canal = str(item)
        a, b = [int(x) for x in canal.split('-')]
        centros = app._HD_CANAL_CENTROS.get(canal, [])
        if not any(c in abiertos for c in centros):
            continue
        if a in natal and b in natal:
            continue
        if a in natal:
            ints = puertas.get(b, [])
        elif b in natal:
            ints = puertas.get(a, [])
        else:
            ints = _intersecar(puertas.get(a, []), puertas.get(b, []))
        if ints:
            out[canal] = ints
    return out


def _centros_temporales(abiertos, canales):
    out = {}
    for c in abiertos:
        ints = []
        for canal, lst in canales.items():
            if c in app._HD_CANAL_CENTROS.get(canal, []):
                ints.extend(lst)
        if ints:
            out[c] = _fusionar(ints)
    return out


def _activos(intervalos, t):
    return [k for k, lst in intervalos.items() if any(s <= t < e for s, e, _ in lst)]


def _canales_de_centro(canales, centro, t):
    return sorted(k for k, lst in canales.items()
                  if centro in app._HD_CANAL_CENTROS.get(k, [])
                  and any(s <= t < e for s, e, _ in lst))


def _fin_de_canal(canales, canal, t, dia_fin):
    # Un canal que termina justo a medianoche sigue "todo el día": no es evento.
    for s, e, _ in canales.get(canal, []):
        if s <= t < e and e < dia_fin:
            return e
    return None


def _canal_que_definia(canales, centro, t):
    """Canal que definía el centro en t (para el estado de ayer)."""
    ops = _canales_de_centro(canales, centro, t)
    return ops[0] if ops else None


def _fin_de_centro(canales, centro, t, dia_fin):
    """Fin del canal que definía el centro en t, si termina antes de dia_fin."""
    canal = _canal_que_definia(canales, centro, t)
    if not canal:
        return None, None
    return canal, _fin_de_canal(canales, canal, t, dia_fin)


def _texto_hoy(canales, centros, ficha, t, dia_fin):
    natal = set(int(x) for x in ficha['puertas'])
    abiertos = list(ficha['centros_indefinidos'])
    hoy_centros = _activos(centros, t)
    ayer_t = t - timedelta(days=1)

    ayer_abiertos = []
    for c in abiertos:
        if c in _activos(centros, ayer_t) and c not in hoy_centros:
            canal, fin = _fin_de_centro(canales, c, ayer_t, t)
            if canal:
                ayer_abiertos.append((c, canal, fin))

    fines = []
    for canal in canales:
        for s, e, _ in canales.get(canal, []):
            if s <= t < e and e < dia_fin:
                fines.append((e, canal, s))
    fines.sort()

    inicios = []
    for canal, lst in canales.items():
        for s, e, _ in lst:
            if t < s < dia_fin:
                inicios.append((s, canal))
    inicios.sort()

    # AYER: solo lo que cambia. Un canal que termina hoy y sigue activo, o un
    # centro que ayer estaba definido y hoy quedó abierto.
    ayer_items = []
    for c, canal, fin in ayer_abiertos:
        extra = f' hasta {_hora(fin)}' if fin else ''
        ayer_items.append(f'{_nombre_centro(c)} por {_fmt_canal(canal, natal)} ({_fmt_centros(canal)}){extra}')
    for fin, canal, ini in fines:
        if ini < dia_fin - timedelta(days=1):
            ayer_items.append(f'{_fmt_canal(canal, natal)} ({_fmt_centros(canal)})')

    # HOY
    partes = []
    mencionados = set()
    for c, canal, fin in ayer_abiertos:
        sens = _sensacion(canal)
        if sens.startswith('impulso '):
            sens = 'el ' + sens
        partes.append(f'{_nombre_centro(c)} abierto: se va {sens}.')
        mencionados.add(c)
    for fin, canal, _ in fines:
        sens = _sensacion(canal)
        extra = ''
        # Si al terminar el canal el centro queda abierto, decirlo una vez.
        for c in _centros_canal(canal):
            if c in abiertos and not _canales_de_centro(canales, c, fin + timedelta(minutes=1)):
                extra = f' {_nombre_centro(c)} queda abierto.'
                mencionados.add(c)
                break
        partes.append(f'{_fmt_canal(canal, natal)} ->| {_hora(fin)}: {sens}.{extra}')
        mencionados.update(_centros_canal(canal))
    for ini, canal in inicios:
        partes.append(f'{_fmt_canal(canal, natal)} entra {_hora(ini)}: {_implicacion(canal)}.')
        mencionados.update(_centros_canal(canal))

    # Centros que siguen definidos: agrupar por canal. Si el grupo toca un
    # centro mencionado, se muestra con su implicación; si no, va en "Siguen".
    sin_eventos = not ayer_items and not fines and not inicios and not ayer_abiertos
    event_channels = ({canal for _, canal, _ in fines}
                      | {canal for _, canal in inicios}
                      | {canal for _, canal, _ in ayer_abiertos})
    grupos = {}
    for c in hoy_centros:
        # El canal que se está yendo ya se contó como evento: no repetirlo.
        ops = tuple(k for k in _canales_de_centro(canales, c, t)
                    if k not in event_channels)
        if ops:
            grupos.setdefault(ops, []).append(c)
    siguen = []
    for canales_grupo, centros_grupo in grupos.items():
        toca = any(c in mencionados for c in centros_grupo)
        if sin_eventos or toca:
            cs = '/'.join(_nombre_centro(c) for c in centros_grupo)
            canales_txt = ', '.join(_fmt_canal(k, natal) for k in canales_grupo)
            impl = '; '.join(_implicacion(k) for k in canales_grupo)
            partes.append(f'{cs} por {canales_txt}: {impl}.')
        else:
            siguen.append((centros_grupo, canales_grupo))
    if siguen:
        items = []
        for centros_grupo, canales_grupo in siguen:
            cs = '/'.join(_nombre_centro(c) for c in centros_grupo)
            canales_txt = ', '.join(_fmt_canal(k, natal) for k in canales_grupo)
            items.append(f'{cs} ({canales_txt})')
        partes.append('Siguen ' + _lista_y(items) + '.')

    return ayer_items, partes


def _texto_manana(canales, centros, ficha, t):
    """Solo si mañana cambia el set de centros abiertos definidos."""
    natal = set(int(x) for x in ficha['puertas'])
    hoy = set(_activos(centros, t))
    man = set(_activos(centros, t + timedelta(days=1)))
    if hoy == man:
        return []
    partes = []
    for c in sorted(man - hoy, key=lambda x: ORDEN_CENTROS.index(x) if x in ORDEN_CENTROS else 99):
        ops = _canales_de_centro(canales, c, t + timedelta(days=1))
        if ops:
            partes.append(f'{_nombre_centro(c)} por {", ".join(_fmt_canal(k, natal) for k in ops)}.')
    for c in sorted(hoy - man, key=lambda x: ORDEN_CENTROS.index(x) if x in ORDEN_CENTROS else 99):
        partes.append(f'{_nombre_centro(c)} abierto.')
    return partes


def generar_briefing(persona: str, fecha: str | None = None, hora: str | None = None,
                     fuente: str | None = None, incluir_detalle: bool = False):
    """Devuelve {'ok', 'persona', 'fecha', 'hora', 'lineas', 'texto', ...}."""
    if fuente:
        app.set_fuente(fuente)
    ficha, err = app._ficha_basica_para_persona(persona)
    if err:
        return {'ok': False, 'error': err}

    ahora = _ahora_local()
    if fecha:
        d = datetime.strptime(fecha, '%Y-%m-%d')
    else:
        d = datetime(ahora.year, ahora.month, ahora.day)
    if hora:
        hh, mm = [int(x) for x in hora.split(':')[:2]]
        ref = d.replace(hour=hh, minute=mm)
    elif fecha:
        ref = d.replace(hour=9, minute=0)
    else:
        ref = datetime(ahora.year, ahora.month, ahora.day, ahora.hour, ahora.minute)

    desde = d - timedelta(days=1)
    hasta = d + timedelta(days=2)
    dia_fin = d + timedelta(days=1)

    puertas = _intervalos_puertas(desde, hasta)
    canales = _canales_temporales(ficha, puertas)
    centros = _centros_temporales(ficha['centros_indefinidos'], canales)

    ayer, hoy = _texto_hoy(canales, centros, ficha, ref, dia_fin)
    manana = _texto_manana(canales, centros, ficha, ref)

    lineas = []
    if ayer:
        lineas.append({'etiqueta': 'AYER', 'texto': ' · '.join(ayer)})
    if hoy:
        lineas.append({'etiqueta': 'HOY', 'texto': ' '.join(hoy)})
    if manana:
        lineas.append({'etiqueta': 'MAÑANA', 'texto': ' '.join(manana)})
    if not lineas:
        lineas.append({'etiqueta': 'HOY', 'texto': 'El clima sigue igual que ayer.'})

    cab = f'Briefing {d.strftime("%d/%m")} · {_hora(ref)} · {ficha["nombre"]}'
    texto = cab + '\n' + '\n'.join(f'{l["etiqueta"]}: {l["texto"]}' for l in lineas)
    out = {
        'ok': True,
        'persona': ficha['nombre'],
        'fecha': d.strftime('%Y-%m-%d'),
        'hora': _hora(ref),
        'tipo': ficha['tipo'],
        'autoridad': ficha['autoridad'],
        'lineas': lineas,
        'texto': texto,
    }
    if incluir_detalle:
        out['detalle'] = {
            'puertas': {str(g): [{'ini': s.isoformat(), 'fin': e.isoformat(), 'planetas': sorted(p)}
                                  for s, e, p in lst] for g, lst in puertas.items()},
            'canales': {k: [{'ini': s.isoformat(), 'fin': e.isoformat(), 'planetas': sorted(p)}
                             for s, e, p in lst] for k, lst in canales.items()},
            'centros': {k: [{'ini': s.isoformat(), 'fin': e.isoformat()} for s, e, _ in lst]
                        for k, lst in centros.items()},
        }
    return out


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
    p = argparse.ArgumentParser(description='Briefing diario de Diseño Humano')
    p.add_argument('--persona', required=True)
    p.add_argument('--fecha', default='', help='AAAA-MM-DD (vacío = hoy)')
    p.add_argument('--hora', default='', help='HH:MM (vacío = ahora)')
    p.add_argument('--fuente', default='', help='xlsx activo (opcional)')
    p.add_argument('--json', action='store_true')
    a = p.parse_args()
    fuente = a.fuente or None
    if not fuente:
        try:
            if app._ficha_basica_para_persona(a.persona)[0] is None and (BASE / '_viejos' / 'datos_privados.xlsx').exists():
                fuente = str(BASE / '_viejos' / 'datos_privados.xlsx')
        except Exception:
            pass
    res = generar_briefing(a.persona, a.fecha or None, a.hora or None, fuente)
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    elif res.get('ok'):
        print(res['texto'])
    else:
        print('ERROR:', res.get('error'), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
