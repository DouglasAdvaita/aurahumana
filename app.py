from flask import Flask, g, has_request_context, render_template, jsonify, request, send_from_directory, send_file, Response
import csv
import functools as _functools
import gzip as _gzip
import hashlib as _hashlib
_GZ_CACHE = {}
import io as _io
import json as _json
import os
import re as _re
import time as _time
import threading as _threading
import unicodedata
import urllib.parse as _urlparse
import urllib.request as _urlrequest
from datetime import datetime, timedelta, timezone
import pandas as pd
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
    ZONEINFO_DISPONIBLE = True
except ImportError:
    ZoneInfo = None
    ZONEINFO_DISPONIBLE = False

# .env local opcional (ignorado por git): permite GEMINI_API_KEY=... sin exponerla.
# No requiere python-dotenv.
try:
    _env_path = Path(__file__).with_name('.env')
    if _env_path.exists():
        for _line in _env_path.read_text(encoding='utf-8', errors='replace').splitlines():
            _line = _line.strip()
            if not _line or _line.startswith('#') or '=' not in _line:
                continue
            _k, _v = _line.split('=', 1)
            _k, _v = _k.strip(), _v.strip().strip('"').strip("'")
            if _k and _k not in os.environ and _k in ('DATABASE_URL', 'GEMINI_API_KEY', 'GEMINI_MODEL', 'PORT',
                    'IA_PROVIDER', 'IA_MODEL', 'IA_TIMEOUT',
                    'GROQ_API_KEY', 'GROQ_MODEL',
                    'CEREBRAS_API_KEY', 'CEREBRAS_MODEL',
                    'OPENROUTER_API_KEY', 'OPENROUTER_MODEL',
                    'OLLAMA_HOST', 'OLLAMA_MODEL',
                    'SMTP_HOST', 'SMTP_PORT', 'SMTP_USER', 'SMTP_PASS', 'SMTP_FROM',
                    'BREVO_API_KEY', 'BREVO_FROM', 'BREVO_FROM_NAME'):
                os.environ[_k] = _v
except Exception:
    pass

app = Flask(__name__)

@app.after_request
def _gzip_response(resp):
    try:
        if resp.mimetype == 'text/html':
            # Sin esto el navegador puede quedarse con el HTML viejo tras un
            # despliegue (el botón de foto parecía no responder).
            resp.headers['Cache-Control'] = 'no-cache, must-revalidate'
        if resp.status_code < 200 or resp.status_code >= 300:
            return resp
        if 'gzip' not in (request.headers.get('Accept-Encoding') or '').lower():
            return resp
        if 'Content-Encoding' in resp.headers or resp.direct_passthrough:
            return resp
        data = resp.get_data()
        if len(data) < 600:
            return resp
        mt = resp.mimetype or ''
        if mt.startswith('image/') or mt in ('application/pdf', 'application/zip') or 'openxmlformats' in mt:
            return resp  # ya comprimidos: gastar CPU no reduce nada
        # Cache de lo ya comprimido: el mismo HTML (~800 KB) no se vuelve a gzipear en cada visita.
        _k = _hashlib.blake2b(data, digest_size=16).digest()
        gz = _GZ_CACHE.get(_k)
        if gz is None:
            gz = _gzip.compress(data, compresslevel=6)
            if len(_GZ_CACHE) >= 24:
                _GZ_CACHE.pop(next(iter(_GZ_CACHE)))
            _GZ_CACHE[_k] = gz
        resp.set_data(gz)
        resp.headers['Content-Encoding'] = 'gzip'
        resp.headers['Content-Length'] = str(len(gz))
        v = resp.headers.get('Vary', '')
        resp.headers['Vary'] = (v + ', Accept-Encoding' if v else 'Accept-Encoding')
    except Exception:
        pass
    return resp

try:
    import swisseph as swe
    SWE_DISPONIBLE = True
except ImportError:
    swe = None
    SWE_DISPONIBLE = False

# Secuencia de puertas alrededor de la rueda; la 41 arranca en 302.0° (calibrado vs datos.csv).
SECUENCIA_PUERTAS = [41, 19, 13, 49, 30, 55, 37, 63, 22, 36, 25, 17, 21, 51, 42, 3, 27, 24, 2, 23, 8, 20, 16, 35, 45, 12, 15, 52, 39, 53, 62, 56, 31, 33, 7, 4, 29, 59, 40, 64, 47, 6, 46, 18, 48, 57, 32, 50, 28, 44, 1, 43, 14, 34, 9, 5, 26, 11, 10, 58, 38, 54, 61, 60]
OFFSET_PUERTA_41 = 302.0

LUGARES = {
    'montevideo': (-34.9011, -56.1645, -3.0),
    'buenos aires': (-34.6037, -58.3816, -3.0),
    'la paz': (-16.4897, -68.1193, -4.0),
    'rosario': (-32.9468, -60.6393, -3.0),
    'caracas': (10.4806, -66.9036, -4.0),
    'sarajevo': (43.8563, 18.4131, 1.0),
    'sarajebo': (43.8563, 18.4131, 1.0),
    'mumbai': (19.0760, 72.8777, 5.5),
    'bombay': (19.0760, 72.8777, 5.5),
    'guangyuan': (32.4396, 105.8434, 8.0),
    'melo': (-32.3653, -54.1876, -3.0),
    'colonia': (-34.4727, -57.8448, -3.0),
    'colonia del sacramento': (-34.4727, -57.8448, -3.0),
    'punta del este': (-34.9396, -54.9491, -3.0),
    'maldonado': (-34.9081, -54.9587, -3.0),
    'canelones': (-34.5228, -56.2819, -3.0),
    'salto': (-31.3890, -57.9687, -3.0),
    'paysandu': (-32.3214, -58.0756, -3.0),
    'paysandú': (-32.3214, -58.0756, -3.0),
    'rivera': (-30.9053, -55.5509, -3.0),
    'artigas': (-30.4707, -56.4703, -3.0),
    'santiago': (-33.4489, -70.6693, -4.0),
    'santiago de chile': (-33.4489, -70.6693, -4.0),
    'san pablo': (-23.5558, -46.6396, -3.0),
    'sao paulo': (-23.5558, -46.6396, -3.0),
    'madrid': (40.4168, -3.7038, 1.0),
    'nueva york': (40.7128, -74.0060, -5.0),
    'new york': (40.7128, -74.0060, -5.0),
    'miami': (25.7617, -80.1918, -5.0),
    'ciudad de mexico': (19.4326, -99.1332, -6.0),
    'mexico df': (19.4326, -99.1332, -6.0),
}

_NOMBRES_LUGAR = {
    'montevideo': 'Montevideo', 'buenos aires': 'Buenos Aires', 'la paz': 'La Paz',
    'rosario': 'Rosario', 'caracas': 'Caracas', 'sarajevo': 'Sarajevo',
    'mumbai': 'Mumbai', 'guangyuan': 'Guangyuan', 'melo': 'Melo',
    'colonia del sacramento': 'Colonia del Sacramento', 'punta del este': 'Punta del Este',
    'maldonado': 'Maldonado', 'canelones': 'Canelones', 'salto': 'Salto',
    'paysandu': 'Paysandú', 'rivera': 'Rivera', 'artigas': 'Artigas',
    'santiago de chile': 'Santiago de Chile', 'sao paulo': 'São Paulo', 'madrid': 'Madrid',
    'nueva york': 'Nueva York', 'miami': 'Miami', 'ciudad de mexico': 'Ciudad de México',
}

def _etiqueta_lugar(clave):
    tz = LUGARES[clave][2]
    nombre = _NOMBRES_LUGAR.get(clave, clave.title())
    return f'{nombre} (UTC{tz:+g})'

@app.route('/api/lugares')
def api_lugares():
    vistos = set()
    out = []
    for clave in LUGARES:
        nombre = _NOMBRES_LUGAR.get(clave, clave)
        if nombre in vistos:
            continue
        vistos.add(nombre)
        out.append({'id': clave, 'label': _etiqueta_lugar(clave)})
    return jsonify(sorted(out, key=lambda x: x['label']))

# ---------- Geocoding autocomplete (Open-Meteo, sin API key) ----------
# El frontend escribe la ciudad y este proxy devuelve candidatos con
# lat/lon + zona IANA (ej. America/Montevideo). Proxyamos en el backend
# para evitar CORS/adblockers y poder cachear. Fallback: /api/lugares.
_GEO_CACHE = {}
_GEO_UA = {'User-Agent': 'DisenioHumanoApp/1.0 (local)'}

@app.route('/api/geo')
def api_geo():
    q = (request.args.get('q') or '').strip()
    if len(q) < 2:
        return jsonify([])
    try:
        n = max(1, min(int(request.args.get('count') or 8), 12))
    except (ValueError, TypeError):
        n = 8
    lang = (request.args.get('lang') or 'es').strip() or 'es'
    clave = f'{q.lower()}|{n}|{lang}'
    if clave in _GEO_CACHE:
        return jsonify(_GEO_CACHE[clave])
    params = _urlparse.urlencode({'name': q, 'count': n, 'language': lang, 'format': 'json'})
    url = f'https://geocoding-api.open-meteo.com/v1/search?{params}'
    try:
        req = _urlrequest.Request(url, headers=_GEO_UA)
        with _urlrequest.urlopen(req, timeout=8) as resp:
            data = _json.loads(resp.read().decode('utf-8', 'replace'))
    except Exception as e:
        return jsonify({'error': f'Geocoding no disponible: {e}'}), 502
    out = []
    for r in (data.get('results') or [])[:n]:
        nombre = r.get('name') or ''
        admin = r.get('admin1') or ''
        pais = r.get('country') or ''
        tz = r.get('timezone') or ''
        etiqueta = ', '.join([p for p in (nombre, admin, pais) if p])
        if tz:
            etiqueta += f' ({tz})'
        out.append({
            'label': etiqueta or nombre,
            'nombre': nombre, 'admin': admin, 'pais': pais,
            'lat': r.get('latitude'), 'lon': r.get('longitude'),
            'tz_name': tz,
        })
    _GEO_CACHE[clave] = out
    return jsonify(out)

def _offset_de_zona(dt_naive, tz_name):
    """Offset UTC en horas de una zona IANA para una fecha local dada. None si no se puede."""
    if not ZONEINFO_DISPONIBLE or not tz_name:
        return None
    try:
        aware = dt_naive.replace(tzinfo=ZoneInfo(str(tz_name).strip()))
        off = aware.utcoffset()
        if off is None:
            return None
        return off.total_seconds() / 3600.0
    except Exception:
        return None

def _norm_lugar(s):
    s = unicodedata.normalize('NFKD', str(s or '')).encode('ascii', 'ignore').decode()
    return ' '.join(s.lower().split())

def _puerta_de_lon(lon):
    idx = int((((lon - OFFSET_PUERTA_41) % 360) / 360) * 64) % 64
    return SECUENCIA_PUERTAS[idx]

def _linea_de_lon(lon):
    """Línea 1-6 dentro de la puerta (cada puerta = 5.625°, cada línea = 0.9375°)."""
    pos = (((lon - OFFSET_PUERTA_41) % 360) / 360) * 64
    frac = pos - int(pos)
    return int(frac * 6) % 6 + 1

def _puerta_linea_de_lon(lon):
    idx = int((((lon - OFFSET_PUERTA_41) % 360) / 360) * 64) % 64
    frac = ((((lon - OFFSET_PUERTA_41) % 360) / 360) * 64) - int((((lon - OFFSET_PUERTA_41) % 360) / 360) * 64)
    return SECUENCIA_PUERTAS[idx], int(frac * 6) % 6 + 1

def _perfil_de_lineas(linea_sol_consc, linea_sol_inconsc):
    try:
        a, b = int(linea_sol_consc), int(linea_sol_inconsc)
        if 1 <= a <= 6 and 1 <= b <= 6:
            return f'{a}/{b}'
    except (ValueError, TypeError):
        pass
    return None

@_functools.lru_cache(maxsize=4096)
def _lon_sol(jd):
    return swe.calc_ut(jd, swe.SUN, swe.FLG_SWIEPH)[0][0] % 360

@_functools.lru_cache(maxsize=1024)
def _jd_diseno(jd_natal):
    """Momento en que el Sol estaba 88° antes (Newton sobre longitud solar)."""
    objetivo = (_lon_sol(jd_natal) - 88.0) % 360
    jd = jd_natal - 88.0
    for _ in range(60):
        f = ((_lon_sol(jd) - objetivo + 180) % 360) - 180
        if abs(f) < 1e-7:
            break
        a = _lon_sol(jd + 0.05)
        b = _lon_sol(jd - 0.05)
        v = (((a - b + 180) % 360) - 180) / 0.1 or 1.0
        jd -= f / v
    return jd

_PLANETAS = None
def _planetas():
    global _PLANETAS
    if _PLANETAS is None:
        _PLANETAS = [('Sol', swe.SUN), ('Luna', swe.MOON), ('NodoN', swe.TRUE_NODE),
                     ('Mercurio', swe.MERCURY), ('Venus', swe.VENUS), ('Marte', swe.MARS),
                     ('Jupiter', swe.JUPITER), ('Saturno', swe.SATURN), ('Urano', swe.URANUS),
                     ('Neptuno', swe.NEPTUNE), ('Pluton', swe.PLUTO)]
    return _PLANETAS

_CACHE_PUERTAS = {}
_CACHE_GATE = {'mtime': None, 'val': None}
_JD_UNIX = 2440587.5  # JD de 1970-01-01T00:00Z

def _jd_a_ms(jd):
    try:
        return int((float(jd) - _JD_UNIX) * 86400000)
    except (ValueError, TypeError):
        return None

def _lon_planeta_transito(jd, planeta):
    """Longitud eclíptica (geocéntrica, sin topo) para el cálculo de duraciones de tránsito."""
    f = swe.FLG_SWIEPH
    if planeta == 'Tierra':
        return (swe.calc_ut(jd, swe.SUN, f)[0][0] + 180.0) % 360
    if planeta == 'NodoS':
        return (swe.calc_ut(jd, swe.TRUE_NODE, f)[0][0] + 180.0) % 360
    for nombre, pid in _planetas():
        if nombre == planeta:
            return swe.calc_ut(jd, pid, f)[0][0] % 360
    return None

def _clave_tramo(jd, planeta, nivel):
    lon = _lon_planeta_transito(jd, planeta)
    if lon is None:
        return None
    puerta, linea = _puerta_linea_de_lon(lon)
    return puerta if nivel == 'puerta' else (puerta, linea)

def _buscar_limite_tramo(jd_ref, planeta, nivel='puerta', direccion=-1):
    """JD del cambio de puerta (o línea) más cercano en una dirección.

    Intervalo contiguo que contiene a jd_ref (vale con retrógrados).
    None si sigue igual tras ~6 años o si hay error.
    """
    try:
        ref = _clave_tramo(jd_ref, planeta, nivel)
        if ref is None:
            return None
        paso = 10.0 / 1440.0  # 10 min en días
        max_dias = 6 * 365.25
        ultimo_igual = float(jd_ref)
        acumulado = 0.0
        jd_distinto = None
        while acumulado < max_dias:
            cand = ultimo_igual + direccion * paso
            if _clave_tramo(cand, planeta, nivel) != ref:
                jd_distinto = cand
                break
            ultimo_igual = cand
            acumulado += paso
            paso *= 2.0
        if jd_distinto is None:
            return None
        lo = min(ultimo_igual, jd_distinto)
        hi = max(ultimo_igual, jd_distinto)
        for _ in range(32):
            if (hi - lo) < (1.0 / 1440.0):  # precisión ~1 min
                break
            mid = (lo + hi) / 2.0
            if _clave_tramo(mid, planeta, nivel) == ref:
                if direccion < 0:
                    hi = mid
                    # lo es distinto, hi es igual -> el borde está entre ambos;
                    # reordenamos: mantener invariante lo=distinto? simplificar:
                    # en dirección -1, ultimo_igual > jd_distinto.
                    pass
                else:
                    lo = mid
            else:
                if direccion < 0:
                    lo = mid
                else:
                    hi = mid
            # Corrección del invariante para dirección -1:
            # queremos lo=distinto(pass), hi=igual. Tras el paso de arriba:
            # - si mid es igual y direccion<0 -> hi=mid (ok, lo sigue distinto)
            # - si mid es distinto y direccion<0 -> lo=mid (ok)
            # Para dirección +1: lo=igual, hi=distinto (mismo código vale).
            # El bloque de arriba ya lo cumple; el `pass` es solo claridad.
        # El instante del cambio está entre lo y hi; devolver el lado igual
        # (inicio = primer momento igual al ir hacia atrás => hi; fin => lo... )
        # En ambas direcciones el borde útil es el extremo igual:
        return hi if direccion < 0 else lo
    except Exception:
        return None

def _duraciones_transito(jd_ref, detalle):
    """Anexa inicio/fin (ms UTC) de puerta y línea contiguas a cada entrada del detalle."""
    for d in detalle:
        planeta = d.get('planeta')
        try:
            ini_p = _buscar_limite_tramo(jd_ref, planeta, 'puerta', -1)
            fin_p = _buscar_limite_tramo(jd_ref, planeta, 'puerta', +1)
            ini_l = _buscar_limite_tramo(jd_ref, planeta, 'linea', -1)
            fin_l = _buscar_limite_tramo(jd_ref, planeta, 'linea', +1)
        except Exception:
            ini_p = fin_p = ini_l = fin_l = None
        d['inicio_puerta_ms'] = _jd_a_ms(ini_p) if ini_p is not None else None
        d['fin_puerta_ms'] = _jd_a_ms(fin_p) if fin_p is not None else None
        d['inicio_linea_ms'] = _jd_a_ms(ini_l) if ini_l is not None else None
        d['fin_linea_ms'] = _jd_a_ms(fin_l) if fin_l is not None else None
    return detalle
def _puertas_momento(jd, topocentrico=True):
    key = (round(float(jd), 4), bool(topocentrico))
    if key in _CACHE_PUERTAS:
        # copia profunda ligera para evitar mutación
        return [dict(d) for d in _CACHE_PUERTAS[key]]
    flags = swe.FLG_SWIEPH | (swe.FLG_TOPOCTR if topocentrico else 0)
    lons = {}
    for nombre, p in _planetas():
        lons[nombre] = swe.calc_ut(jd, p, flags)[0][0] % 360
    lons['Tierra'] = (lons['Sol'] + 180) % 360
    lons['NodoS'] = (lons['NodoN'] + 180) % 360
    orden = ['Sol', 'Tierra', 'Luna', 'NodoN', 'NodoS', 'Mercurio', 'Venus',
             'Marte', 'Jupiter', 'Saturno', 'Urano', 'Neptuno', 'Pluton']
    out = []
    for k in orden:
        puerta, linea = _puerta_linea_de_lon(lons[k])
        out.append({'planeta': k, 'longitud': round(lons[k], 3), 'puerta': puerta, 'linea': linea})
    # limitar cache a 8192 entradas (la gráfica de tránsitos usa ~900 de una vez)
    if len(_CACHE_PUERTAS) > 8192:
        _CACHE_PUERTAS.clear()
    _CACHE_PUERTAS[key] = [dict(d) for d in out]
    return out

def _lugar_a_coords(s):
    """Nombre conocido (con alias) o 'lat, lon, tz'. Devuelve (lat, lon, tz, nota, error)."""
    clave = _norm_lugar(s)
    if clave in LUGARES:
        lat, lon, tz = LUGARES[clave]
        return lat, lon, tz, None, None
    sin_esp = clave.replace(' ', '')
    for k, v in LUGARES.items():
        if k.replace(' ', '') == sin_esp:
            return v[0], v[1], v[2], None, None
    try:
        partes = [float(x.strip()) for x in str(s or '').replace(';', ',').split(',')]
        if len(partes) in (2, 3) and -90 <= partes[0] <= 90 and -180 <= partes[1] <= 180:
            tz = partes[2] if len(partes) == 3 else 0.0
            if -14 <= tz <= 14:
                nota = None if len(partes) == 3 else 'Sin zona horaria: se asume UTC, verificar'
                return partes[0], partes[1], tz, nota, None
    except (ValueError, AttributeError):
        pass
    return None, None, None, None, f'Lugar desconocido. Conocidos: {", ".join(sorted(LUGARES))} o "lat, lon, tz" (ej. -34.9, -56.2, -3)'

def _parse_nacimiento(data):
    """Valida {fecha DD/MM/AAAA, hora HH:MM opcional, lugar} -> (jd_utc, warnings, etiqueta, error)."""
    if not SWE_DISPONIBLE:
        return None, None, None, 'Falta el paquete pyswisseph (pip install pyswisseph)'
    try:
        d, m, y = [int(x) for x in str(data.get('fecha', '')).split('/')]
        dt = datetime(y, m, d)
    except (ValueError, AttributeError):
        return None, None, None, 'Fecha inválida (usar DD/MM/AAAA)'
    warnings = []
    hora_txt = str(data.get('hora', '') or '').strip()
    if hora_txt:
        try:
            hh, mm = [int(x) for x in hora_txt.split(':')]
            dt = dt.replace(hour=hh, minute=mm)
        except (ValueError, AttributeError):
            return None, None, None, 'Hora inválida (usar HH:MM 24h)'
    else:
        dt = dt.replace(hour=12, minute=0)
        warnings.append('Sin hora: se asume 12:00 del mediodía, la Luna es aproximada')
    lat, lon, tzh = data.get('lat'), data.get('lon'), data.get('tz')
    tz_name = str(data.get('tz_name') or data.get('zona') or data.get('tzname') or '').strip()
    if lat is not None or lon is not None or tzh is not None or tz_name:
        try:
            lat, lon = float(lat), float(lon)
            if tzh not in (None, ''):
                tz = float(tzh)
            elif tz_name:
                tz = _offset_de_zona(dt, tz_name)
                if tz is None:
                    return None, None, None, f'Zona horaria desconocida: {tz_name}'
                warnings.append(f'Zona {tz_name} (UTC{tz:+g} en esa fecha)')
            else:
                tz = 0.0
            if not (-90 <= lat <= 90 and -180 <= lon <= 180 and -14 <= tz <= 14):
                raise ValueError()
        except (ValueError, TypeError):
            return None, None, None, 'Coordenadas inválidas (lat -90..90, lon -180..180, tz -14..14)'
        if tzh in (None, '') and not tz_name:
            warnings.append('Sin zona horaria: se asume UTC, verificar')
        etiqueta = f'{lat}, {lon} (UTC{tz:+g})'
    else:
        lat, lon, tz, nota, err = _lugar_a_coords(data.get('lugar', ''))
        if err:
            return None, None, None, err
        if nota:
            warnings.append(nota)
        etiqueta = f'{str(data.get("lugar", "")).strip()} (UTC{tz:+g})'
    swe.set_topo(lon, lat, 0)
    utc = dt - timedelta(hours=tz)
    jd = swe.julday(utc.year, utc.month, utc.day, utc.hour + utc.minute / 60.0 + utc.second / 3600.0)
    return jd, warnings, f'{str(data.get("lugar", "")).strip()} (UTC{tz:+g})', None

@app.route('/api/calcular', methods=['POST'])
def api_calcular():
    """Calcula las 26 puertas (+ líneas y perfil) desde fecha/hora/lugar. Inconscientes=diseño, conscientes=personalidad."""
    data = request.get_json(force=True, silent=True) or {}
    jd, warnings, etiqueta, err = _parse_nacimiento(data)
    if err:
        return jsonify({'error': err}), (501 if 'pyswisseph' in err else 400)
    personalidad = _puertas_momento(jd, topocentrico=False)
    diseno = _puertas_momento(_jd_diseno(jd), topocentrico=False)
    perfil = _perfil_de_lineas(personalidad[0]['linea'], diseno[0]['linea'])
    return jsonify({
        'inconscientes': [d['puerta'] for d in diseno],  # orden planeta: Sol..Plutón
        'conscientes': [d['puerta'] for d in personalidad],
        'inconscientes_lineas': [d['linea'] for d in diseno],
        'conscientes_lineas': [d['linea'] for d in personalidad],
        'perfil': perfil,
        'detalle_personalidad': personalidad,
        'detalle_diseno': diseno,
        'warnings': warnings,
    })

def _tipo_perfil_en_jd(jd):
    """Tipo/autoridad/perfil/definición para un instante (misma lógica que la ficha BASICO)."""
    personalidad = _puertas_momento(jd, topocentrico=False)
    diseno = _puertas_momento(_jd_diseno(jd), topocentrico=False)
    perfil = _perfil_de_lineas(personalidad[0]['linea'], diseno[0]['linea'])
    puertas = set([d['puerta'] for d in personalidad] + [d['puerta'] for d in diseno])
    canales = _hd_canales_de_puertas(puertas)
    centros = _hd_centros_definidos(canales)
    tipo, autoridad = _hd_tipo_autoridad(centros, canales)
    definicion = _hd_definicion(centros, canales)
    return tipo, autoridad, perfil, definicion

@app.route('/api/dia', methods=['POST'])
def api_dia():
    """Panel del día: hora por hora (00-23, hora local del lugar) Tipo y Perfil. Hora recibida se ignora."""
    data = request.get_json(force=True, silent=True) or {}
    if not str(data.get('fecha', '')).strip():
        return jsonify({'error': 'Fecha inválida (usar DD/MM/AAAA)'}), 400
    # Validar fecha + lugar una vez (hora 12) para errores legibles.
    jd0, warnings, etiqueta, err = _parse_nacimiento({**data, 'hora': '12:00'})
    if err:
        return jsonify({'error': err}), (501 if 'pyswisseph' in err else 400)
    horas = []
    for h in range(24):
        jd, _, _, errh = _parse_nacimiento({**data, 'hora': f'{h:02d}:00'})
        if errh:
            return jsonify({'error': errh}), 400
        tipo, autoridad, perfil, definicion = _tipo_perfil_en_jd(jd)
        horas.append({'hora': f'{h:02d}:00', 'tipo': tipo, 'perfil': perfil,
                      'autoridad': autoridad, 'definicion': definicion})
    return jsonify({'horas': horas, 'warnings': warnings, 'etiqueta': etiqueta})

@app.route('/api/transito')
def api_transito():
    """Tránsito del momento (o de ?fecha=AAAA-MM-DD[THH:MM], hora de Montevideo UTC-3)."""
    if not SWE_DISPONIBLE:
        return jsonify({'error': 'Falta el paquete pyswisseph (pip install pyswisseph)'}), 501
    f = (request.args.get('fecha') or '').strip()
    if f:
        try:
            if 'T' in f:
                dpart, tpart = f.split('T')
                y, m, d = [int(x) for x in dpart.split('-')]
                hh, mm = [int(x) for x in tpart.split(':')[:2]]
                base = datetime(y, m, d, hh, mm) + timedelta(hours=3)  # Montevideo -> UTC
                nombre = f'Transito {d}-{m}-{str(y)[2:]} {hh:02d}:{mm:02d}'
            else:
                y, m, d = [int(x) for x in f.split('-')]
                base = datetime(y, m, d, 12, 0) + timedelta(hours=3)
                nombre = f'Transito {d}-{m}-{str(y)[2:]}'
            base = base.replace(tzinfo=timezone.utc)
        except (ValueError, AttributeError):
            return jsonify({'error': 'Fecha inválida (AAAA-MM-DD[THH:MM])'}), 400
    else:
        base = datetime.now(timezone.utc)
        montevideo = base + timedelta(hours=-3)
        nombre = f'Transito {montevideo.day}-{montevideo.month}-{str(montevideo.year)[2:]} {montevideo.hour:02d}:{montevideo.minute:02d}'
    jd = swe.julday(base.year, base.month, base.day, base.hour + base.minute / 60.0)
    det = _puertas_momento(jd, topocentrico=False)
    try:
        _duraciones_transito(jd, det)
    except Exception:
        pass
    return jsonify({
        'nombre': nombre,
        't_ms': int(base.timestamp() * 1000),
        'inconscientes': [],
        'conscientes': [d['puerta'] for d in det],  # orden planeta: Sol..Plutón
        'detalle': det,
    })

def _canales_svg_norm():
    """Pares normalizados de los 36 canales del SVG (caché en memoria)."""
    if not hasattr(_canales_svg_norm, 'cache'):
        import re
        ids = re.findall(r'id="(c\d+-\d+)"', cargar_svg())
        pares = set()
        for c in ids:
            m = re.match(r'c(\d+)-(\d+)', c)
            a, b = sorted((int(m.group(1)), int(m.group(2))))
            pares.add((a, b))
        _canales_svg_norm.cache = sorted(pares)
    return _canales_svg_norm.cache

@app.route('/api/transitos', methods=['POST'])
def api_transitos():
    """Tránsitos día a día para Persona 1: contactos y canales que se forman con sus puertas."""
    if not SWE_DISPONIBLE:
        return jsonify({'error': 'Falta el paquete pyswisseph (pip install pyswisseph)'}), 501
    data = request.get_json(force=True, silent=True) or {}
    try:
        set_a = set(int(x) for x in (data.get('puertas') or []))
    except (ValueError, TypeError):
        return jsonify({'error': 'Puertas inválidas'}), 400
    if not set_a:
        return jsonify({'error': 'Sin puertas de Persona 1'}), 400
    try:
        dias = max(1, min(int(data.get('dias', 14)), 30))
        paso_h = max(1, min(int(data.get('paso_horas', 24)), 24 * 7))
    except (ValueError, TypeError):
        return jsonify({'error': 'Rango inválido'}), 400
    pares = set(_canales_svg_norm())
    import math
    if math.ceil(dias * 24 / paso_h) > 200:
        return jsonify({'error': 'Rango muy denso (máx 200 puntos)'}), 400
    inicio = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    DOW3 = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom']
    filas = []
    t = inicio
    while (t - inicio).days < dias:
        jd = swe.julday(t.year, t.month, t.day, t.hour + t.minute / 60.0)
        det = _puertas_momento(jd, topocentrico=False)
        set_t = set(d['puerta'] for d in det)
        contactos, canales = [], set()
        for g in sorted(set_t):
            for h in sorted(set_a):
                a, b = (g, h) if g < h else (h, g)
                if (a, b) in pares:
                    contactos.append({'t': g, 'socio': h, 'canal': f'{a}-{b}'})
                    canales.add(f'{a}-{b}')
        # Canales completos dentro del propio tránsito (las dos puertas activas
        # en el cielo, aunque la persona no aporte ninguna). Ej. 30-41 cuando
        # el Nodo trae 30 y Plutón trae 41: antes no aparecían en el cuadro
        # porque solo se listaban los electromagnéticos con la persona.
        propios = set()
        st = sorted(set_t)
        for i in range(len(st)):
            for j in range(i + 1, len(st)):
                if (st[i], st[j]) in pares:
                    propios.add(f'{st[i]}-{st[j]}')
        filas.append({
            'fecha': t.strftime('%d/%m %H:00'),
            'dow': DOW3[t.weekday()],
            'contactos': contactos,
            'canales': sorted(canales, key=lambda c: [int(x) for x in c.split('-')]),
            'canales_transito': sorted(propios, key=lambda c: [int(x) for x in c.split('-')]),
            'puertas_transito': sorted(set_t),
        })
        t += timedelta(hours=paso_h)
    return jsonify({'filas': filas})

@app.route('/api/transitos_rango', methods=['POST'])
def api_transitos_rango():
    """Batch rápido: puertas de tránsito cada 4h entre desde/hasta (fechas Montevideo)."""
    if not SWE_DISPONIBLE:
        return jsonify({'error': 'Falta el paquete pyswisseph (pip install pyswisseph)'}), 501
    data = request.get_json(force=True, silent=True) or {}
    desde_s = (data.get('desde') or '').strip()
    hasta_s = (data.get('hasta') or '').strip()
    try:
        paso_h = max(1, min(int(data.get('paso_horas', 4)), 24))
    except (ValueError, TypeError):
        paso_h = 4
    if not desde_s or not hasta_s:
        return jsonify({'error': 'Faltan desde/hasta (AAAA-MM-DDTHH:MM)'}), 400
    def _parse_local(s):
        # s es datetime-local de Montevideo (UTC-3) como en /api/transito
        if 'T' in s:
            dpart, tpart = s.split('T')
            y, m, d = [int(x) for x in dpart.split('-')]
            hh, mm = [int(x) for x in tpart.split(':')[:2]]
            base = datetime(y, m, d, hh, mm) + timedelta(hours=3)
        else:
            y, m, d = [int(x) for x in s.split('-')]
            base = datetime(y, m, d, 12, 0) + timedelta(hours=3)
        return base.replace(tzinfo=timezone.utc)
    try:
        t0 = _parse_local(desde_s)
        t1 = _parse_local(hasta_s)
    except (ValueError, AttributeError):
        return jsonify({'error': 'Fecha inválida (AAAA-MM-DDTHH:MM)'}), 400
    if t1 <= t0:
        return jsonify({'error': 'hasta debe ser posterior a desde'}), 400
    paso = timedelta(hours=paso_h)
    n = int((t1 - t0) / paso) + 1
    if n > 5000:
        return jsonify({'error': f'Rango muy grande ({n} puntos, máx 5000)'}), 400
    filas = []
    t = t0
    while t <= t1:
        jd = swe.julday(t.year, t.month, t.day, t.hour + t.minute/60.0 + t.second/3600.0)
        det = _puertas_momento(jd, topocentrico=False)
        puertas = sorted(set(d['puerta'] for d in det))
        # Planeta en puerta: el briefing compara el clima de hoy contra el de ayer.
        planetas = [{'planeta': d['planeta'], 'puerta': d['puerta'], 'linea': d['linea']}
                    for d in det]
        filas.append({'t': int(t.timestamp()*1000), 'puertas': puertas, 'planetas': planetas})
        t += paso
    return jsonify({'filas': filas, 'paso_horas': paso_h})

def _parse_fecha_transito(f):
    """'AAAA-MM-DD[THH:MM]' (hora Montevideo UTC-3) -> (base_utc, nombre, error). '' -> ahora."""
    f = (f or '').strip()
    if f:
        try:
            if 'T' in f:
                dpart, tpart = f.split('T')
                y, m, d = [int(x) for x in dpart.split('-')]
                hh, mm = [int(x) for x in tpart.split(':')[:2]]
                base = datetime(y, m, d, hh, mm) + timedelta(hours=3)  # Montevideo -> UTC
                nombre = f'Transito {d}-{m}-{str(y)[2:]} {hh:02d}:{mm:02d}'
            else:
                y, m, d = [int(x) for x in f.split('-')]
                base = datetime(y, m, d, 12, 0) + timedelta(hours=3)
                nombre = f'Transito {d}-{m}-{str(y)[2:]}'
            return base.replace(tzinfo=timezone.utc), nombre, None
        except (ValueError, AttributeError):
            return None, None, 'Fecha inválida (AAAA-MM-DD[THH:MM])'
    base = datetime.now(timezone.utc)
    montevideo = base + timedelta(hours=-3)
    nombre = f'Transito {montevideo.day}-{montevideo.month}-{str(montevideo.year)[2:]} {montevideo.hour:02d}:{montevideo.minute:02d}'
    return base, nombre, None

def _jd_de_utc(dt):
    return swe.julday(dt.year, dt.month, dt.day, dt.hour + dt.minute / 60.0 + dt.second / 3600.0)

def _puerta_de_planeta_en(jd, planeta):
    lon = _lon_planeta_transito(jd, planeta)
    if lon is None:
        return None
    return _puerta_linea_de_lon(lon)[0]

def _primer_ocupante(jd, puerta):
    """Primer planeta (orden Sol..Plutón) que ocupa la puerta en jd, o None."""
    try:
        for d in _puertas_momento(jd, topocentrico=False):
            if d['puerta'] == puerta:
                return d['planeta']
    except Exception:
        pass
    return None

@app.route('/api/proximo_puerta')
def api_proximo_puerta():
    """Próximo ingreso a una puerta desde ?fecha= (o ahora). Rápido (~60ms).

    La Luna visita las 64 puertas cada ~27 días, así que un barrido compartido
    de 40 días a paso 6h siempre encuentra al próximo ocupante (el mínimo entre
    todos los planetas). Entrada refinada por bisección, salida exacta.
    """
    if not SWE_DISPONIBLE:
        return jsonify({'error': 'Falta el paquete pyswisseph (pip install pyswisseph)'}), 501
    try:
        puerta = int(request.args.get('puerta'))
        assert 1 <= puerta <= 64
    except (ValueError, TypeError, AssertionError):
        return jsonify({'error': 'Puerta inválida (1-64)'}), 400
    base, _nombre, err = _parse_fecha_transito(request.args.get('fecha'))
    if err:
        return jsonify({'error': err}), 400
    jd_ref = _jd_de_utc(base)
    ref_ms = int(base.timestamp() * 1000)
    ocup = [d['planeta'] for d in _puertas_momento(jd_ref, topocentrico=False) if d['puerta'] == puerta]
    if ocup:
        return jsonify({'puerta': puerta, 'ref_ms': ref_ms, 'actual': True, 'ocupantes': ocup})
    paso = 6.0 / 24.0
    jd = jd_ref + paso
    limite = jd_ref + 40.0
    entrada_jd, planeta = None, None
    while jd <= limite:
        p = _primer_ocupante(jd, puerta)
        if p:
            entrada_jd, planeta = jd, p
            break
        jd += paso
    if entrada_jd is None:
        return jsonify({'puerta': puerta, 'ref_ms': ref_ms, 'proximo': None,
                        'motivo': 'Sin ingreso en los próximos 40 días'})
    prev = entrada_jd - paso
    n = 0
    while n < 3 and prev > jd_ref and _puerta_de_planeta_en(prev, planeta) == puerta:
        entrada_jd = prev
        prev -= paso
        n += 1
    lo, hi = prev, entrada_jd  # lo distinto, hi igual
    for _ in range(24):
        if (hi - lo) < (1.0 / 1440.0):  # ~1 min
            break
        mid = (lo + hi) / 2.0
        if _puerta_de_planeta_en(mid, planeta) == puerta:
            hi = mid
        else:
            lo = mid
    fin_jd = _buscar_limite_tramo(entrada_jd, planeta, 'puerta', +1)
    return jsonify({
        'puerta': puerta, 'ref_ms': ref_ms, 'actual': False,
        'planeta': planeta,
        'entrada_ms': _jd_a_ms(hi),
        'salida_ms': _jd_a_ms(fin_jd) if fin_jd is not None else None,
    })

@app.route('/api/grafica_transitos', methods=['POST'])
def api_grafica_transitos():
    """Gráfica del cielo sin personas: ventana fija ref-3d..ref+7d en slots de 4h.

    Devuelve slots (puertas+canales por slot), rachas contiguas por puerta y
    canal (con extensión real en los bordes) y próximo rango para las vacías
    (barrido 6h hasta +200d). Todo queda en window.GRAFICA_TRANSITOS para la IA.
    """
    if not SWE_DISPONIBLE:
        return jsonify({'error': 'Falta el paquete pyswisseph (pip install pyswisseph)'}), 501
    data = request.get_json(force=True, silent=True) or {}
    base, nombre, err = _parse_fecha_transito(str(data.get('fecha') or ''))
    if err:
        return jsonify({'error': err}), 400
    ref_ms = int(base.timestamp() * 1000)
    desde = base - timedelta(days=3)
    hasta = base + timedelta(days=7)
    paso = timedelta(hours=4)
    pares = _canales_svg_norm()
    slots, detalle_slots, slots_jd = [], [], []
    t = desde
    while t <= hasta:
        jd = _jd_de_utc(t)
        det = _puertas_momento(jd, topocentrico=False)
        mp = {d['planeta']: d['puerta'] for d in det}
        ml = {d['planeta']: d['linea'] for d in det}
        st = set(mp.values())
        cn = sorted(f'{a}-{b}' for (a, b) in pares if a in st and b in st)
        por_puerta = {}
        for d in det:
            por_puerta.setdefault(str(d['puerta']), {'l': [], 'p': []})
            por_puerta[str(d['puerta'])]['l'].append(d['linea'])
            por_puerta[str(d['puerta'])]['p'].append(d['planeta'])
        lineas = {g: sorted(set(v['l'])) for g, v in por_puerta.items()}
        quienes = {g: v['p'] for g, v in por_puerta.items()}
        slots.append({'t': int(t.timestamp() * 1000), 'puertas': sorted(st), 'canales': cn,
                      'lineas': lineas, 'quienes': quienes})
        detalle_slots.append(mp)
        slots_jd.append(jd)
        t += paso
    nslots = len(slots)

    def _rachas(es_activo, planetas_en):
        """Rachas contiguas de slots activos. planetas_en(i) -> lista de planetas."""
        out = []
        s = None
        pls = set()
        for i in range(nslots):
            if es_activo(i):
                if s is None:
                    s = i
                    pls = set()
                pls.update(planetas_en(i))
            elif s is not None:
                out.append((s, i - 1, sorted(pls)))
                s = None
        if s is not None:
            out.append((s, nslots - 1, sorted(pls)))
        return out

    rangos_puertas, rangos_canales = {}, {}
    for g in range(1, 65):
        runs = _rachas(lambda i, g=g: g in slots[i]['puertas'],
                       lambda i, g=g: [p for p, gv in detalle_slots[i].items() if gv == g])
        lst = []
        for (s, e, pls) in runs:
            r = {'ini_ms': slots[s]['t'], 'fin_ms': slots[e]['t'], 'planetas': pls,
                 'toca_ini': s == 0, 'toca_fin': e == nslots - 1,
                 'ini_real_ms': None, 'fin_real_ms': None}
            if r['toca_ini'] and pls:
                lim = _buscar_limite_tramo(slots_jd[s], pls[0], 'puerta', -1)
                r['ini_real_ms'] = _jd_a_ms(lim) if lim is not None else None
            if r['toca_fin'] and pls:
                lim = _buscar_limite_tramo(slots_jd[e], pls[0], 'puerta', +1)
                r['fin_real_ms'] = _jd_a_ms(lim) if lim is not None else None
            lst.append(r)
        if lst:
            rangos_puertas[str(g)] = lst
    claves_canal = sorted(f'{a}-{b}' for (a, b) in pares)
    for k in claves_canal:
        a, b = (int(x) for x in k.split('-'))
        runs = _rachas(
            lambda i, k=k: k in slots[i]['canales'],
            lambda i, a=a, b=b: [p for p, gv in detalle_slots[i].items() if gv == a or gv == b])
        lst = []
        for (s, e, pls) in runs:
            pa = next((p for p, gv in detalle_slots[s].items() if gv == a), None)
            pb = next((p for p, gv in detalle_slots[s].items() if gv == b), None)
            r = {'ini_ms': slots[s]['t'], 'fin_ms': slots[e]['t'], 'planetas': pls,
                 'toca_ini': s == 0, 'toca_fin': e == nslots - 1,
                 'ini_real_ms': None, 'fin_real_ms': None}
            if r['toca_ini'] and pa and pb:
                la = _buscar_limite_tramo(slots_jd[s], pa, 'puerta', -1)
                lb = _buscar_limite_tramo(slots_jd[s], pb, 'puerta', -1)
                reales = [x for x in (la, lb) if x is not None]
                r['ini_real_ms'] = _jd_a_ms(max(reales)) if reales else None
            if r['toca_fin'] and pa and pb:
                la = _buscar_limite_tramo(slots_jd[e], pa, 'puerta', +1)
                lb = _buscar_limite_tramo(slots_jd[e], pb, 'puerta', +1)
                reales = [x for x in (la, lb) if x is not None]
                r['fin_real_ms'] = _jd_a_ms(min(reales)) if reales else None
            lst.append(r)
        if lst:
            rangos_canales[k] = lst
    # Próximos para filas vacías: un solo barrido a paso 8h hasta +200d.
    # (Lo más rápido, la Luna, ocupa cada puerta >=9h, así que paso 8h no pierde ingresos.)
    vac_g = [g for g in range(1, 65) if str(g) not in rangos_puertas]
    vac_c = [k for k in claves_canal if k not in rangos_canales]
    prox_puertas, prox_canales = {}, {}
    if vac_g or vac_c:
        # g -> [planeta_ini, entrada_jd, planetas_set, salida_jd|None]; salida=None = sigue abierto
        pend_g = {g: None for g in vac_g}
        pend_c = {k: None for k in vac_c}
        jd_hasta = _jd_de_utc(hasta)
        limite = jd_hasta + 200.0
        def _pendientes():
            return (any(v is None or v[3] is None for v in pend_g.values())
                    or any(v is None or v[3] is None for v in pend_c.values()))

        def _barrer(jd_ini, jd_fin, paso_dias):
            jd = jd_ini
            while jd <= jd_fin and _pendientes():
                det = _puertas_momento(jd, topocentrico=False)
                mp = {d['planeta']: d['puerta'] for d in det}
                st = set(mp.values())
                for g in vac_g:
                    v = pend_g[g]
                    if v is not None and v[3] is not None:
                        continue
                    if g in st:
                        if v is None:
                            p0 = next(p for p, gv in mp.items() if gv == g)
                            pend_g[g] = [p0, jd, {p0}, None]
                        else:
                            v[2].update(p for p, gv in mp.items() if gv == g)
                    elif v is not None:
                        v[3] = jd - paso_dias  # último slot ocupado
                for k in vac_c:
                    v = pend_c[k]
                    if v is not None and v[3] is not None:
                        continue
                    a, b = (int(x) for x in k.split('-'))
                    if a in st and b in st:
                        if v is None:
                            pls = sorted(p for p, gv in mp.items() if gv == a or gv == b)
                            pa0 = next((p for p, gv in mp.items() if gv == a), None)
                            pb0 = next((p for p, gv in mp.items() if gv == b), None)
                            pend_c[k] = [pls[0] if pls else '?', jd, set(pls), None, pa0, pb0]
                        else:
                            v[2].update(p for p, gv in mp.items() if gv == a or gv == b)
                    elif v is not None:
                        v[3] = jd - paso_dias
                jd += paso_dias
        # Fase fina (8h hasta +60d): rápidos (la Luna cubre las 64 puertas en ~27d).
        _barrer(jd_hasta + 8.0 / 24.0, jd_hasta + 60.0, 8.0 / 24.0)
        # Fase gruesa (24h hasta +200d): solo lentos (ocupaciones de semanas/meses).
        _barrer(jd_hasta + 60.0 + 1.0, limite, 1.0)
        # Refinar rachas angostas (<16h, típico Luna muestreada 1-2 veces -> entrada==salida):
        # límites exactos por efemérides en vez de precisión de slot.
        _UMBRAL_ANGOSTO = 16.0 / 24.0
        for g, v in pend_g.items():
            if v is not None and v[3] is not None and (v[3] - v[1]) < _UMBRAL_ANGOSTO:
                try:
                    ini = _buscar_limite_tramo(v[1], v[0], 'puerta', -1)
                    fin = _buscar_limite_tramo(v[1], v[0], 'puerta', +1)
                    if ini is not None:
                        v[1] = ini
                    if fin is not None:
                        v[3] = fin
                except Exception:
                    pass
        for k, v in pend_c.items():
            if v is not None and v[3] is not None and (v[3] - v[1]) < _UMBRAL_ANGOSTO and v[4] and v[5]:
                try:
                    la = _buscar_limite_tramo(v[1], v[4], 'puerta', -1)
                    lb = _buscar_limite_tramo(v[1], v[5], 'puerta', -1)
                    reales = [x for x in (la, lb) if x is not None]
                    if reales:
                        v[1] = max(reales)
                    la2 = _buscar_limite_tramo(v[1], v[4], 'puerta', +1)
                    lb2 = _buscar_limite_tramo(v[1], v[5], 'puerta', +1)
                    reales2 = [x for x in (la2, lb2) if x is not None]
                    if reales2:
                        v[3] = min(reales2)
                except Exception:
                    pass
        for g, v in pend_g.items():
            if v is None:
                prox_puertas[str(g)] = None
            else:
                _p0, entrada_jd, pls, salida_jd = v
                prox_puertas[str(g)] = {
                    'planeta': _p0, 'planetas': sorted(pls),
                    'entrada_ms': _jd_a_ms(entrada_jd),
                    'salida_ms': _jd_a_ms(salida_jd) if salida_jd is not None else None,
                    'abierto': salida_jd is None,
                }
        for k, v in pend_c.items():
            if v is None:
                prox_canales[k] = None
            else:
                _p0, entrada_jd, pls, salida_jd = v[0], v[1], v[2], v[3]
                prox_canales[k] = {
                    'planeta': _p0, 'planetas': sorted(pls),
                    'entrada_ms': _jd_a_ms(entrada_jd),
                    'salida_ms': _jd_a_ms(salida_jd) if salida_jd is not None else None,
                    'abierto': salida_jd is None,
                }
    return jsonify({
        'ref_ms': ref_ms, 'ref_nombre': nombre,
        'desde_ms': int(desde.timestamp() * 1000), 'hasta_ms': int(hasta.timestamp() * 1000),
        'paso_horas': 4,
        'slots': slots,
        'rangos_puertas': rangos_puertas,
        'rangos_canales': rangos_canales,
        'proximos_puertas': prox_puertas,
        'proximos_canales': prox_canales,
    })

CSV_PATH = Path("datos.csv")
SVG_PATH = Path("mapa.svg")
CENTROS_PATH = Path("centros.csv")
CANALES_PATH = Path("canales.csv")
PUERTAS_PATH = Path("puertas.csv")
VINCULOS_PATH = Path("vinculos.csv")
BIOS_LARGAS_PATH = Path("bios_publicas.csv")
CONOCIDOS_PATH = Path("conocidos.csv")
CLAN_PATH = Path("clan.csv")
LINEAS_PATH = Path("lineas_popup.csv")
TIPOS_PATH = Path("tipos.csv")
AUTORIDADES_PATH = Path("autoridades.csv")
PERFILES_PATH = Path("perfiles.csv")
DEFINICIONES_PATH = Path("definiciones.csv")
CRUCES_PATH = Path("cruces.csv")
INFORME_CSV_PATH = Path("informe.csv")
TEST_CSV_PATH = Path("test.csv")
TEST_CSV_COLS = ['nombre', 'fecha', 'hora', 'lugar', 'triada', 'modo', 'foco',
                 'sensorial', 'rutina', 'social', 'cuerpo', 'diges', 'sueno',
                 'busco', 'eneatipo', 'dosha_dom', 'vida', 'destino', 'solar',
                 'luna', 'asc', 'informe',
                 'sernoser_fecha', 'sernoser_alin', 'sernoser_fugas', 'sernoser_resp']

def _leer_test_rows():
    """Lee test.csv tolerando ';' o tab y distintos encodings (utf-8, cp1252, latin-1)."""
    if _FUENTE['path'] is not None:
        df = _leer_xlsx_hoja(_FUENTE['path'], 'test')
        return [list(df.columns)] + df.values.tolist()
    encodings = ['utf-8-sig', 'utf-8', 'cp1252', 'latin-1']
    ultimo = None
    with open(TEST_CSV_PATH, 'rb') as fb:
        raw = fb.read()
    for enc in encodings:
        try:
            s = raw.decode(enc)
            import io as _io
            muestra = s.splitlines()[0] if s.splitlines() else ''
            sep = '\t' if ('\t' in muestra and ';' not in muestra) else ';'
            return [r for r in csv.reader(_io.StringIO(s), delimiter=sep)]
        except Exception as e:
            ultimo = e
    raise ultimo

def _upsert_test(fila):
    """Guarda (o reemplaza por nombre) el resultado del test corto en test.csv.

    Con sesión iniciada lo guarda dentro del perfil de la cuenta (Neon)."""
    perfiles = _perfiles_cuenta_actual()
    if perfiles is not None:
        return _upsert_test_cuenta(perfiles, fila)
    try:
        head = list(TEST_CSV_COLS)
        cuerpo = []
        if TEST_CSV_PATH.exists():
            leidas = _leer_test_rows()
            if leidas:
                head = leidas[0] if leidas[0] else head
                cuerpo = leidas[1:]
        if 'nombre' not in [str(c or '').strip().lower() for c in head]:
            head = list(TEST_CSV_COLS)
            cuerpo = []
        inom = [str(c or '').strip().lower() for c in head].index('nombre')
        nueva = [str(fila.get(c, '') or '') for c in head]
        clave = str(fila.get('nombre', '') or '').strip().lower()
        puesta = False
        for i, r in enumerate(cuerpo):
            if inom < len(r) and str(r[inom] or '').strip().lower() == clave:
                cuerpo[i] = nueva
                puesta = True
                break
        if not puesta:
            cuerpo.append(nueva)
        with open(TEST_CSV_PATH, 'w', newline='', encoding='utf-8-sig') as f:
            w = csv.writer(f, delimiter=';')
            w.writerow(head)
            w.writerows(cuerpo)
        return True
    except Exception:
        return False

def _upsert_test_cuenta(perfiles, fila):
    """Merges the test into the account's perfil in Neon."""
    try:
        ct = _cuenta_actual()
        nombre = str(fila.get('nombre') or '').strip()
        if not ct or not nombre:
            return False
        previo = next((p for p in perfiles
                       if str(p.get('nombre') or '').strip().lower() == nombre.lower()), None)
        base = dict(previo) if previo else {'nombre': nombre, 'fecha': '', 'hora': '',
                                            'lugar': '', 'visibilidad': 'privado'}
        dj = dict(_dj(base)) if previo else {}
        test = dict(dj.get('test') or {})
        for k, v in (fila or {}).items():
            if str(v if v is not None else '').strip():
                test[k] = v
        test['nombre'] = nombre
        dj['test'] = test
        base['nombre'] = nombre
        base['datos_json'] = dj
        _auth.subir_perfil(ct['id'], base)
        g.perfiles_cuenta = None
        return True
    except Exception:
        return False


def _leer_test(nombre):
    """Devuelve el test guardado para el nombre (dict) o None si no existe."""
    try:
        if not TEST_CSV_PATH.exists():
            return None
        leidas = _leer_test_rows()
        if not leidas:
            return None
        head = leidas[0]
        inom = [str(c or '').strip().lower() for c in head].index('nombre') if 'nombre' in [str(c or '').strip().lower() for c in head] else None
        if inom is None:
            return None
        clave = str(nombre or '').strip().lower()
        for r in leidas[1:]:
            if inom < len(r) and str(r[inom] or '').strip().lower() == clave:
                return {head[i]: (r[i] if i < len(r) else '') for i in range(len(head))}
        return None
    except Exception:
        return None

_SNS_CACHE = {'key': None, 'nombres': set()}


def _nombres_con_sns():
    """Nombres con el cuestionario Ser/No-Ser respondido (cache por mtime de la fuente)."""
    p = _FUENTE['path']
    ruta = p if p is not None else TEST_CSV_PATH
    try:
        clave = (str(ruta), ruta.stat().st_mtime_ns)
    except Exception:
        return set()
    if _SNS_CACHE['key'] == clave:
        return _SNS_CACHE['nombres']
    nombres = set()
    try:
        filas = _leer_test_rows()
        if filas:
            head = [str(c or '').strip().lower() for c in filas[0]]
            if 'nombre' in head and 'sernoser_resp' in head:
                i_n = head.index('nombre')
                i_r = head.index('sernoser_resp')
                for r in filas[1:]:
                    if i_n < len(r) and i_r < len(r) and str(r[i_r] or '').strip().strip('|'):
                        nombres.add(str(r[i_n] or '').strip().lower())
    except Exception:
        pass
    _SNS_CACHE['key'] = clave
    _SNS_CACHE['nombres'] = nombres
    return nombres


def _borrar_test(nombre):
    """Elimina la fila del test.csv para el nombre. Devuelve cuántas filas borró."""
    try:
        if not TEST_CSV_PATH.exists():
            return 0
        leidas = _leer_test_rows()
        if not leidas:
            return 0
        head = leidas[0]
        lows = [str(c or '').strip().lower() for c in head]
        if 'nombre' not in lows:
            return 0
        inom = lows.index('nombre')
        clave = str(nombre or '').strip().lower()
        resto = [r for r in leidas[1:] if not (inom < len(r) and str(r[inom] or '').strip().lower() == clave)]
        borradas = len(leidas[1:]) - len(resto)
        if not borradas:
            return 0
        with open(TEST_CSV_PATH, 'w', newline='', encoding='utf-8-sig') as f:
            w = csv.writer(f, delimiter=';')
            w.writerow(head)
            w.writerows(resto)
        return borradas
    except Exception:
        return 0

IA_CSV_PATH = Path("ia.csv")
IA_CSV_COLS = ['nombre', 'texto', 'proveedor', 'generado']

def _leer_ia_rows():
    encodings = ['utf-8-sig', 'utf-8', 'cp1252', 'latin-1']
    with open(IA_CSV_PATH, 'rb') as fb:
        raw = fb.read()
    for enc in encodings:
        try:
            s = raw.decode(enc)
            import io as _io
            muestra = s.splitlines()[0] if s.splitlines() else ''
            sep = '\t' if ('\t' in muestra and ';' not in muestra) else ';'
            return [r for r in csv.reader(_io.StringIO(s), delimiter=sep)]
        except Exception:
            pass
    return []

def _leer_ia(nombre):
    """Devuelve el texto IA guardado en ia.csv para el nombre (dict) o None.

    Con sesión iniciada no lee el ia.csv local (es de otra persona)."""
    if _perfiles_cuenta_actual() is not None:
        return None
    try:
        if not IA_CSV_PATH.exists():
            return None
        leidas = _leer_ia_rows()
        if not leidas:
            return None
        head = leidas[0]
        lows = [str(c or '').strip().lower() for c in head]
        if 'nombre' not in lows:
            return None
        inom = lows.index('nombre')
        clave = str(nombre or '').strip().lower()
        for r in leidas[1:]:
            if inom < len(r) and str(r[inom] or '').strip().lower() == clave:
                return {head[i]: (r[i] if i < len(r) else '') for i in range(len(head))}
        return None
    except Exception:
        return None

def _guardar_ia(nombre, texto, proveedor=''):
    """Con sesión iniciada no escribe en ia.csv (archivo compartido del dueño)."""
    if _perfiles_cuenta_actual() is not None:
        return False
    """Guarda (o reemplaza por nombre) la descripción IA en ia.csv."""
    try:
        from datetime import datetime as _dt
        head = list(IA_CSV_COLS)
        cuerpo = []
        if IA_CSV_PATH.exists():
            leidas = _leer_ia_rows()
            if leidas:
                head = leidas[0] if leidas[0] else head
                cuerpo = leidas[1:]
        if 'nombre' not in [str(c or '').strip().lower() for c in head]:
            head = list(IA_CSV_COLS)
            cuerpo = []
        inom = [str(c or '').strip().lower() for c in head].index('nombre')
        _fecha = _dt.now().strftime('%Y-%m-%d %H:%M')
        nueva = []
        for c in head:
            _cn = str(c or '').strip().lower()
            if _cn == 'nombre':
                nueva.append(str(nombre or ''))
            elif _cn == 'texto':
                nueva.append(str(texto or ''))
            elif _cn == 'proveedor':
                nueva.append(str(proveedor or ''))
            elif _cn == 'generado' or 'fecha' in _cn:
                nueva.append(_fecha)
            else:
                nueva.append('')
        clave = str(nombre or '').strip().lower()
        puesta = False
        for i, r in enumerate(cuerpo):
            if inom < len(r) and str(r[inom] or '').strip().lower() == clave:
                cuerpo[i] = nueva
                puesta = True
                break
        if not puesta:
            cuerpo.append(nueva)
        with open(IA_CSV_PATH, 'w', newline='', encoding='utf-8-sig') as f:
            w = csv.writer(f, delimiter=';')
            w.writerow(head)
            w.writerows(cuerpo)
        return True
    except Exception:
        return False

def _borrar_ia(nombre):
    """Elimina la fila de ia.csv para el nombre. Devuelve cuántas filas borró."""
    try:
        if not IA_CSV_PATH.exists():
            return 0
        leidas = _leer_ia_rows()
        if not leidas:
            return 0
        head = leidas[0]
        lows = [str(c or '').strip().lower() for c in head]
        if 'nombre' not in lows:
            return 0
        inom = lows.index('nombre')
        clave = str(nombre or '').strip().lower()
        resto = [r for r in leidas[1:] if not (inom < len(r) and str(r[inom] or '').strip().lower() == clave)]
        borradas = len(leidas[1:]) - len(resto)
        if not borradas:
            return 0
        with open(IA_CSV_PATH, 'w', newline='', encoding='utf-8-sig') as f:
            w = csv.writer(f, delimiter=';')
            w.writerow(head)
            w.writerows(resto)
        return borradas
    except Exception:
        return 0

def _renombrar_en_csv(path, viejo, nuevo, columnas):
    """Reemplaza el nombre viejo por el nuevo en las columnas indicadas.

    Devuelve cuántas celdas cambió. Tolera ';' o tab y los encodings habituales."""
    try:
        if not path.exists():
            return 0
        raw = path.read_bytes()
        texto = None
        for enc in ('utf-8-sig', 'utf-8', 'cp1252', 'latin-1'):
            try:
                texto = raw.decode(enc)
                break
            except Exception:
                continue
        if texto is None:
            return 0
        lineas = texto.splitlines()
        muestra = lineas[0] if lineas else ''
        sep = '\t' if ('\t' in muestra and ';' not in muestra) else ';'
        filas = list(csv.reader(_io.StringIO(texto), delimiter=sep))
        if not filas:
            return 0
        lows = [str(c or '').strip().lower() for c in filas[0]]
        idxs = sorted({lows.index(str(c or '').strip().lower())
                       for c in columnas if str(c or '').strip().lower() in lows})
        if not idxs:
            return 0
        vl = str(viejo or '').strip().lower()
        cambios = 0
        for r in filas[1:]:
            for i in idxs:
                if i < len(r) and str(r[i] or '').strip().lower() == vl:
                    r[i] = nuevo
                    cambios += 1
        if cambios:
            with open(path, 'w', newline='', encoding='utf-8-sig') as f:
                csv.writer(f, delimiter=sep).writerows(filas)
            _cache_invalidate(path)
        return cambios
    except Exception:
        return 0

# ---------- Caché Etapa 1: evita re-leer CSV/SVG en cada request (invalidación por mtime) ----------
_CACHE_MTIME = {}
_CACHE_VAL = {}

def _cache_get(path: Path, loader, key=None):
    """Cachea por mtime. Si el archivo no cambió, devuelve valor previo."""
    try:
        mtime = path.stat().st_mtime
    except FileNotFoundError:
        return loader()
    key = key or str(path.resolve())
    if key in _CACHE_MTIME and _CACHE_MTIME[key] == mtime:
        val = _CACHE_VAL[key]
        try:
            if isinstance(val, pd.DataFrame):
                return val.copy()
        except Exception:
            pass
        return val
    val = loader()
    _CACHE_MTIME[key] = mtime
    _CACHE_VAL[key] = val
    try:
        if isinstance(val, pd.DataFrame):
            return val.copy()
    except Exception:
        pass
    return val

def _cache_invalidate(path: Path):
    for k in (str(path), str(path.resolve()) if path.exists() else None):
        if k:
            _CACHE_MTIME.pop(k, None)
            _CACHE_VAL.pop(k, None)

def _leer_csv_robusto(path, **kwargs):
    """Lee un CSV probando encodings comunes (utf-8, utf-8-sig, cp1252, latin-1)."""
    encodings = ['utf-8-sig', 'utf-8', 'cp1252', 'latin-1']
    ultimo_error = None
    for enc in encodings:
        try:
            return pd.read_csv(path, encoding=enc, **kwargs)
        except Exception as e:
            ultimo_error = e
    raise ultimo_error


# ---------- Fuente de datos (modo A): leer las tablas mutables desde un xlsx ----------
# Fuente activa: None = CSV de siempre. Path = xlsx elegido (hojas datos/vinculos/test/clan).
# Prioridad al arrancar: 1) cuenta logueada -> Neon, 2) datos.csv propio con contenido -> CSV,
# 3) si no (Render o clon nuevo) -> datos_publicos.xlsx.
def _es_render():
    """True si corre en Render (Render define RENDER=true)."""
    return bool((os.environ.get('RENDER') or '').strip()
                or (os.environ.get('RENDER_SERVICE_ID') or '').strip())


def _datos_csv_utilizables():
    """True si existe datos.csv propio con contenido real."""
    try:
        return CSV_PATH.exists() and CSV_PATH.stat().st_size > 200
    except Exception:
        return False


_DEFAULT_XLSX = Path(__file__).with_name('actores_hollywood.xlsx')
_FUENTE = {'path': (_DEFAULT_XLSX if (_DEFAULT_XLSX.exists()
                                       and (not _datos_csv_utilizables() or _es_render())) else None)}
_TABLAS_MUTABLES = ('datos', 'vinculos', 'test', 'clan')


def fuente_activa():
    return _FUENTE['path']


def _cache_clear():
    _CACHE_MTIME.clear()
    _CACHE_VAL.clear()


def set_fuente(path):
    """Activa (Path) o desactiva (None) la fuente xlsx. Limpia la caché."""
    _FUENTE['path'] = Path(path) if path else None
    _cache_clear()
    return _FUENTE['path']


def _leer_xlsx_hoja(path, hoja):
    """Lee una hoja del xlsx como texto (sin convertir fechas/horas)."""
    return pd.read_excel(path, sheet_name=hoja, dtype=str).fillna('')


def _tabla_mutable(hoja, csv_path, **csv_kw):
    """DataFrame de una tabla mutable: desde el xlsx activo (hoja `hoja`) o del CSV."""
    p = _FUENTE['path']
    if p is not None and hoja in _TABLAS_MUTABLES:
        return _leer_xlsx_hoja(p, hoja)
    return _leer_csv_robusto(csv_path, **csv_kw)


def _cache_arg(csv_path, tabla):
    """(ruta_para_mtime, clave_de_cache) según la fuente activa (xlsx por tabla o CSV)."""
    p = _FUENTE['path']
    if p is not None:
        return p, f"{p.resolve()}::{tabla}"
    return csv_path, None


# ---------- Modo A: escrituras al xlsx activo ----------
# Con un xlsx cargado, las rutas que ESCRIBEN (persona/vinculos/test/clan)
# materializan el xlsx en los CSV, corren el handler como en modo CSV y vuelcan
# el resultado al xlsx. Los CSV quedan intactos (se restauran al terminar).
_TABLA_CSV = {
    'datos': CSV_PATH,
    'vinculos': VINCULOS_PATH,
    'test': TEST_CSV_PATH,
    'clan': CLAN_PATH,
}
_MODOA_RUTAS = ('/api/persona', '/api/autoconocimiento', '/api/clan')
_MODOA_LOCK = _threading.RLock()


def _leer_tabla_csv(csv_path):
    """Lee un CSV tolerando separador/encoding -> (head, filas) o (None, None)."""
    if not csv_path.exists():
        return None, None
    raw = csv_path.read_bytes()
    texto = None
    for enc in ('utf-8-sig', 'utf-8', 'cp1252', 'latin-1'):
        try:
            texto = raw.decode(enc)
            break
        except Exception:
            continue
    if texto is None:
        texto = raw.decode('latin-1', errors='replace')
    lineas = texto.splitlines()
    sep = '\t' if (lineas and '\t' in lineas[0] and ';' not in lineas[0]) else ';'
    filas = [r for r in csv.reader(_io.StringIO(texto), delimiter=sep)
             if any((c or '').strip() for c in r)]
    if not filas:
        return None, None
    return filas[0], filas[1:]


def _materializar_xlsx_a_csv(path, tabla, csv_path):
    """Vuelca una hoja del xlsx sobre su CSV (texto, separador ';')."""
    df = _leer_xlsx_hoja(path, tabla)
    cols = [str(c) for c in df.columns]
    with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f, delimiter=';')
        w.writerow(cols)
        for _, r in df.iterrows():
            w.writerow([('' if pd.isna(r[c]) else str(r[c])) for c in df.columns])


def _sincronizar_csv_a_xlsx(path):
    """Escribe de vuelta los 4 CSV en las hojas del xlsx (crea la hoja si falta)."""
    from openpyxl import load_workbook
    from openpyxl.styles import Font
    wb = load_workbook(path)
    for tabla, csv_path in _TABLA_CSV.items():
        head, filas = _leer_tabla_csv(csv_path)
        if head is None:
            head, filas = [''], []
        n = len(head)
        if tabla in wb.sheetnames:
            idx = wb.sheetnames.index(tabla)
            wb.remove(wb[tabla])
            ws = wb.create_sheet(tabla, idx)
        else:
            ws = wb.create_sheet(tabla)
        ws.append([str(c) for c in head])
        for fila in filas:
            fila = (list(fila) + [''] * n)[:n]
            ws.append([('' if c is None else str(c)) for c in fila])
        for celda in ws[1]:
            celda.font = Font(bold=True)
        ws.freeze_panes = 'A2'
    wb.save(path)


@app.before_request
def _modoA_preparar():
    g._modoA = None
    p = _FUENTE['path']
    if p is None or request.method not in ('POST', 'PUT', 'DELETE'):
        return
    ruta = request.path or ''
    if not any(ruta == r or ruta.startswith(r + '/') for r in _MODOA_RUTAS):
        return
    _MODOA_LOCK.acquire()
    backups = {}
    try:
        try:
            from openpyxl import load_workbook
            wb = load_workbook(p, read_only=True)
            hojas = set(wb.sheetnames)
            wb.close()
        except Exception:
            hojas = set(_TABLAS_MUTABLES)
        for tabla, csv_path in _TABLA_CSV.items():
            backups[tabla] = csv_path.read_bytes() if csv_path.exists() else None
            if tabla in hojas:
                _materializar_xlsx_a_csv(p, tabla, csv_path)
        _FUENTE['path'] = None
        _cache_clear()
        g._modoA = {'path': p, 'backups': backups}
    except Exception as e:
        for tabla, b in backups.items():
            csv_path = _TABLA_CSV[tabla]
            try:
                if b is None:
                    if csv_path.exists():
                        csv_path.unlink()
                else:
                    csv_path.write_bytes(b)
            except Exception:
                pass
        _FUENTE['path'] = p
        _cache_clear()
        _MODOA_LOCK.release()
        g._modoA = None
        return app.response_class(_json.dumps({'error': f'no se pudo preparar el xlsx: {e}'}),
                                  status=400, mimetype='application/json')


@app.after_request
def _modoA_cerrar(resp):
    info = getattr(g, '_modoA', None)
    if not info:
        return resp
    path, backups = info['path'], info['backups']
    err = None
    try:
        _sincronizar_csv_a_xlsx(path)
    except PermissionError:
        err = 'el xlsx esta abierto en Excel; cerralo para poder guardar'
    except Exception as e:
        err = f'no se pudo guardar en el xlsx: {e}'
    finally:
        for tabla, b in backups.items():
            csv_path = _TABLA_CSV[tabla]
            try:
                if b is None:
                    if csv_path.exists():
                        csv_path.unlink()
                else:
                    csv_path.write_bytes(b)
            except Exception:
                pass
        _FUENTE['path'] = path
        _cache_clear()
        _MODOA_LOCK.release()
    if err:
        resp = app.response_class(
            _json.dumps({'error': err}), status=400, mimetype='application/json')
    return resp


def _leer_vinculos_df():
    """Lee vinculos.csv detectando el separador: el archivo real es tab-separated,
    aunque el resto de los CSV de RAVE usan ';'. Devuelve el DataFrame con columnas reales."""
    p = _FUENTE['path']
    if p is not None:
        return _leer_xlsx_hoja(p, 'vinculos')
    for sep in (';', '\t'):
        df = _leer_csv_robusto(VINCULOS_PATH, sep=sep)
        cols = [str(c).strip().lower() for c in df.columns]
        if (len(df.columns) >= 2 and 'nombre' in cols and 'referente' in cols):
            return df
    return _leer_csv_robusto(VINCULOS_PATH, sep='\t')

def cargar_centros():
    """Lee centros.csv (';'-separated, utf-8). Devuelve lista de dicts. Cacheado por mtime."""
    def _load():
        try:
            df = _leer_csv_robusto(CENTROS_PATH, sep=';')
            df.columns = [str(c).strip().lower() for c in df.columns]
            resultados = []
            for _, row in df.iterrows():
                centro = str(row.get('centro', '') or '').strip()
                estado = str(row.get('estado', '') or '').strip()
                descripcion = str(row.get('descripcion', '') or '').strip()
                if not centro and not descripcion:
                    continue
                elemento = f"{centro} — {estado}".strip(' —') if estado else centro
                resultados.append({
                    'elemento': elemento,
                    'centro': centro,
                    'estado': estado,
                    'descripcion': descripcion,
                })
            return resultados
        except FileNotFoundError:
            return []
    return _cache_get(CENTROS_PATH, _load)

_CENTROS_MATRIZ_CACHE = {'mtime': None, 'val': None}

def _centros_matriz_detallada():
    """Lee 'centros_detallado Matriz 9 Centros.xlsx' (hoja 'Matriz 9 Centros').

    Devuelve {(centro, estado): {'tematica': str, 'parrafos': [4 textos]}} con
    centro en clave canónica (Corona/Ajna/Garganta/G/Plexo/Sacro/Ego/Raiz/Bazo)
    y estado 'Definido'/'Indefinido'. Cacheado por mtime del archivo.
    """
    import unicodedata
    crisx = Path(__file__).with_name('centros_detallado Matriz 9 Centros.xlsx')
    try:
        _mtime = crisx.stat().st_mtime
    except Exception:
        return {}
    if _CENTROS_MATRIZ_CACHE['mtime'] == _mtime and _CENTROS_MATRIZ_CACHE['val'] is not None:
        return _CENTROS_MATRIZ_CACHE['val']
    def _norm(s):
        return unicodedata.normalize('NFKD', str(s or '')).encode('ascii', 'ignore').decode('ascii').strip().lower()
    _centros = {
        '1. cabeza': 'Corona', '2. ajna': 'Ajna', '3. garganta': 'Garganta',
        '4. centro g': 'G', '5. sacral': 'Sacro', '6. ego / corazon': 'Ego',
        '7. raiz': 'Raiz', '8. bazo': 'Bazo', '9. plexo solar': 'Plexo',
    }
    _estados = {'definido': 'Definido', 'sin definir': 'Indefinido'}
    out = {}
    try:
        import openpyxl
        wb = openpyxl.load_workbook(crisx, data_only=True, read_only=True)
        ws = wb['Matriz 9 Centros'] if 'Matriz 9 Centros' in wb.sheetnames else wb.worksheets[0]
        rows = ws.iter_rows(values_only=True)
        next(rows, None)
        for row in rows:
            if not row:
                continue
            centro_n = _centros.get(_norm(row[1] if len(row) > 1 else ''))
            estado = _estados.get(_norm(row[2] if len(row) > 2 else ''))
            if not centro_n or not estado:
                continue
            tematica = str(row[3] or '').strip() if len(row) > 3 else ''
            parrafos = [str(row[j] or '').strip() if len(row) > j else '' for j in (4, 5, 6, 7)]
            parrafos = [x for x in parrafos if x]
            out[(centro_n, estado)] = {'tematica': tematica, 'parrafos': parrafos}
        try:
            wb.close()
        except Exception:
            pass
    except Exception:
        pass
    _CENTROS_MATRIZ_CACHE['mtime'] = _mtime
    _CENTROS_MATRIZ_CACHE['val'] = out
    return out

def cargar_canales():
    """Lee canales.csv (';'-separated, utf-8). Devuelve lista de dicts. Cacheado por mtime."""
    def _load():
        try:
            df = _leer_csv_robusto(CANALES_PATH, sep=';')
            df.columns = [str(c).strip().lower() for c in df.columns]
            resultados = []
            for _, row in df.iterrows():
                canal = str(row.get('canal', '') or '').strip()
                descripcion = str(row.get('descripcion', '') or '').strip()
                if not canal and not descripcion:
                    continue
                resultados.append({'elemento': canal, 'descripcion': descripcion})
            return resultados
        except FileNotFoundError:
            return []
    return _cache_get(CANALES_PATH, _load)

def cargar_puertas():
    """Lee puertas.csv (sep=';', encoding cp1252/latin-1). Devuelve lista de dicts. Cacheado por mtime."""
    def _load():
        try:
            df = _leer_csv_robusto(PUERTAS_PATH, sep=';')
            df.columns = [str(c).strip().lower() for c in df.columns]
            col_puerta = next((c for c in df.columns if 'puerta' in c), df.columns[0])
            col_desc = next((c for c in df.columns if 'descripcion' in c or 'descripci' in c), df.columns[-1])
            resultados = []
            for _, row in df.iterrows():
                try:
                    nro = str(row.get(col_puerta, '')).strip()
                    nro = str(int(float(nro))) if nro.replace('.', '', 1).isdigit() else nro
                except (ValueError, TypeError):
                    nro = str(row.get(col_puerta, '') or '').strip()
                descripcion = str(row.get(col_desc, '') or '').strip()
                if not nro and not descripcion:
                    continue
                resultados.append({'elemento': nro, 'descripcion': descripcion})
            def _clave(d):
                try:
                    return (0, int(d['elemento']))
                except (ValueError, TypeError):
                    return (1, d['elemento'])
            return sorted(resultados, key=_clave)
        except FileNotFoundError:
            return []
    return _cache_get(PUERTAS_PATH, _load)

def cargar_lineas():
    """Lee lineas_popup.csv (sep=';', utf-8). Columnas Puerta;linea;arquetipo;rasgo.
    Devuelve dict 'puerta.linea' -> {'arquetipo':..., 'rasgo':...}. Cacheado por mtime."""
    def _load():
        try:
            df = _leer_csv_robusto(LINEAS_PATH, sep=';')
            df.columns = [str(c).strip().lower() for c in df.columns]
            mapa = {}
            for _, row in df.iterrows():
                try:
                    puerta = int(float(str(row.get('puerta', '') or '').strip()))
                    linea = int(float(str(row.get('linea', '') or '').strip()))
                except (ValueError, TypeError):
                    continue
                if not 1 <= puerta <= 64 or not 1 <= linea <= 6:
                    continue
                arquetipo = str(row.get('arquetipo', '') or '').strip()
                rasgo = str(row.get('rasgo', '') or '').strip()
                if not arquetipo and not rasgo:
                    continue
                mapa[f"{puerta}.{linea}"] = {'arquetipo': arquetipo, 'rasgo': rasgo}
            return mapa
        except FileNotFoundError:
            return {}
    return _cache_get(LINEAS_PATH, _load)

def cargar_tipos():
    def _load():
        try:
            df = _leer_csv_robusto(TIPOS_PATH, sep=';')
            df.columns = [str(c).strip().lower() for c in df.columns]
            out = {}
            for _, r in df.iterrows():
                tipo = str(r.get('tipo') or '').strip()
                desc = str(r.get('descripcion') or '').strip()
                if tipo: out[tipo] = desc
            return out
        except FileNotFoundError:
            return {}
    return _cache_get(TIPOS_PATH, _load)

def cargar_autoridades():
    def _load():
        try:
            df = _leer_csv_robusto(AUTORIDADES_PATH, sep=';')
            df.columns = [str(c).strip().lower() for c in df.columns]
            out = {}
            for _, r in df.iterrows():
                k = str(r.get('autoridad') or '').strip()
                if k: out[k] = str(r.get('descripcion') or '').strip()
            return out
        except FileNotFoundError:
            return {}
    return _cache_get(AUTORIDADES_PATH, _load)

def cargar_perfiles():
    def _load():
        try:
            df = _leer_csv_robusto(PERFILES_PATH, sep=';')
            df.columns = [str(c).strip().lower() for c in df.columns]
            out = {}
            for _, r in df.iterrows():
                k = str(r.get('perfil') or '').strip()
                if k: out[k] = {'nombre': str(r.get('nombre') or '').strip(), 'emojis': str(r.get('emojis') or '').strip(), 'descripcion': str(r.get('descripcion') or '').strip()}
            return out
        except FileNotFoundError:
            return {}
    return _cache_get(PERFILES_PATH, _load)

def cargar_definiciones():
    def _load():
        try:
            df = _leer_csv_robusto(DEFINICIONES_PATH, sep=';')
            df.columns = [str(c).strip().lower() for c in df.columns]
            out = {}
            for _, r in df.iterrows():
                k = str(r.get('definicion') or '').strip()
                if k: out[k] = str(r.get('descripcion') or '').strip()
            return out
        except FileNotFoundError:
            return {}
    return _cache_get(DEFINICIONES_PATH, _load)

def cargar_cruces():
    def _load():
        try:
            df = _leer_csv_robusto(CRUCES_PATH, sep=';')
            df.columns = [str(c).strip().lower() for c in df.columns]
            out = {}
            for _, r in df.iterrows():
                k = str(r.get('cruz') or '').strip()
                if k: out[k] = str(r.get('descripcion') or '').strip()
            return out
        except FileNotFoundError:
            return {}
    return _cache_get(CRUCES_PATH, _load)

def cargar_informes():
    """Lee informe.csv (sep=';', utf-8). Columnas nombre;informe. Cacheado por mtime.

    Con sesión iniciada no expone informes del archivo local (son de otra persona)."""
    if _perfiles_cuenta_actual() is not None:
        return {}
    def _load():
        try:
            df = _leer_csv_robusto(INFORME_CSV_PATH, sep=';')
            df.columns = [str(c).strip().lower() for c in df.columns]
            out = {}
            for _, r in df.iterrows():
                n = str(r.get('nombre') or '').strip()
                if n:
                    out[n.lower()] = str(r.get('informe') or '').strip()
            return out
        except FileNotFoundError:
            return {}
    return _cache_get(INFORME_CSV_PATH, _load)

@app.route('/api/lineas_info')
def api_lineas_info():
    """Expone arquetipo y rasgo por puerta.línea (los consume el popup de números de línea)."""
    return jsonify(cargar_lineas())

def _txt(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ''
    s = str(v).strip()
    return '' if s.lower() == 'nan' else s

def _edad(v):
    try:
        return int(float(str(v).strip()))
    except (ValueError, TypeError, AttributeError):
        return None

def cargar_vinculos():
    """Lee vinculos.csv (sep automático ';' o tab). Cacheado por mtime.

    Con sesión iniciada devuelve solo nacimiento de las personas de esa cuenta."""
    _perfiles = _perfiles_cuenta_actual()
    if _perfiles is not None:
        return [{'nombre': str(p.get('nombre') or ''), 'fecha': p.get('fecha') or '',
                 'hora': p.get('hora') or '', 'edad': None, 'lugar': p.get('lugar') or '',
                 'referente': '', 'vinc_ref': '', 'vinc_jorge': '', 'bio': ''}
                for p in _perfiles if str(p.get('nombre') or '').strip()]
    def _load():
        try:
            df = _leer_vinculos_df()
            df = df.fillna('')
            df.columns = [str(c).strip() for c in df.columns]
            col = lambda *nombres: next((c for c in df.columns if c.lower() in nombres), None)
            c_fecha, c_hora, c_edad = col('fecha'), col('hora'), col('edad')
            c_lugar, c_nombre = col('lugar'), col('nombre')
            c_ref = col('referente')
            c_vr = next((c for c in df.columns if 'vinculo' in c.lower() or 'vínculo' in c.lower()), None)
            if c_vr == c_ref:
                c_vr = next((c for c in df.columns if ('referente' in c.lower() or 'vinculo' in c.lower()) and c != c_ref), None)
            c_vj = next((c for c in df.columns if 'jorge' in c.lower()), None)
            c_bio = next((c for c in df.columns if str(c).strip().lower() == 'bio'), None)
            c_larga = next((c for c in df.columns
                            if str(c).strip().lower() in ('bio_larga', 'biografia_larga')), None)
            out = []
            for _, row in df.iterrows():
                nombre = _txt(row.get(c_nombre)) if c_nombre else ''
                if not nombre:
                    continue
                out.append({
                    'nombre': nombre,
                    'fecha': _txt(row.get(c_fecha)) if c_fecha else '',
                    'hora': _txt(row.get(c_hora)) if c_hora else '',
                    'edad': _edad(row.get(c_edad)) if c_edad else None,
                    'lugar': _txt(row.get(c_lugar)) if c_lugar else '',
                    'referente': _txt(row.get(c_ref)) if c_ref else '',
                    'vinc_ref': _txt(row.get(c_vr)) if c_vr else '',
                    'vinc_jorge': _txt(row.get(c_vj)) if c_vj else '',
                    'bio': _txt(row.get(c_bio)) if c_bio else '',
                    'bio_larga': _txt(row.get(c_larga)) if c_larga else '',
                })
            return out
        except FileNotFoundError:
            return []
    _src, _key = _cache_arg(VINCULOS_PATH, 'vinculos')
    return _cache_get(_src, _load, key=_key)


def cargar_bios_largas():
    """Mapa nombre normalizado -> bio larga (bios_publicas.csv, de Wikipedia)."""
    def _load():
        out = {}
        try:
            df = _leer_csv_robusto(BIOS_LARGAS_PATH, sep=';', dtype=str,
                                  keep_default_na=False)
        except Exception:
            return out
        for _, row in df.iterrows():
            n = str(row.get('nombre') or '').strip()
            t = str(row.get('bio_larga') or '').strip()
            if n and t:
                out[_norm_lugar(n)] = t
        return out
    return _cache_get(BIOS_LARGAS_PATH, _load)


@app.route('/api/vinculos')
def api_vinculos():
    return jsonify(cargar_vinculos())

@app.route('/api/tipos_vinculo')
def api_tipos_vinculo():
    """Valores únicos de vínculo (unión de 'vínculo con el referente' y 'vínculo con Jorge')."""
    tipos = set()
    for v in cargar_vinculos():
        for k in ('vinc_ref', 'vinc_jorge'):
            t = (v.get(k) or '').strip()
            if t:
                tipos.add(t)
    return jsonify(sorted(tipos, key=lambda s: s.lower()))


# ---------- Human Design: ficha básica para INFORME (tipos/perfiles/definición) ----------
_HD_CENTRO_CANALES = {
    'Raiz':     ['18-58','38-28','54-32','53-42','60-3','52-9','19-49','39-55','41-30'],
    'Sacro':    ['5-15','14-2','29-46','59-6','9-52','3-60','42-53','27-50','34-57','34-10','34-20'],
    'Bazo':     ['48-16','57-34','57-20','57-10','44-26','50-27','32-54','28-38','18-58'],
    'Plexo':    ['6-59','37-40','49-19','55-39','30-41','36-35','22-12'],
    'Ego':      ['21-45','40-37','26-44','51-25'],
    'G':        ['1-8','2-14','7-31','13-33','10-20','10-34','10-57','25-51','15-5','46-29'],
    'Garganta': ['16-48','20-57','20-34','20-10','31-7','8-1','33-13','35-36','12-22','45-21','62-17','23-43','56-11'],
    'Ajna':     ['11-56','24-61','43-23','47-64','4-63','17-62'],
    'Corona':   ['61-24','63-4','64-47'],
}
_HD_CANAL_CENTROS = {}
for _cc, _lista in _HD_CENTRO_CANALES.items():
    for _c in _lista:
        _p = '-'.join(sorted(_c.split('-'), key=lambda x: int(x)))
        _HD_CANAL_CENTROS.setdefault(_p, []).append(_cc)

# Emojis y circuito por canal (desde Ficha y referencias S y circuito estándar)
_CANAL_EMOJI={
    '1-8':'🌟','2-14':'🚀','3-60':'🌀','4-63':'🔍','5-15':'🔄','6-59':'💞','7-31':'🧭','9-52':'🎯','10-20':'🔑','10-34':'⚡','10-57':'⚡','11-56':'📚','12-22':'🎭','13-33':'⏳','16-48':'⚙️','17-62':'🧠','18-58':'⚖️','19-49':'⚔️','20-34':'⚡','20-57':'💡','21-45':'🏰','23-43':'💡','24-61':'🌀','25-51':'⚡','26-44':'🔄','27-50':'🛡️','28-38':'⚔️','29-46':'🌊','30-41':'🔥','32-54':'📈','34-57':'🌀','35-36':'🌅','37-40':'🤝','39-55':'🌧️','42-53':'🔄','47-64':'🧩','58-38':'⚔️','38-28':'⚔️','54-32':'📈','53-42':'🔄','60-3':'🌀','52-9':'🎯','39-55':'🌧️','41-30':'🔥','60-3':'🌀','2-14':'🚀','15-5':'🔄','46-29':'🌊','33-13':'⏳','31-7':'🧭','8-1':'🌟','20-10':'🔑','45-21':'🏰','62-17':'🧠','56-11':'📚','43-23':'💡','61-24':'🌀','63-4':'🔍','64-47':'🧩',
}
_CANAL_CIRCUITO={
    '1-8':'INDIVIDUAL','2-14':'INDIVIDUAL','3-60':'INDIVIDUAL','4-63':'GRUPAL','5-15':'GRUPAL','6-59':'TRIBAL','7-31':'GRUPAL','9-52':'GRUPAL','10-20':'INDIVIDUAL','10-34':'INDIVIDUAL','10-57':'INDIVIDUAL','11-56':'GRUPAL','12-22':'INDIVIDUAL','13-33':'GRUPAL','16-48':'GRUPAL','17-62':'GRUPAL','18-58':'GRUPAL','19-49':'TRIBAL','20-34':'INDIVIDUAL','20-57':'INDIVIDUAL','21-45':'TRIBAL','23-43':'INDIVIDUAL','24-61':'INDIVIDUAL','25-51':'INDIVIDUAL','26-44':'TRIBAL','27-50':'TRIBAL','28-38':'INDIVIDUAL','29-46':'GRUPAL','30-41':'GRUPAL','32-54':'TRIBAL','34-10':'INDIVIDUAL','34-20':'INDIVIDUAL','34-57':'INDIVIDUAL','35-36':'GRUPAL','36-35':'GRUPAL','37-40':'TRIBAL','39-55':'INDIVIDUAL','40-37':'TRIBAL','41-30':'GRUPAL','42-53':'GRUPAL','44-26':'TRIBAL','47-64':'GRUPAL','48-16':'GRUPAL','50-27':'TRIBAL','51-25':'INDIVIDUAL','52-9':'GRUPAL','53-42':'GRUPAL','54-32':'TRIBAL','55-39':'INDIVIDUAL','57-10':'INDIVIDUAL','57-20':'INDIVIDUAL','57-34':'INDIVIDUAL','58-38':'INDIVIDUAL','60-3':'INDIVIDUAL','61-24':'INDIVIDUAL','62-17':'GRUPAL','63-4':'GRUPAL','64-47':'GRUPAL','38-28':'INDIVIDUAL','15-5':'GRUPAL','46-29':'GRUPAL','33-13':'GRUPAL','31-7':'GRUPAL','8-1':'INDIVIDUAL','20-10':'INDIVIDUAL','45-21':'TRIBAL','62-17':'GRUPAL','56-11':'GRUPAL','43-23':'INDIVIDUAL','61-24':'INDIVIDUAL','63-4':'GRUPAL','64-47':'GRUPAL',
}
def _canal_circuito(k):
    return _CANAL_CIRCUITO.get(_hd_norm_canal(k), 'GRUPAL')

def _hd_norm_canal(s):
    try:
        a,b = [int(x) for x in str(s).split('-')]
        return f"{min(a,b)}-{max(a,b)}"
    except Exception:
        return str(s).strip()

def _hd_canales_de_puertas(puertas):
    s = set(int(p) for p in puertas if p is not None)
    out=set()
    for k, centros in _HD_CANAL_CENTROS.items():
        a,b = [int(x) for x in k.split('-')]
        if a in s and b in s:
            out.add(k)
    return sorted(out)

def _hd_centros_definidos(canales):
    sc=set(_hd_norm_canal(c) for c in canales)
    defs=set()
    for centro, lista in _HD_CENTRO_CANALES.items():
        if any(_hd_norm_canal(c) in sc for c in lista):
            defs.add(centro)
    return defs

def _hd_tipo_autoridad(centros_def, canales):
    sc=set(_hd_norm_canal(c) for c in canales)
    # Garganta conectada a motor
    adj={}
    for k in sc:
        par=_HD_CANAL_CENTROS.get(k,[])
        if len(par)!=2: continue
        x,y=par
        if x not in centros_def or y not in centros_def: continue
        adj.setdefault(x,[]).append(y)
        adj.setdefault(y,[]).append(x)
    motores={'Sacro','Ego','Plexo','Raiz'}
    vis=set(['Garganta']); cola=['Garganta']
    motor_throat=False
    while cola:
        n=cola.pop()
        if n in motores:
            motor_throat=True; break
        for v in adj.get(n,[]):
            if v not in vis:
                vis.add(v); cola.append(v)
    if 'Sacro' in centros_def and motor_throat: tipo='Generador Manifestante'
    elif 'Sacro' in centros_def: tipo='Generador'
    elif motor_throat: tipo='Manifestador'
    elif len(centros_def)==0: tipo='Reflector'
    else: tipo='Proyector'
    if 'Plexo' in centros_def: aut='Emocional'
    elif 'Sacro' in centros_def: aut='Sacral'
    elif 'Bazo' in centros_def: aut='Esplénica'
    elif 'Ego' in centros_def: aut='del Ego'
    elif 'G' in centros_def: aut='Autoproyectada'
    elif 'Ajna' in centros_def: aut='Mental'
    else: aut='Lunar'
    return tipo, aut

def _hd_definicion(centros_def, canales):
    if not centros_def: return 'ninguna'
    sc=set(_hd_norm_canal(c) for c in canales)
    # graph of defined centers linked by defined channels
    adj={c:set() for c in centros_def}
    for k in sc:
        par=_HD_CANAL_CENTROS.get(k,[])
        if len(par)!=2: continue
        x,y=par
        if x in adj and y in adj:
            adj[x].add(y); adj[y].add(x)
    visit=set(); comps=0
    for c in centros_def:
        if c in visit: continue
        comps+=1; cola=[c]; visit.add(c)
        while cola:
            n=cola.pop()
            for v in adj.get(n,[]):
                if v not in visit:
                    visit.add(v); cola.append(v)
    if comps==1: return 'única'
    if comps==2: return 'dividida'
    if comps==3: return 'triple'
    if comps>=4: return 'cuádruple'
    return 'única'

def _foto_publica_para(nombre):
    """URL /publicos/<archivo> de la foto de la persona (hoja fichas del xlsx activo)."""
    p = _FUENTE['path']
    if p is None:
        return ''
    try:
        def _cargar():
            df = _leer_xlsx_hoja(p, 'fichas')
            if 'foto' not in df.columns:
                return {}
            idx = {}
            for _, r in df.iterrows():
                foto = str(r.get('foto') or '').strip()
                if not foto:
                    continue
                url = f'/publicos/{Path(foto).name}'
                for col in ('nombre_base', 'nombre'):
                    if col in df.columns:
                        k = str(r.get(col) or '').strip().lower()
                        if k:
                            idx.setdefault(k, url)
            return idx
        idx = _cache_get(p, _cargar, key=f'{p.resolve()}::fichas_fotos')
        return idx.get(str(nombre).strip().lower(), '')
    except Exception:
        return ''


def _foto_persona_para(nombre):
    """Foto lista para mostrar en el navegador.

    Orden: planilla pública (xlsx), foto de la cuenta en Neon y, al final, la
    foto local elegida en el panel (fotos_personas.csv). Las rutas del equipo se
    devuelven como /api/foto_local?ruta=... para que el SVG pueda cargarlas.
    """
    nombre = str(nombre or '').strip()
    if not nombre:
        return ''
    candidatas = []
    try:
        candidatas.append(_foto_publica_para(nombre))
    except Exception:
        pass
    try:
        for _p in (_perfiles_cuenta_actual() or []):
            if str(_p.get('nombre') or '').strip().lower() == nombre.lower():
                candidatas.append(str(_p.get('foto') or '').strip())
                candidatas.append(str(_dj(_p).get('foto') or '').strip())
                break
    except Exception:
        pass
    try:
        candidatas.append(_cargar_fotos_personas().get(nombre.lower(), ''))
    except Exception:
        pass
    for foto in candidatas:
        foto = str(foto or '').strip()
        if not foto:
            continue
        if _re.match(r'^(?:https?:|data:|/)', foto, _re.I):
            return foto
        return '/api/foto_local?ruta=' + _urlparse.quote(foto, safe='')
    return ''


def _ficha_basica_para_persona(nombre, _df=None, _vinc=None):
    """Ficha BASICO: tipo/autoridad/perfil/definición/centros/canales/puertas para la persona."""
    df=_df if _df is not None else cargar_datos()
    dfp=df[df['Nombre'].astype(str).str.lower()==str(nombre).strip().lower()]
    if dfp.empty:
        return None, f'Persona \"{nombre}\" no encontrada'
    puertas=sorted(set(int(x) for x in dfp['Puerta'].tolist() if x is not None))
    # líneas para perfil
    try:
        lineas=[int(x) for x in dfp['Linea'].tolist() if x is not None and not pd.isna(x)]
    except Exception:
        lineas=[]
    # tipo C/I: separate
    # C/I: Inconsciente vs Consciente (Inconsciente contiene 'consciente', usar igualdad)
    def _is_incon(v): return str(v).strip().lower()=='inconsciente'
    def _is_consc(v): return str(v).strip().lower()=='consciente'
    incon=set(dfp[dfp['C/I'].apply(_is_incon)]['Puerta'].tolist()) if 'C/I' in dfp.columns else set()
    consc=set(dfp[dfp['C/I'].apply(_is_consc)]['Puerta'].tolist()) if 'C/I' in dfp.columns else set()
    # fallback if C/I not parseable: first half incon
    if not incon and not consc:
        incon=set(puertas[:13]); consc=set(puertas[13:])
    canales=_hd_canales_de_puertas(puertas)
    centros=_hd_centros_definidos(canales)
    tipo, autoridad=_hd_tipo_autoridad(centros, canales)
    definicion=_hd_definicion(centros, canales)
    # perfil: from lineas if we have conscious/unconscious lines by C/I
    try:
        incon_l=[int(x) for x in dfp[dfp['C/I'].apply(_is_incon)]['Linea'].tolist() if x is not None and not pd.isna(x)]
        consc_l=[int(x) for x in dfp[dfp['C/I'].apply(_is_consc)]['Linea'].tolist() if x is not None and not pd.isna(x)]
        perfil=_perfil_de_lineas(consc_l[0] if consc_l else None, incon_l[0] if incon_l else None) if (consc_l or incon_l) else None
    except Exception:
        perfil=None
    # if perfil None, try overall
    if not perfil and lineas:
        perfil=_perfil_de_lineas(lineas[0] if len(lineas)>1 else None, lineas[1] if len(lineas)>1 else None)
    # cargar descripciones editables
    tipos=cargar_tipos(); auts=cargar_autoridades(); perfs=cargar_perfiles(); definis=cargar_definiciones()
    informes=cargar_informes()
    # centros definidos/indefinidos con descripcion
    centros_data=cargar_centros()
    _centros_idx={f"{str(c.get('centro','')).lower()}|{str(c.get('estado','')).lower()}": c.get('descripcion','') for c in centros_data}
    def _desc_centro(nombre, estado):
        return _centros_idx.get(f"{nombre.lower()}|{estado.lower()}", '')
    centros_det=[{'centro':c, 'estado':'Definido', 'descripcion':_desc_centro(c,'Definido')} for c in sorted(centros)]
    centros_det+=[{'centro':c, 'estado':'Indefinido', 'descripcion':_desc_centro(c,'Indefinido')} for c in ['Corona','Ajna','Garganta','G','Ego','Bazo','Plexo','Sacro','Raiz'] if c not in centros]
    # canales con descripcion — claves normalizadas (min-max) para que 63-4 y 4-63 coincidan
    canales_data=cargar_canales()
    cmap={_hd_norm_canal(str(c.get('elemento','')).strip()): c.get('descripcion','') for c in canales_data if str(c.get('elemento','')).strip()}
    canales_det=[{'canal':_hd_norm_canal(k), 'descripcion': cmap.get(_hd_norm_canal(k),'')} for k in canales]
    # puertas con descripcion + linea y centro (para agrupar por centro y mostrar línea)
    puertas_data=cargar_puertas()
    pmap={str(p['elemento']).strip():p['descripcion'] for p in puertas_data}
    # mapa puerta -> centro (estándar HD)
    _PUERTA_CENTRO={}
    for centro, lista in _HD_CENTRO_CANALES.items():
        # canales no dan puerta->centro directo; usar lista conocida de 64 puertas
        pass
    # hardcode 64 puertas -> centro
    _PUERTA_A_CENTRO={64:'Corona',61:'Corona',63:'Corona',47:'Ajna',24:'Ajna',4:'Ajna',17:'Ajna',43:'Ajna',11:'Ajna',62:'Garganta',23:'Garganta',56:'Garganta',35:'Garganta',12:'Garganta',45:'Garganta',33:'Garganta',8:'Garganta',20:'Garganta',31:'Garganta',16:'Garganta',7:'G',1:'G',13:'G',10:'G',25:'G',15:'G',46:'G',2:'G',21:'Ego',40:'Ego',26:'Ego',51:'Ego',48:'Bazo',57:'Bazo',44:'Bazo',50:'Bazo',32:'Bazo',28:'Bazo',18:'Bazo',36:'Plexo',22:'Plexo',37:'Plexo',49:'Plexo',30:'Plexo',55:'Plexo',6:'Plexo',5:'Sacro',14:'Sacro',29:'Sacro',59:'Sacro',9:'Sacro',3:'Sacro',42:'Sacro',27:'Sacro',34:'Sacro',53:'Raiz',60:'Raiz',52:'Raiz',19:'Raiz',39:'Raiz',41:'Raiz',58:'Raiz',38:'Raiz',54:'Raiz'}
    # activaciones con línea (puerta.línea) por C/I
    def _activaciones(sub_df):
        out=[]
        for _, row in sub_df.iterrows():
            try:
                pu=int(row['Puerta'])
                li=row.get('Linea')
                li=int(float(li)) if li is not None and not pd.isna(li) else None
            except Exception:
                continue
            out.append({'puerta':pu, 'linea':li, 'centro':_PUERTA_A_CENTRO.get(pu,'?')})
        return out
    incon_act=_activaciones(dfp[dfp['C/I'].apply(_is_incon)]) if 'C/I' in dfp.columns else []
    consc_act=_activaciones(dfp[dfp['C/I'].apply(_is_consc)]) if 'C/I' in dfp.columns else []
    # mixtas = puertas en ambos
    set_incon=set(a['puerta'] for a in incon_act)
    set_consc=set(a['puerta'] for a in consc_act)
    mixtas=set_incon & set_consc
    # puertas_det ahora incluye línea y estado y centro
    puertas_det=[]
    # agrupar por puerta única pero mostrar líneas (si hay duplicadas, promediar)
    from collections import defaultdict as _dd
    lineas_por_puerta=_dd(list)
    estado_por_puerta={}
    for a in incon_act:
        lineas_por_puerta[a['puerta']].append(a['linea'])
        estado_por_puerta[a['puerta']]= 'mixto' if a['puerta'] in mixtas else 'inconsciente'
    for a in consc_act:
        lineas_por_puerta[a['puerta']].append(a['linea'])
        if a['puerta'] not in estado_por_puerta:
            estado_por_puerta[a['puerta']]='consciente'
        elif estado_por_puerta[a['puerta']]!='mixto' and a['puerta'] in mixtas:
            estado_por_puerta[a['puerta']]='mixto'
    # línea arquetipo/rasgo (más específico que solo puerta)
    lineas_map=cargar_lineas()
    for pu in puertas:
        lst=[x for x in lineas_por_puerta.get(pu,[]) if x]
        lin=lst[0] if lst else None
        st=estado_por_puerta.get(pu, 'desconocido')
        desc_pu=pmap.get(str(pu),'')
        # emoji si existe al inicio de la descripción, lo separamos
        linea_key=f"{pu}.{lin}" if lin else None
        lin_info=lineas_map.get(linea_key, {}) if linea_key else {}
        puertas_det.append({'puerta':str(pu), 'linea':lin, 'lineas':lst, 'estado':st, 'centro':_PUERTA_A_CENTRO.get(pu,'?'), 'descripcion':desc_pu,
                            'linea_arquetipo': lin_info.get('arquetipo',''), 'linea_rasgo': lin_info.get('rasgo','')})
    # agrupar por centro para informe
    puertas_por_centro=_dd(list)
    for _pu in puertas_det:
        puertas_por_centro[_pu['centro']].append(_pu)
    # ordenar centros en orden clásico y puertas numérico
    orden_centros=['Corona','Ajna','Garganta','G','Ego','Bazo','Plexo','Sacro','Raiz']
    puertas_por_centro_ord=[(c, sorted(puertas_por_centro[c], key=lambda x: int(x['puerta']))) for c in orden_centros if c in puertas_por_centro]
    # Cruz de Encarnación — usando orden Sol,Tierra,Luna... (índices 0,1) por lado
    cruz_nombre = None
    cruz_desc = None
    try:
        cruces_map = cargar_cruces()
        # datos vienen ordenados Sol(0),Tierra(1)... por lado -> Sol/Tierra son los 2 primeros
        # reconstruir orden original por persona (preservando C/I y orden de archivo)
        df_ord = dfp  # ya filtrado por nombre, mantiene orden de archivo
        incon_ord = df_ord[df_ord['C/I'].apply(lambda v: str(v).strip().lower()=='inconsciente')]
        consc_ord = df_ord[df_ord['C/I'].apply(lambda v: str(v).strip().lower()=='consciente')]
        sol_p = int(consc_ord.iloc[0]['Puerta']) if len(consc_ord)>=1 else None
        tierra_p = int(consc_ord.iloc[1]['Puerta']) if len(consc_ord)>=2 else None
        sol_d = int(incon_ord.iloc[0]['Puerta']) if len(incon_ord)>=1 else None
        tierra_d = int(incon_ord.iloc[1]['Puerta']) if len(incon_ord)>=2 else None
        # determinar ángulo por perfil
        def _angulo(perfil):
            if not perfil: return 'derecho'
            if perfil=='4/1': return 'yuxtapuesta'
            if perfil in ('5/1','5/2','6/2','6/3'): return 'izquierdo'
            return 'derecho'
        ang = _angulo(perfil)
        ang_token = {'derecho':'Angulo Derecho','yuxtapuesta':'Yuxtapuesta','izquierdo':'Angulo Izquierdo'}[ang]
        # buscar cruz que contenga el token de ángulo y mencione puerta del Sol P
        import re
        cands=[]
        for k, desc in cruces_map.items():
            if ang_token.lower() not in k.lower():
                continue
            if sol_p and re.search(rf'\b0*{sol_p}\b', desc):
                cands.append(k)
        if not cands and sol_p:
            # fallback sin filtrar ángulo (por si el ángulo no coincide exacto en BD)
            for k, desc in cruces_map.items():
                if re.search(rf'\b0*{sol_p}\b', desc):
                    cands.append(k)
        if cands:
            def _score(k):
                d=cruces_map[k]
                s=0
                if sol_d and re.search(rf'\b0*{sol_d}\b', d): s+=2
                if tierra_p and re.search(rf'\b0*{tierra_p}\b', d): s+=1
                # preferir el que tenga ang_token
                if ang_token.lower() in k.lower(): s+=5
                return s
            cands.sort(key=_score, reverse=True)
            cruz_nombre=cands[0]
            cruz_desc=cruces_map.get(cruz_nombre)
    except Exception:
        cruz_nombre=None
        cruz_desc=None
    # nacimiento (fecha/hora/lugar) desde vinculos.csv, si existe
    _nac=None
    _bio=''
    _bio_larga=''
    try:
        _n_orig=str(nombre).strip().lower()
        for _v in (_vinc if _vinc is not None else cargar_vinculos()):
            if str(_v.get('nombre') or '').strip().lower()==_n_orig:
                if _nac is None:
                    _nac=_v
                if not _bio and str(_v.get('bio') or '').strip():
                    _bio=str(_v.get('bio')).strip()
                if not _bio_larga and str(_v.get('bio_larga') or '').strip():
                    _bio_larga=str(_v.get('bio_larga')).strip()
                if _nac is not None and _bio and _bio_larga:
                    break
    except Exception:
        _nac=None
    if not _bio_larga:
        try:
            _bio_larga=cargar_bios_largas().get(_norm_lugar(nombre), '')
        except Exception:
            _bio_larga=''
    # carta: Sol/Luna/Ascendente (solo si hay fecha) — se reusa la misma
    # función que el test de autoconocimiento (swisseph + lugar a coordenadas).
    _sol=_luna=_asc=None
    if _nac and str(_nac.get('fecha') or '').strip():
        try:
            _carta=_carta_natal({'fecha': str(_nac['fecha']).strip(),
                                 'hora': str(_nac.get('hora') or '').strip(),
                                 'lugar': str(_nac.get('lugar') or '').strip()})
            if isinstance(_carta, dict) and not _carta.get('error'):
                _sol=_carta.get('sol'); _luna=_carta.get('luna'); _asc=_carta.get('asc')
        except Exception:
            _sol=_luna=_asc=None
    ficha={
        'nombre': str(nombre),
        'foto': _foto_persona_para(nombre),
        'bio': _bio,
        'bio_larga': _bio_larga,
        'informe': informes.get(str(nombre).strip().lower(), ''),
        'fecha': (_nac or {}).get('fecha','') or '',
        'hora': (_nac or {}).get('hora','') or '',
        'lugar': (_nac or {}).get('lugar','') or '',
        'sol': _sol,
        'luna': _luna,
        'asc': _asc,
        'tipo': tipo,
        'tipo_descripcion': tipos.get(tipo,''),
        'autoridad': autoridad,
        'autoridad_descripcion': auts.get(autoridad,'') or auts.get(autoridad.lower(),''),
        'perfil': perfil,
        'perfil_detalle': perfs.get(perfil,{}) if perfil else {},
        'definicion': definicion,
        'definicion_descripcion': definis.get(definicion,'') or definis.get(definicion.lower(),''),
        'cruz': cruz_nombre,
        'cruz_descripcion': cruz_desc or (cargar_cruces().get(cruz_nombre) if cruz_nombre else None),
        'centros_definidos': sorted(centros),
        'centros_indefinidos': sorted([c for c in ['Corona','Ajna','Garganta','G','Ego','Bazo','Plexo','Sacro','Raiz'] if c not in centros]),
        'centros_detalle': centros_det,
        'canales': canales,
        'canales_detalle': canales_det,
        'puertas': puertas,
        'puertas_detalle': puertas_det,
        'puertas_por_centro': puertas_por_centro_ord,
        'puertas_inconscientes': sorted(incon) if incon else [],
        'puertas_conscientes': sorted(consc) if consc else [],
    }
    return ficha, None

@app.route('/api/ficha_basica')
def api_ficha_basica():
    nombre=(request.args.get('persona') or '').strip()
    if not nombre:
        return jsonify({'error':'Falta ?persona='}),400
    ficha, err=_ficha_basica_para_persona(nombre)
    if err:
        return jsonify({'error':err}),404
    return jsonify(ficha)


@app.route('/api/briefing')
def api_briefing():
    """Briefing diario sin IA: AYER / HOY / MAÑANA (si cambia)."""
    try:
        from briefing import generar_briefing
        persona = (request.args.get('persona') or '').strip() or get_persona_default()
        fecha = (request.args.get('fecha') or '').strip() or None
        hora = (request.args.get('hora') or '').strip() or None
        detalle = request.args.get('detalle') in ('1', 'true', 'si', 'sí')
        res = generar_briefing(persona, fecha, hora, incluir_detalle=detalle)
    except ValueError as e:
        return jsonify({'ok': False, 'error': f'Fecha/hora inválida: {e}'}), 400
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500
    if not res.get('ok'):
        return jsonify(res), 404
    if request.args.get('formato') == 'texto':
        return Response(res['texto'], mimetype='text/plain; charset=utf-8')
    return jsonify(res)


@app.route('/publicos/<path:fn>')
def servir_foto_publica(fn):
    return send_from_directory(str(Path(__file__).resolve().parent / 'Publicos'), fn)

# Emojis en PDF: Helvetica no tiene dibujo y salían cuadraditos.
# Se lee Segoe UI Symbol (Windows) una vez para dibujarlos en el PDF.
_FUENTE_SIMB = None
_GLIFOS_SIMB = frozenset()
try:
    from reportlab.pdfbase import pdfmetrics as _pm_sim
    from reportlab.pdfbase.ttfonts import TTFont as _TTF_sim, TTFontFile as _TTFF_sim
    try:
        _pm_sim.registerFont(_TTF_sim('SegoeSym', r'C:\Windows\Fonts\seguisym.ttf'))
        _GLIFOS_SIMB = frozenset(_TTFF_sim(r'C:\Windows\Fonts\seguisym.ttf', validate=0).charToGlyph.keys())
        _FUENTE_SIMB = 'SegoeSym'
    except Exception:
        _FUENTE_SIMB = None
except Exception:
    _FUENTE_SIMB = None
_FE0F = chr(0xFE0F)
_PUNTO_MEDIO = chr(0x2022)

def _es_letra_pdf(c):
    try:
        c.encode('cp1252')
        return True
    except Exception:
        return False

def _emoji_pdf(s):
    """Texto para el PDF: lo normal queda igual; cada emoji se dibuja con
    SegoeSym (o se saca sin dejar cuadradito si esa letra no está)."""
    out, buf = [], []
    def _flush():
        if not buf:
            return
        if _FUENTE_SIMB:
            t = ''.join('' if c == _FE0F else (c if ord(c) in _GLIFOS_SIMB else _PUNTO_MEDIO) for c in buf)
            out.append('<font name="%s">%s</font>' % (_FUENTE_SIMB, t))
        del buf[:]
    for c in str(s or ''):
        if _es_letra_pdf(c):
            _flush()
            out.append(c)
        else:
            buf.append(c)
    _flush()
    return ''.join(out)

def _sanear_error_ia(msg):
    """Quita posibles claves del texto de error antes de exponerlo (sin ocultar el motivo)."""
    try:
        s = str(msg or '')
        for _k in ('GEMINI_API_KEY', 'GROQ_API_KEY', 'CEREBRAS_API_KEY', 'OPENROUTER_API_KEY'):
            _v = (os.environ.get(_k) or '').strip()
            if _v and len(_v) > 4 and _v in s:
                s = s.replace(_v, '***')
        return s
    except Exception:
        return str(msg or '')


# Clasificación de puertas por categoría (lámina del usuario: círculo engrosado
# negro=Rol, rojo=Amor personal, verde=Amor impersonal; la 10 es de las tres).
# Miedo = puertas ubicadas en Bazo, Ajna y Plexo.
_PUERTAS_ROL = {1, 7, 10, 13, 27, 59}
_PUERTAS_AMOR_PERSONAL = {10, 28, 40, 41, 44, 55, 58}
_PUERTAS_AMOR_IMPERSONAL = {10, 15, 25, 46}
_PUERTAS_MIEDO = {4, 6, 11, 17, 18, 22, 24, 28, 30, 32, 36, 37, 43, 44, 47, 48, 49, 50, 55, 57}

_SYS_IA = ("Sos un analista de Diseño Humano. Escribí en español claro, prosa breve (120-180 palabras), "
           "personalizada con la ficha, sin inventar datos fuera de la ficha. No repitas las descripciones "
           "de Tipo, Perfil, canales ni centros, que van por separado en el informe: describí cómo vive "
           "esta persona su diseño, sus temas de rol, amor y miedo.")
_PREGUNTA_IA = ("Genera el retrato personal introductorio del informe en prosa clara para esta persona, "
                "sin repetir las descripciones de Tipo ni Perfil.")

_IA_EN_PROCESO = set()
_IA_LOCK = _threading.Lock()


def _contexto_ia_descripcion(ficha):
    """Contexto para la IA: base_informe_ia.txt + ficha resumida con las puertas
    separadas por categoría (rol / amor personal / amor impersonal / miedo)."""
    try:
        _base = Path(__file__).with_name('base_informe_ia.txt').read_text(encoding='utf-8', errors='replace')[:8000]
    except Exception:
        _base = ''
    _p = set(int(x) for x in (ficha.get('puertas') or []) if x)
    def _cat(conj):
        s = sorted(conj & _p)
        return ', '.join(str(x) for x in s) if s else '(ninguna)'
    _res = (f"Tipo: {ficha.get('tipo')}\n"
        f"Perfil: {ficha.get('perfil')}\n"
        f"Canales: {', '.join(ficha.get('canales') or [])}\n"
        f"Centros definidos: {', '.join(ficha.get('centros_definidos') or [])}; "
        f"Indefinidos: {', '.join(ficha.get('centros_indefinidos') or [])}\n"
        f"Puertas de rol: {_cat(_PUERTAS_ROL)}\n"
        f"Puertas de amor personal: {_cat(_PUERTAS_AMOR_PERSONAL)}\n"
        f"Puertas de amor impersonal: {_cat(_PUERTAS_AMOR_IMPERSONAL)}\n"
        f"Puertas de miedo: {_cat(_PUERTAS_MIEDO)}")
    return _base, (_base + '\n\n--- FICHA ---\n' + _res)[:12000]


def _generar_ia_por_persona(nombre):
    """Thread: pide la descripción IA en segundo plano y la guarda en ia.csv.
    Si todos los proveedores fallan (hasta IA_INTENTOS intentos), no guarda nada
    y la próxima carga reintenta."""
    nombre = (nombre or '').strip()
    if not nombre:
        return
    with _IA_LOCK:
        if nombre.lower() in _IA_EN_PROCESO:
            return
        _IA_EN_PROCESO.add(nombre.lower())
    try:
        ficha, err = _ficha_basica_para_persona(nombre)
        if err:
            return
        _base_txt, _ctx_txt = _contexto_ia_descripcion(ficha)
        _cands = [c for c in _candidatos_ia() if c.get('configurado')]
        if not _cands:
            return
        _old_to = os.environ.get('IA_RACE_TIMEOUT')
        os.environ['IA_RACE_TIMEOUT'] = '30'
        _intentos = int(os.environ.get('IA_INTENTOS') or 4)
        try:
            for _intento in range(max(1, _intentos)):
                try:
                    _cfgp, _mod, _resp, _av = _carrera_proveedores(_cands, _SYS_IA, _ctx_txt,
                                                                   _PREGUNTA_IA, None, max_tokens=600)
                    _txt = str(_resp or '').strip()[:4000]
                    if _txt:
                        _guardar_ia(nombre, _txt, f"{_cfgp.get('proveedor')}/{_mod}")
                    break
                except RuntimeError:
                    pass
        finally:
            try:
                if _old_to is None:
                    del os.environ['IA_RACE_TIMEOUT']
                else:
                    os.environ['IA_RACE_TIMEOUT'] = _old_to
            except Exception:
                pass
    finally:
        with _IA_LOCK:
            _IA_EN_PROCESO.discard(nombre.lower())


@app.route('/api/ia_descripcion')
def api_ia_descripcion():
    """Devuelve la descripción IA guardada en ia.csv para la persona; si no
    existe, la encola en segundo plano (no bloquea) y avisa 'generando'."""
    nombre = (request.args.get('persona') or '').strip()
    if not nombre:
        return jsonify({'error': 'Falta ?persona='}), 400
    ficha, err = _ficha_basica_para_persona(nombre)
    if err:
        return jsonify({'error': err}), 404
    guardado = _leer_ia(ficha['nombre'])
    if guardado and (guardado.get('texto') or '').strip():
        return jsonify({'estado': 'listo', 'texto': guardado.get('texto'),
                        'proveedor': guardado.get('proveedor', ''), 'generado': guardado.get('generado', ''),
                        'persona': ficha['nombre']})
    with _IA_LOCK:
        _generando = ficha['nombre'].lower() in _IA_EN_PROCESO
    if not _generando:
        _threading.Thread(target=_generar_ia_por_persona, args=(ficha['nombre'],), daemon=True).start()
    return jsonify({'estado': 'generando', 'persona': ficha['nombre']})


@app.route('/api/ia_probar', methods=['POST'])
def api_ia_probar():
    """Prueba directa de IA con el mismo contexto del PDF (base_informe_ia.txt + ficha).

    Body: {"persona": "Jorge"} o {"texto": "..."} / {"pregunta": "..."}.
    Devuelve respuesta + proveedor/modelo/aviso, o error real visible (sin claves).
    """
    data = request.get_json(force=True, silent=True) or {}
    persona = (data.get('persona') or data.get('nombre') or '').strip()
    pregunta = (data.get('texto') or data.get('pregunta') or '').strip()
    if not pregunta:
        pregunta = 'Genera la introducción personalizada del informe en prosa clara para esta persona'
    ficha = None
    if persona:
        ficha, err = _ficha_basica_para_persona(persona)
        if err:
            return jsonify({'error': err}), 404
        _base_txt, _ctx_txt = _contexto_ia_descripcion(ficha)
    else:
        try:
            _base_txt = Path(__file__).with_name('base_informe_ia.txt').read_text(encoding='utf-8', errors='replace')[:8000]
        except Exception:
            _base_txt = ''
        _ctx_txt = (_base_txt + '\n\n--- FICHA ---\n(sin ficha: texto libre)')[:12000]
    _cands = [c for c in _candidatos_ia() if c.get('configurado')]
    if not _cands:
        return jsonify({'error': 'IA no configurada: sin proveedores con clave (groq/gemini/cerebras/openrouter) y ollama no disponible. Definí la API key en el servidor.',
                        'proveedores_probados': []}), 502
    _old_to = os.environ.get('IA_RACE_TIMEOUT')
    os.environ['IA_RACE_TIMEOUT'] = '30'
    try:
        try:
            _cfgp, _mod, _resp, _av = _carrera_proveedores(
                _cands,
                'Sos un analista de Diseño Humano. Escribí en español claro, prosa breve (120-180 palabras), personalizada con la ficha, sin inventar datos fuera de la ficha.',
                _ctx_txt, pregunta, None, max_tokens=600)
        except RuntimeError as e:
            return jsonify({'error': _sanear_error_ia(str(e))[:800],
                            'proveedores_probados': [c.get('proveedor') for c in _cands],
                            'timeout_s': 30}), 502
    finally:
        try:
            if _old_to is None:
                del os.environ['IA_RACE_TIMEOUT']
            else:
                os.environ['IA_RACE_TIMEOUT'] = _old_to
        except Exception:
            pass
    out = {'respuesta': str(_resp or '').strip()[:4000],
           'proveedor': _cfgp.get('proveedor'), 'model': _mod, 'timeout_s': 30}
    if persona:
        out['persona'] = persona
    if _av:
        out['aviso'] = _av
    return jsonify(out)


@app.route('/api/informe_pdf', methods=['POST'])
def api_informe_pdf():
    data=request.get_json(force=True, silent=True) or {}
    persona=(data.get('persona') or data.get('nombre') or '').strip()
    if not persona:
        return jsonify({'error':'Falta persona'}),400
    ficha, err=_ficha_basica_para_persona(persona)
    if err:
        return jsonify({'error':err}),404
    # imagen del gráfico: preferencia png base64, fallback svg
    png_b64=data.get('png') or data.get('imagen') or ''
    svg_txt=data.get('svg') or ''
    img_data=None
    if png_b64:
        try:
            if ',' in png_b64:
                png_b64=png_b64.split(',',1)[1]
            import base64
            img_data=base64.b64decode(png_b64)
        except Exception:
            img_data=None
    # generar PDF
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.colors import HexColor
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle, PageBreak, HRFlowable, KeepTogether
        from reportlab.lib.enums import TA_LEFT, TA_CENTER
        import io
    except ImportError as e:
        return jsonify({'error': f'Falta dependencia PDF: {e}. Instalar reportlab'}),501
    buf=io.BytesIO()
    doc=SimpleDocTemplate(buf, pagesize=A4, leftMargin=14*mm, rightMargin=14*mm, topMargin=12*mm, bottomMargin=12*mm,
                          title=f"Informe {persona}", author="RAVE")
    styles=getSampleStyleSheet()
    s_title=ParagraphStyle('Title2', parent=styles['Title'], fontSize=18, leading=22, textColor=HexColor('#1a237e'), alignment=TA_CENTER)
    s_h1=ParagraphStyle('H1', parent=styles['Heading1'], fontSize=13, leading=16, textColor=HexColor('#1a237e'), spaceAfter=6)
    s_h2=ParagraphStyle('H2', parent=styles['Heading2'], fontSize=11, leading=14, textColor=HexColor('#37474f'), spaceAfter=4)
    s_body=ParagraphStyle('Body', parent=styles['BodyText'], fontSize=9, leading=12, alignment=TA_LEFT, spaceAfter=4)
    s_small=ParagraphStyle('Small', parent=s_body, fontSize=8, leading=10, textColor=HexColor('#616161'))
    story=[]
    def p(txt, style=s_body):
        return Paragraph(_emoji_pdf(txt), style)
    def _clean(s):
        return str(s or '').replace('|','<br/>').replace('\n','<br/>')
    # Intro IA precargada (primer bloque): se usa el texto ya guardado en
    # ia.csv por la generación en segundo plano. Sin texto guardado, se omite.
    _ia_intro_txt=None; _ia_intro_prov=None
    _ia_guardado=_leer_ia(persona)
    if _ia_guardado and (_ia_guardado.get('texto') or '').strip():
        _ia_intro_txt=_ia_guardado.get('texto')
        _ia_intro_prov=_ia_guardado.get('proveedor','')
    # Portada
    story.append(p(f"Informe de Diseño Humano — {persona}", s_title))
    story.append(Spacer(1,4*mm))
    story.append(p(f"Tipo <b>{ficha['tipo']}</b> &nbsp;·&nbsp; Autoridad <b>{ficha['autoridad']}</b> &nbsp;·&nbsp; Perfil <b>{ficha['perfil'] or '-'}</b> &nbsp;·&nbsp; Definición <b>{ficha['definicion']}</b>", ParagraphStyle('sub', parent=s_body, alignment=TA_CENTER, fontSize=10, textColor=HexColor('#37474f'))))
    # Nacimiento (discreto, gris 50%) — solo si hay algún dato
    _nac_parts=[]
    if str(ficha.get('fecha') or '').strip(): _nac_parts.append(str(ficha['fecha']))
    if str(ficha.get('hora') or '').strip(): _nac_parts.append(str(ficha['hora']))
    if str(ficha.get('lugar') or '').strip(): _nac_parts.append(str(ficha['lugar']))
    if _nac_parts:
        from reportlab.pdfbase.pdfmetrics import stringWidth as _sw
        _nac_txt="Nacimiento: " + ' · '.join(_nac_parts)
        _sNac=ParagraphStyle('nacimiento', parent=s_body, alignment=TA_LEFT, fontSize=8, leading=10, textColor=HexColor('#808080'))
        _celdas_nac=[p(_nac_txt, _sNac)]
        _cart_cols={'sol':'#FF7F00','luna':'#87CEEB','asc':'#ffffff'}
        _cart_txt={'sol':'#ffffff','luna':'#111111','asc':'#111111'}
        _n_sq=0
        for _ck in ('sol','luna','asc'):
            _sig=str(ficha.get(_ck) or '').strip()
            if not _sig:
                continue
            _glifo=_SIGNO_SIMBOLO.get(_sig,'')
            _sSim=ParagraphStyle('cSim', parent=s_small, alignment=TA_CENTER, fontSize=7, leading=7, textColor=HexColor(_cart_txt[_ck]))
            _marc=Table([[p(_emoji_pdf(_glifo), _sSim)]], colWidths=[5*mm], rowHeights=[5*mm])
            _styl=[('BACKGROUND',(0,0),(-1,-1),HexColor(_cart_cols[_ck])),
                   ('ALIGN',(0,0),(-1,-1),'CENTER'),('VALIGN',(0,0),(-1,-1),'MIDDLE'),
                   ('LEFTPADDING',(0,0),(-1,-1),0),('RIGHTPADDING',(0,0),(-1,-1),0),
                   ('TOPPADDING',(0,0),(-1,-1),0),('BOTTOMPADDING',(0,0),(-1,-1),0)]
            if _ck=='asc':
                _styl.append(('BOX',(0,0),(-1,-1),0.6,HexColor('#bdbdbd')))
            _marc.setStyle(TableStyle(_styl))
            _celdas_nac.append(_marc)
            _n_sq+=1
        _w_txt=_sw(_nac_txt,'Helvetica',8)
        _tNac=Table([_celdas_nac], colWidths=[_w_txt+8*mm]+[6*mm]*_n_sq, hAlign='CENTER')
        _tNac.setStyle(TableStyle([
            ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
            ('LEFTPADDING',(0,0),(-1,-1),0),('RIGHTPADDING',(0,0),(-1,-1),0),
            ('TOPPADDING',(0,0),(-1,-1),0),('BOTTOMPADDING',(0,0),(-1,-1),0),
            ('RIGHTPADDING',(0,0),(0,0),6),
        ]))
        story.append(_tNac)
    story.append(Spacer(1,3*mm))
    if _ia_intro_txt:
        story.append(p("Introducción", s_h1))
        for _par in [x.strip() for x in _ia_intro_txt.split('\n') if x.strip()]:
            story.append(p(_clean(_par), s_body))
        if _ia_intro_prov:
            story.append(p(_ia_intro_prov, ParagraphStyle('iaProv', parent=s_small, textColor=HexColor('#999999'), fontSize=7, leading=9)))
        story.append(Spacer(1,3*mm))
    # Gráfico
    if img_data:
        try:
            im_io=io.BytesIO(img_data)
            # reportlab Image needs file-like; keep aspect
            from PIL import Image as PILImage
            pil=PILImage.open(io.BytesIO(img_data))
            w,h=pil.size
            max_w=160*mm; max_h=160*mm
            ratio=min(max_w/w, max_h/h)
            iw=w*ratio; ih=h*ratio
            story.append(Image(im_io, width=iw, height=ih))
            story.append(Spacer(1,3*mm))
        except Exception:
            pass
    elif svg_txt:
        story.append(p("Gráfico SVG no rasterizado — para ver el gráfico, enviar PNG desde el navegador.", s_small))
        story.append(Spacer(1,3*mm))
    # Ficha básica
    story.append(p("Ficha básica", s_h1))
    # Tipo y estrategia
    if ficha['tipo']:
        story.append(p(f"<b>Tipo y estrategia: {ficha['tipo']}</b>", s_h2))
        if ficha['tipo_descripcion']:
            story.append(p(_clean(ficha['tipo_descripcion']), s_body))
    if ficha['autoridad']:
        story.append(p(f"<b>Autoridad: {ficha['autoridad']}</b>", s_h2))
        if ficha['autoridad_descripcion']:
            story.append(p(_clean(ficha['autoridad_descripcion']), s_body))
    if ficha['perfil']:
        _perfil_info=ficha['perfil_detalle']
        story.append(p(f"<b>Perfil: {ficha['perfil']}</b> — {_perfil_info.get('nombre','')} {_perfil_info.get('emojis','')}", s_h2))
        if _perfil_info.get('descripcion'):
            story.append(p(_clean(_perfil_info.get('descripcion')), s_body))
    story.append(p(f"<b>Definición: {ficha['definicion']}</b>", s_h2))
    if ficha['definicion_descripcion']:
        story.append(p(_clean(ficha['definicion_descripcion']), s_body))
    # Cruz de Encarnación — solo si hay descripción (si no, no se muestra ni título)
    _cruz_nombre = (ficha.get('cruz') or '').strip() if ficha.get('cruz') else ''
    _cruz_desc = (ficha.get('cruz_descripcion') or '').strip() if ficha.get('cruz_descripcion') else ''
    if _cruz_desc:
        if not _cruz_nombre:
            _cruz_nombre = 'Cruz de Encarnación'
        story.append(p(f"<b>{_cruz_nombre}</b>", s_h2))
        story.append(p(_clean(_cruz_desc), s_body))
        story.append(Spacer(1,2*mm))
    # Informe personalizado por persona (informe.csv: nombre;informe)
    _inf=(ficha.get('informe') or '').strip()
    if _inf:
        story.append(p("Informe personalizado", s_h1))
        for _par in [x.strip() for x in _inf.split('\n') if x.strip()]:
            if _par.startswith('#'):
                _h=_par.lstrip('#').strip()
                if _h:
                    story.append(p(_h, s_h2))
            else:
                story.append(p(_clean(_par), s_body))
        story.append(Spacer(1,3*mm))
    # Autoconocimiento — test corto guardado en test.csv (va luego del informe IA
    # y de la ficha básica, antes de los Centros). Solo si existe.
    try:
        _test = _leer_test(persona)
    except Exception:
        _test = None
    if _test and str(_test.get('informe') or '').strip():
        story.append(p("Autoconocimiento — test corto", s_h1))
        _resumen = ' · '.join([x for x in [
            ("Eneatipo " + str(_test.get('eneatipo') or '').strip()) if str(_test.get('eneatipo') or '').strip() else '',
            ("Dosha " + str(_test.get('dosha_dom') or '').strip()) if str(_test.get('dosha_dom') or '').strip() else '',
            ("Vida " + str(_test.get('vida') or '').strip() + " Destino " + str(_test.get('destino') or '').strip()) if (str(_test.get('vida') or '').strip() or str(_test.get('destino') or '').strip()) else '',
            ("Sol en " + str(_test.get('solar') or '').strip()) if str(_test.get('solar') or '').strip() else '',
        ] if x])
        if _resumen:
            story.append(p(_resumen, s_body))
        story.append(p(_clean(str(_test.get('informe') or '')), s_body))
        story.append(Spacer(1,3*mm))
    # Centros (Definidos en negrita, Indefinidos en gris 80%)
    story.append(p("Centros — Definido / Indefinido", s_h1))
    _CENTRO_NOMBRE={'G':'G (Identidad y Amor)','Ego':'Corazón (Ego)','Bazo':'Bazo (Instinto)'}
    def _nombre_centro(n): return _CENTRO_NOMBRE.get(n, n)
    s_centro_def=ParagraphStyle('centroDef', parent=s_small, fontName='Helvetica-Bold', textColor=HexColor('#111111'))
    s_centro_indef=ParagraphStyle('centroIndef', parent=s_small, textColor=HexColor('#616161'))
    s_estado_def=ParagraphStyle('estadoDef', parent=s_small, fontName='Helvetica-Bold', textColor=HexColor('#111111'))
    s_estado_indef=ParagraphStyle('estadoIndef', parent=s_small, textColor=HexColor('#616161'))
    s_desc_def=ParagraphStyle('descDef', parent=s_small, textColor=HexColor('#111111'))
    s_desc_indef=ParagraphStyle('descIndef', parent=s_small, textColor=HexColor('#616161'))
    rows=[[p("<b>Centro</b>",s_small), p("<b>Estado</b>",s_small), p("<b>Descripción</b>",s_small)]]
    for cd in ficha['centros_detalle']:
        es_def=cd['estado']=='Definido'
        sc_centro=s_centro_def if es_def else s_centro_indef
        sc_estado=s_estado_def if es_def else s_estado_indef
        sc_desc=s_desc_def if es_def else s_desc_indef
        _mz=_centros_matriz_detallada().get((cd['centro'], cd['estado']))
        if _mz:
            _esc_t=str(_mz.get('tematica') or '').replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')
            _desc_val=(f"<b>{_esc_t}</b><br/>" if _esc_t else '')+'<br/>'.join(_clean(x) for x in _mz.get('parrafos') or [])
            if not _desc_val:
                _desc_val=_clean(cd['descripcion'])
        else:
            _desc_val=_clean(cd['descripcion'])
        rows.append([p(_nombre_centro(cd['centro']), sc_centro), p(cd['estado'], sc_estado), p(_desc_val, sc_desc)])
    t=Table(rows, colWidths=[34*mm, 22*mm, 104*mm])
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),HexColor('#e8eaf6')),('GRID',(0,0),(-1,-1),0.4,HexColor('#cfd8dc')),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),4),('RIGHTPADDING',(0,0),(-1,-1),4)]))
    story.append(t); story.append(Spacer(1,4*mm))
    # Canales — en marco
    story.append(p("Canales definidos", s_h1))
    if ficha['canales']:
        canal_rows=[[p("<b>Canal</b>", s_small), p("<b>Descripción</b>", s_small)]]
        for cd in ficha['canales_detalle']:
            norm=_hd_norm_canal(cd['canal'])
            circ=_canal_circuito(norm)
            emoji=_CANAL_EMOJI.get(norm, '')
            desc_raw=cd['descripcion'] or 'Sin descripción en canales.csv.'
            desc=_clean(desc_raw)
            # evitar duplicar emoji si ya viene
            if emoji and not desc.lstrip().startswith(emoji):
                desc=f"{emoji} {desc}"
            canal_rows.append([p(f"<b>{norm} ({circ})</b>", s_small), p(desc, s_small)])
        tc=Table(canal_rows, colWidths=[28*mm, 132*mm])
        tc.setStyle(TableStyle([
            ('BACKGROUND',(0,0),(-1,0),HexColor('#ede7f6')),
            ('BOX',(0,0),(-1,-1),1.2,HexColor('#5e35b1')),
            ('INNERGRID',(0,0),(-1,-1),0.4,HexColor('#b39ddb')),
            ('VALIGN',(0,0),(-1,-1),'TOP'),
            ('LEFTPADDING',(0,0),(-1,-1),4),('RIGHTPADDING',(0,0),(-1,-1),4),
            ('ROWBACKGROUNDS',(0,1),(-1,-1),[HexColor('#ffffff'), HexColor('#f3e5f5')]),
        ]))
        story.append(tc)
    else:
        story.append(p("Sin canales definidos.", s_body))
    story.append(PageBreak())
    # Puertas — agrupadas por centro, cada puerta con su línea separada por línea horizontal (página nueva)
    story.append(p("Puertas activas — por centro", s_h1))
    story.append(p(
        "<font color=\"#c62828\"><b>● ROJO = Inconsciente</b></font> — no te reconoces en estas conductas (Sombra de Jung) pero los demás sí. Puedes confirmar preguntando a otros si te ven así.<br/>"
        "<font color=\"#111111\"><b>● NEGRO = Consciente</b></font> — esta característica sí te la reconoces.<br/>"
        "<font color=\"#2e7d32\"><b>● VERDE = Ambas</b></font> — activa en consciente e inconsciente (mixta).",
        ParagraphStyle('leyendaColores', parent=s_small, fontSize=7.5, leading=9, spaceAfter=2, textColor=HexColor('#424242'))
    ))
    story.append(Spacer(1,2*mm))
    col_incon=HexColor('#c62828'); col_consc=HexColor('#111111'); col_mixto=HexColor('#2e7d32')
    def _col_estado(est):
        if est=='inconsciente': return col_incon
        if est=='consciente': return col_consc
        if est=='mixto': return col_mixto
        return HexColor('#616161')
    s_puTit=ParagraphStyle('puTit', parent=s_small, fontSize=9, leading=11, spaceAfter=1)
    s_puDesc=ParagraphStyle('puDesc', parent=s_small, fontSize=7.5, leading=9, leftIndent=6, textColor=HexColor('#37474f'), spaceAfter=1)
    s_sep=ParagraphStyle('sep', parent=s_small, alignment=TA_CENTER, textColor=HexColor('#b0bec5'), fontSize=7, leading=7, spaceBefore=1, spaceAfter=1)
    # gris 80% para líneas (titulo y descripción)
    s_linTit=ParagraphStyle('linTit', parent=s_small, fontSize=8, leading=10, leftIndent=6, textColor=HexColor('#616161'))
    s_linDesc=ParagraphStyle('linDesc', parent=s_small, fontSize=7.5, leading=9, leftIndent=6, textColor=HexColor('#616161'))
    if not ficha.get('puertas_por_centro'):
        story.append(p("Sin puertas para mostrar.", s_body))
    else:
        _CENTRO_DISP={'G':'G (Identidad y Amor)','Ego':'Corazón (Ego)','Bazo':'Bazo (Instinto)'}
        for centro, lista in ficha.get('puertas_por_centro', []):
            disp_centro=_CENTRO_DISP.get(centro, centro)
            rows=[]
            rows.append([p(f"<b>Centro: {disp_centro}</b>", ParagraphStyle('centHead', parent=s_h2, fontSize=10, leading=12, textColor=HexColor('#111111'), backColor=HexColor('#f5f5f5')))])
            for _pd in lista:
                est=_pd.get('estado','')
                col=_col_estado(est)
                try: col_hex='#%02x%02x%02x' % (int(col.red*255), int(col.green*255), int(col.blue*255))
                except: col_hex='#616161'
                lin=_pd.get('linea')
                desc_pu_raw=(_pd.get('descripcion') or '').strip()
                # solo primera oración de la puerta (resto del informe igual)
                _primera = (desc_pu_raw.split('\n')[0] if desc_pu_raw else '').strip()
                _m = _re.search(r'(.+?\.)(\s|$)', _primera)
                if _m:
                    _primera = _m.group(1).strip()
                desc_pu=_clean(_primera or 'Sin descripción')
                rows.append([p(f"<font color=\"{col_hex}\"><b>Puerta {_pd['puerta']}</b></font> <font color=\"{col_hex}\">[{est}]</font>", s_puTit)])
                rows.append([p(desc_pu, s_puDesc)])
                # Sin línea asociada: no se pone nada (ni texto ni separador).
                if lin:
                    rows.append([p("<font color=\"#b0bec5\">------------------------------------------------</font>", s_sep)])
                    lin_arq=_pd.get('linea_arquetipo','')
                    lin_ras=_pd.get('linea_rasgo','')
                    tit_lin=f"<b>Línea {lin}</b>" + (f" — {lin_arq}" if lin_arq else "")
                    rows.append([p(tit_lin, s_linTit)])
                    if lin_ras:
                        rows.append([p(_clean(lin_ras), s_linDesc)])
                    else:
                        rows.append([p("Sin descripción de línea.", s_linDesc)])
                if _pd != lista[-1]:
                    rows.append([Spacer(1,2*mm)])
            t_centro=Table(rows, colWidths=[162*mm])
            t_centro.setStyle(TableStyle([
                ('BOX', (0,0), (-1,-1), 1.2, HexColor('#111111')),
                ('BACKGROUND', (0,0), (-1,0), HexColor('#f5f5f5')),
                ('LINEBELOW', (0,0), (-1,0), 1, HexColor('#111111')),
                ('LEFTPADDING', (0,0), (-1,-1), 4),
                ('RIGHTPADDING', (0,0), (-1,-1), 4),
                ('TOPPADDING', (0,0), (-1,-1), 2),
                ('BOTTOMPADDING', (0,0), (-1,-1), 2),
                ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ]))
            story.append(KeepTogether(t_centro))
            story.append(Spacer(1,3*mm))
    try:
        doc.build(story)
    except Exception as e:
        return jsonify({'error': f'Error generando PDF: {e}'}),500
    buf.seek(0)
    fname=f"Informe-{persona.replace(' ','_')}.pdf"
    return (buf.getvalue(), 200, {'Content-Type':'application/pdf','Content-Disposition':f'attachment; filename=\"{fname}\"'})

def _cols_vinculos(df):
    """Detecta columnas de vinculos.csv en formato nuevo o viejo. Devuelve dict rol->columna."""
    cols = list(df.columns)
    low = {c: str(c).strip().lower() for c in cols}
    def pick(*names):
        for c in cols:
            if low[c] in names:
                return c
        return None
    c_fecha, c_hora, c_edad = pick('fecha'), pick('hora'), pick('edad')
    c_lugar, c_nombre = pick('lugar'), pick('nombre')
    c_ref = pick('referente')
    c_vr = next((c for c in cols if 'vinculo' in low[c] or 'vínculo' in low[c]), None)
    if c_vr == c_ref:
        c_vr = next((c for c in cols if c != c_ref and ('referente' in low[c] or 'vinculo' in low[c])), None)
    c_vj = next((c for c in cols if 'jorge' in low[c]), None)
    return {'fecha': c_fecha, 'hora': c_hora, 'edad': c_edad, 'lugar': c_lugar,
            'nombre': c_nombre, 'referente': c_ref, 'vinculo': c_vr, 'jorge': c_vj,
            'bio': next((c for c in cols if low[c] == 'bio'), None)}

def _guardar_vinculo(nombre, referente, vinculo_tipo, fecha='', hora='', lugar=''):
    """Agrega una fila a vinculos.csv respetando su cabecera actual (nueva o vieja).

    Una persona puede tener varias filas (ej. hijo de A + pareja de B); solo se
    evita duplicar el mismo trío nombre+referente+tipo.
    """
    if not nombre or not referente or not vinculo_tipo:
        return
    if VINCULOS_PATH.exists():
        try:
            df = _leer_vinculos_df()
            df.columns = [str(c).strip() for c in df.columns]
            mapa = _cols_vinculos(df)
            if mapa['nombre'] and mapa['referente'] and mapa['vinculo']:
                trio = (nombre.strip().lower(), referente.strip().lower(), vinculo_tipo.strip().lower())
                for _, row in df.iterrows():
                    otro = (str(row.get(mapa['nombre']) or '').strip().lower(),
                            str(row.get(mapa['referente']) or '').strip().lower(),
                            str(row.get(mapa['vinculo']) or '').strip().lower())
                    if otro == trio:
                        return
            header = list(df.columns)
        except (StopIteration, ValueError, IndexError, KeyError):
            header = ['fecha', 'hora', 'Edad', 'Lugar', 'Nombre', 'vinculo con el referente', 'Referente']
    else:
        header = ['fecha', 'hora', 'Edad', 'Lugar', 'Nombre', 'vinculo con el referente', 'Referente']
        with open(VINCULOS_PATH, 'w', newline='', encoding='utf-8-sig') as f:
            csv.writer(f, delimiter=';').writerow(header)
    mapa = _cols_vinculos(pd.DataFrame(columns=header))
    # Compatibilidad con formato viejo (con columna 'vinculo con Jorge'): se deja vacía.
    valores = {'fecha': fecha or '', 'hora': hora or '', 'edad': '', 'lugar': lugar or '',
               'nombre': nombre, 'referente': referente, 'vinculo': vinculo_tipo, 'jorge': ''}
    fila = []
    for c in header:
        l = str(c).strip().lower()
        if mapa['vinculo'] == c or 'vinculo' in l or 'vínculo' in l:
            fila.append(valores['vinculo'] if c != mapa.get('jorge') else '')
        elif mapa['referente'] == c or l == 'referente':
            fila.append(valores['referente'])
        elif mapa['nombre'] == c or l == 'nombre':
            fila.append(valores['nombre'])
        elif mapa['fecha'] == c or l == 'fecha':
            fila.append(valores['fecha'])
        elif mapa['hora'] == c or l == 'hora':
            fila.append(valores['hora'])
        elif mapa['edad'] == c or l == 'edad':
            fila.append(valores['edad'])
        elif mapa['lugar'] == c or l == 'lugar':
            fila.append(valores['lugar'])
        else:
            fila.append('')
    with open(VINCULOS_PATH, 'a', newline='', encoding='utf-8-sig') as f:
        csv.writer(f, delimiter=';').writerow(fila)
    _cache_invalidate(VINCULOS_PATH)

def _anexar_fila_vinculo(nombre, fecha='', hora='', lugar='', referente='', vinculo_tipo=''):
    """Agrega una fila a vinculos.csv aunque no haya vínculo (fecha/hora/lugar
    solos). Así Modificar puede cargarlos después. No duplica: si ya hay una
    fila con ese nombre, no hace nada."""
    nombre = str(nombre or '').strip()
    if not nombre:
        return
    sep = ';'
    vhead = ['fecha', 'hora', 'Edad', 'Lugar', 'Nombre', 'vinculo con el referente', 'Referente']
    existe = VINCULOS_PATH.exists()
    if existe:
        with open(VINCULOS_PATH, 'r', encoding='utf-8-sig', newline='') as f:
            muestra = f.read(4096)
            if muestra.count('\t') > muestra.count(';'):
                sep = '\t'
        with open(VINCULOS_PATH, 'r', encoding='utf-8-sig', newline='') as f:
            vfilas = [r for r in csv.reader(f, delimiter=sep)]
        if vfilas:
            vhead = vfilas[0]
            mapa0 = _cols_vinculos(pd.DataFrame(columns=vhead))
            pos0 = {k: (vhead.index(v) if v in vhead else None) for k, v in mapa0.items()}
            if pos0.get('nombre') is not None:
                for r in vfilas[1:]:
                    if pos0['nombre'] < len(r) and str(r[pos0['nombre']] or '').strip().lower() == nombre.lower():
                        return
    mapa = _cols_vinculos(pd.DataFrame(columns=vhead))
    # mapa trae NOMBRES de columna -> pasar a índices posicionales.
    pos = {k: (vhead.index(v) if v in vhead else None) for k, v in mapa.items()}
    fila = [''] * len(vhead)
    def _set(col, val):
        if col is not None:
            fila[col] = val
    _set(pos.get('fecha'), fecha or '')
    _set(pos.get('hora'), hora or '')
    _set(pos.get('lugar'), lugar or '')
    _set(pos.get('nombre'), nombre)
    _set(pos.get('referente'), referente or '')
    _set(pos.get('vinculo'), vinculo_tipo or '')
    if existe:
        with open(VINCULOS_PATH, 'a', newline='', encoding='utf-8-sig') as f:
            csv.writer(f, delimiter=sep).writerow(fila)
    else:
        with open(VINCULOS_PATH, 'w', newline='', encoding='utf-8-sig') as f:
            w = csv.writer(f, delimiter=sep)
            w.writerow(vhead)
            w.writerow(fila)
    _cache_invalidate(VINCULOS_PATH)

def _guardar_bio_csv(nombre, bio, campo='bio'):
    """Guarda la bio (corta o larga) en la fila propia de la persona en vinculos.csv."""
    campo = 'bio_larga' if str(campo or '').strip().lower() == 'bio_larga' else 'bio'
    sep = ';'
    filas = []
    if VINCULOS_PATH.exists():
        with open(VINCULOS_PATH, 'r', encoding='utf-8-sig', newline='') as f:
            muestra = f.read(4096)
            if muestra.count('\t') > muestra.count(';'):
                sep = '\t'
        with open(VINCULOS_PATH, 'r', encoding='utf-8-sig', newline='') as f:
            filas = list(csv.reader(f, delimiter=sep))
    head = filas[0] if filas else ['fecha', 'hora', 'Edad', 'Lugar', 'Nombre',
                                   'vinculo con el referente', 'Referente', 'bio']
    low = [str(c).strip().lower() for c in head]
    if campo not in low:
        head = head + [campo]
        low = low + [campo]
        for r in filas[1:]:
            r.append('')
    if not filas:
        filas = [head]
    else:
        filas[0] = head
    pos_nom = low.index('nombre') if 'nombre' in low else None
    pos_bio = low.index(campo)
    pos_ref = low.index('referente') if 'referente' in low else None
    if pos_nom is None:
        return False, 'vinculos.csv no tiene columna Nombre'
    objetivo = None
    for r in filas[1:]:
        if pos_nom < len(r) and str(r[pos_nom] or '').strip().lower() == nombre.lower():
            es_propia = (pos_ref is None) or (pos_ref >= len(r)) or not str(r[pos_ref] or '').strip()
            if es_propia:
                objetivo = r
                break
            if objetivo is None:
                objetivo = r
    if objetivo is None:
        objetivo = [''] * len(head)
        objetivo[pos_nom] = nombre
        filas.append(objetivo)
    while len(objetivo) < len(head):
        objetivo.append('')
    objetivo[pos_bio] = bio
    try:
        with open(VINCULOS_PATH, 'w', newline='', encoding='utf-8-sig') as f:
            csv.writer(f, delimiter=sep).writerows(filas)
    except Exception as e:
        return False, f'no se pudo guardar: {e}'
    _cache_clear()
    return True, ''


def _guardar_bio_xlsx(path, nombre, bio, campo='bio'):
    """Guarda la bio (corta o larga) en la hoja 'vinculos' del xlsx de origen (modo A)."""
    campo = 'bio_larga' if str(campo or '').strip().lower() == 'bio_larga' else 'bio'
    try:
        from openpyxl import load_workbook
        wb = load_workbook(path)
    except PermissionError:
        return False, 'el xlsx esta abierto en Excel; cerralo para poder guardar'
    except Exception as e:
        return False, f'no se pudo abrir el xlsx: {e}'
    try:
        if 'vinculos' not in wb.sheetnames:
            return False, 'el xlsx no tiene hoja vinculos'
        ws = wb['vinculos']
        head = [str(ws.cell(row=1, column=c).value or '').strip().lower()
                for c in range(1, ws.max_column + 1)]
        c_nom = head.index('nombre') + 1 if 'nombre' in head else None
        c_ref = head.index('referente') + 1 if 'referente' in head else None
        if c_nom is None:
            return False, 'hoja vinculos sin columna Nombre'
        if campo in head:
            c_bio = head.index(campo) + 1
        else:
            c_bio = ws.max_column + 1
            ws.cell(row=1, column=c_bio, value=campo)
        objetivo = None
        for r in range(2, ws.max_row + 1):
            val = str(ws.cell(row=r, column=c_nom).value or '').strip().lower()
            if val == nombre.lower():
                ref = str(ws.cell(row=r, column=c_ref).value or '').strip() if c_ref else ''
                if not ref:
                    objetivo = r
                    break
                if objetivo is None:
                    objetivo = r
        if objetivo is None:
            objetivo = ws.max_row + 1
            ws.cell(row=objetivo, column=c_nom, value=nombre)
        ws.cell(row=objetivo, column=c_bio, value=bio)
    except Exception as e:
        return False, f'no se pudo actualizar el xlsx: {e}'
    try:
        wb.save(path)
    except PermissionError:
        return False, 'el xlsx esta abierto en Excel; cerralo para poder guardar'
    except Exception as e:
        return False, f'no se pudo guardar: {e}'
    _cache_clear()
    return True, ''


def _guardar_bio(nombre, bio, campo='bio'):
    nombre = str(nombre or '').strip()
    if not nombre:
        return False, 'falta el nombre'
    bio = str(bio or '')
    p = _FUENTE['path']
    if p is not None:
        return _guardar_bio_xlsx(p, nombre, bio, campo)
    return _guardar_bio_csv(nombre, bio, campo)


@app.route('/api/bio', methods=['POST'])
def api_bio():
    """Guarda la bio de la persona en la fuente activa (xlsx de origen o vinculos.csv)."""
    try:
        data = request.get_json(force=True) or {}
    except Exception:
        return jsonify({'error': 'JSON invalido'}), 400
    nombre = str(data.get('persona') or '').strip()
    if not nombre:
        return jsonify({'error': 'falta persona'}), 400
    ok, err = _guardar_bio(nombre, data.get('bio') or '', data.get('campo') or 'bio')
    if not ok:
        return jsonify({'error': err}), 400
    return jsonify({'ok': True})


DINAMICA_CSV_PATH = Path("dinamica_compuesta.csv")
DINAMICA_CSV_COLS = ['p1', 'p2', 'texto', 'actualizado']


def _clave_pareja(a, b):
    return (str(a or '').strip(), str(b or '').strip())


def _leer_dinamica(p1, p2):
    try:
        if not DINAMICA_CSV_PATH.exists():
            return ''
        import io as _io
        raw = DINAMICA_CSV_PATH.read_bytes()
        s = None
        for enc in ('utf-8-sig', 'utf-8', 'cp1252', 'latin-1'):
            try:
                s = raw.decode(enc)
                break
            except Exception:
                continue
        if s is None:
            return ''
        muestra = s.splitlines()[0] if s.splitlines() else ''
        sep = '\t' if ('\t' in muestra and ';' not in muestra) else ';'
        filas = [r for r in csv.reader(_io.StringIO(s), delimiter=sep)]
        if not filas:
            return ''
        head = [str(c or '').strip().lower() for c in filas[0]]
        if 'p1' not in head or 'p2' not in head:
            return ''
        i1, i2 = head.index('p1'), head.index('p2')
        it = head.index('texto') if 'texto' in head else -1
        a, b = _clave_pareja(p1, p2)
        for r in filas[1:]:
            x1 = str(r[i1] if i1 < len(r) else '').strip()
            x2 = str(r[i2] if i2 < len(r) else '').strip()
            if (x1 == a and x2 == b) or (x1 == b and x2 == a):
                return r[it] if it >= 0 and it < len(r) else ''
        return ''
    except Exception:
        return ''


def _guardar_dinamica(p1, p2, texto):
    try:
        from datetime import datetime as _dt
        import io as _io
        head = list(DINAMICA_CSV_COLS)
        cuerpo = []
        if DINAMICA_CSV_PATH.exists():
            raw = DINAMICA_CSV_PATH.read_bytes()
            for enc in ('utf-8-sig', 'utf-8', 'cp1252', 'latin-1'):
                try:
                    s = raw.decode(enc)
                    break
                except Exception:
                    continue
            else:
                s = ''
            muestra = s.splitlines()[0] if s.splitlines() else ''
            sep = '\t' if ('\t' in muestra and ';' not in muestra) else ';'
            leidas = [r for r in csv.reader(_io.StringIO(s), delimiter=sep)] if s else []
            if leidas:
                head = leidas[0] if leidas[0] else head
                cuerpo = leidas[1:]
        a, b = _clave_pareja(p1, p2)
        _fecha = _dt.now().strftime('%Y-%m-%d %H:%M')
        lows = [str(c or '').strip().lower() for c in head]
        if 'p1' not in lows or 'p2' not in lows:
            head, cuerpo = list(DINAMICA_CSV_COLS), []
            lows = [c.lower() for c in head]
        i1, i2 = lows.index('p1'), lows.index('p2')
        it = lows.index('texto') if 'texto' in lows else -1
        ia = lows.index('actualizado') if 'actualizado' in lows else -1
        puesta = False
        for i, r in enumerate(cuerpo):
            x1 = str(r[i1] if i1 < len(r) else '').strip()
            x2 = str(r[i2] if i2 < len(r) else '').strip()
            if (x1 == a and x2 == b) or (x1 == b and x2 == a):
                while len(r) < len(head):
                    r.append('')
                r[i1], r[i2] = a, b
                if it >= 0:
                    r[it] = str(texto or '')
                if ia >= 0:
                    r[ia] = _fecha
                cuerpo[i] = r
                puesta = True
                break
        if not puesta:
            nueva = ['' for _ in head]
            nueva[i1], nueva[i2] = a, b
            if it >= 0:
                nueva[it] = str(texto or '')
            if ia >= 0:
                nueva[ia] = _fecha
            cuerpo.append(nueva)
        with open(DINAMICA_CSV_PATH, 'w', newline='', encoding='utf-8-sig') as f:
            w = csv.writer(f, delimiter=';')
            w.writerow(head)
            w.writerows(cuerpo)
        return True
    except Exception:
        return False


@app.route('/api/dinamica_compuesta', methods=['GET', 'POST'])
def api_dinamica_compuesta():
    """Texto manual editable por pareja P1/P2, guardado en dinamica_compuesta.csv. Sin IA."""
    if _perfiles_cuenta_actual() is not None:
        # Cuentas: todavía no se guarda por cuenta (no mezclar con el archivo local).
        if request.method == 'GET':
            return jsonify({'p1': (request.args.get('p1') or ''), 'p2': (request.args.get('p2') or ''), 'texto': ''})
        return jsonify({'ok': True, 'solo_local': True})
    if request.method == 'GET':
        p1 = str(request.args.get('p1') or '').strip()
        p2 = str(request.args.get('p2') or '').strip()
        if not p1 or not p2:
            return jsonify({'error': 'faltan p1 y p2'}), 400
        return jsonify({'p1': p1, 'p2': p2, 'texto': _leer_dinamica(p1, p2)})
    try:
        data = request.get_json(force=True) or {}
    except Exception:
        return jsonify({'error': 'JSON invalido'}), 400
    p1 = str(data.get('p1') or '').strip()
    p2 = str(data.get('p2') or '').strip()
    if not p1 or not p2:
        return jsonify({'error': 'faltan p1 y p2'}), 400
    if not _guardar_dinamica(p1, p2, data.get('texto') or ''):
        return jsonify({'error': 'no se pudo guardar'}), 500
    return jsonify({'ok': True})


def _normalizar_canal(raw):
    """Clave canónica de canal ordenando sus dos puertas (20-10 -> 10-20)."""
    try:
        a, b = sorted(int(x) for x in str(raw).replace('_', '-').split('-')[:2])
        return f"{a}-{b}"
    except (ValueError, TypeError, AttributeError):
        return str(raw).strip()

def mapa_centros():
    """Mapa 'centro|estado' (minúsculas) -> descripcion, para correlacionar panel/gráfico."""
    mapa = {}
    for c in cargar_centros():
        clave = f"{(c.get('centro') or '').strip().lower()}|{(c.get('estado') or '').strip().lower()}"
        mapa[clave] = c.get('descripcion', '')
    return mapa

def mapa_canales():
    """Mapa canal normalizado -> descripcion."""
    mapa = {}
    for c in cargar_canales():
        mapa[_normalizar_canal(c.get('elemento', ''))] = c.get('descripcion', '')
    return mapa

def mapa_puertas():
    """Mapa nro de puerta (str) -> descripcion."""
    return {str(p.get('elemento', '')).strip(): p.get('descripcion', '') for p in cargar_puertas()}

@app.route('/api/descripciones')
def api_descripciones():
    """Expone los tres diccionarios de descripciones (los consumen paneles y popups)."""
    return jsonify({
        'centros': mapa_centros(),
        'canales': mapa_canales(),
        'puertas': mapa_puertas(),
    })

def _parse_puerta_linea(valor_puerta, valor_linea=None):
    """Acepta 'Puerta' como 41 o decimal '41.1' y 'Linea' opcional. Devuelve (puerta 1-64, linea 1-6 o None)."""
    linea = None
    try:
        if valor_linea is not None and str(valor_linea).strip() not in ('', 'nan', 'None'):
            linea = int(float(str(valor_linea).strip()))
            if not 1 <= linea <= 6:
                linea = None
    except (ValueError, TypeError, AttributeError):
        linea = None
    try:
        s = str(valor_puerta).strip()
        if '.' in s:
            ent, dec = s.split('.', 1)
            puerta = int(ent)
            if linea is None and dec.strip().isdigit():
                d = int(dec.strip())
                if 1 <= d <= 6:
                    linea = d
        else:
            puerta = int(float(s))
    except (ValueError, TypeError, AttributeError):
        return None, None
    if not 1 <= puerta <= 64:
        return None, None
    return puerta, linea

def _cols_datos(df):
    """Detecta columnas de datos.csv aunque cambien de nombre/separador.

    Puerta: primera columna que contenga 'puerta' ('Puerta'; antes 'Puerta Inc').
    Línea: columna 'linea'/'línea' si existe. C/I: columna 'c/i' (o 'ci').
    Devuelve (c_nombre, c_puerta, c_linea|None, c_ci). Falla con KeyError claro si falta.
    """
    low = {c: str(c).strip().lower() for c in df.columns}
    c_nombre = next((c for c in df.columns if low[c] == 'nombre'), None)
    c_puerta = next((c for c in df.columns if 'puerta' in low[c]), None)
    c_linea = next((c for c in df.columns if 'linea' in low[c].replace('í', 'i')), None)
    c_ci = next((c for c in df.columns if low[c].replace(' ', '') in ('c/i', 'c-i', 'ci')), None)
    faltan = [n for n, c in (('Nombre', c_nombre), ('Puerta', c_puerta), ('C/I', c_ci)) if c is None]
    if faltan:
        raise KeyError(f"datos.csv: no se encuentran las columnas {faltan}. Cabecera actual: {list(df.columns)}")
    return c_nombre, c_puerta, c_linea, c_ci

def _linea_o_nan(v):
    try:
        if v in (None, '', 'nan', 'None'):
            return float('nan')
        n = int(float(str(v)))
        return n if 1 <= n <= 6 else float('nan')
    except (ValueError, TypeError):
        return float('nan')


def _perfiles_cuenta_actual():
    """Perfiles de la cuenta logueada (Neon), memoizados por request. None si no hay cuenta."""
    try:
        if not has_request_context():
            return None
        ct = _cuenta_actual()
        if not ct:
            return None
        if getattr(g, 'perfiles_cuenta', None) is None:
            g.perfiles_cuenta = _auth.perfiles_de(ct['id'])
        return g.perfiles_cuenta
    except Exception:
        return None


def _dj(p):
    dj = p.get('datos_json') or {}
    if isinstance(dj, str):
        try:
            dj = _json.loads(dj)
        except Exception:
            dj = {}
    return dj if isinstance(dj, dict) else {}


def _df_de_cuenta(perfiles):
    """DataFrame virtual (Nombre;Puerta;Linea;C/I) con las personas de la cuenta."""
    filas = []
    for p in perfiles:
        nombre = str(p.get('nombre') or '').strip()
        if not nombre:
            continue
        dj = _dj(p)
        for campo, estado in (('inconscientes', 'Inconsciente'), ('conscientes', 'Consciente')):
            lista = dj.get(campo) or []
            lineas = dj.get(campo + '_lineas') or []
            for i, g in enumerate(lista):
                try:
                    puerta = int(float(str(g)))
                except (ValueError, TypeError):
                    continue
                if not 1 <= puerta <= 64:
                    continue
                filas.append({'Nombre': nombre, 'Puerta': puerta,
                              'Linea': _linea_o_nan(lineas[i] if i < len(lineas) else None),
                              'C/I': estado})
    return pd.DataFrame(filas, columns=['Nombre', 'Puerta', 'Linea', 'C/I'])


def cargar_datos():
    """Cacheado por mtime (una sola lectura de datos.csv por versión del archivo).

    Con sesión iniciada devuelve SOLO las personas de esa cuenta (Neon)."""
    _perfiles = _perfiles_cuenta_actual()
    if _perfiles is not None:
        return _df_de_cuenta(_perfiles)
    def _load():
        try:
            df = _tabla_mutable('datos', CSV_PATH, sep=';')
        except Exception as e:
            raise e
        if len(df.columns) < 3:
            raise ValueError(f"datos.csv: parece tener otro separador (se esperan columnas con ';'). Cabecera leída: {list(df.columns)}")
        c_nombre, c_puerta, c_linea, c_ci = _cols_datos(df)
        df = df[df[c_nombre].notna()]
        df = df[df[c_nombre].astype(str).str.strip() != '']
        df = df[df[c_nombre].astype(str).str.strip() != 'FORMULAS']
        puertas, lineas = [], []
        for _, row in df.iterrows():
            p, l = _parse_puerta_linea(row.get(c_puerta), row.get(c_linea) if c_linea else None)
            puertas.append(p)
            lineas.append(l)
        df = df.rename(columns={c_nombre: 'Nombre', c_puerta: 'Puerta', c_ci: 'C/I'})
        df['Puerta'] = puertas
        df['Linea'] = lineas
        df = df[df['Puerta'].notna()]
        df['Puerta'] = df['Puerta'].astype(int)
        return df
    _src, _key = _cache_arg(CSV_PATH, 'datos')
    return _cache_get(_src, _load, key=_key)

def cargar_svg():
    def _load():
        with open(SVG_PATH, 'r', encoding='utf-8') as f:
            return f.read()
    return _cache_get(SVG_PATH, _load)

def get_personas():
    df = cargar_datos()
    return sorted(df['Nombre'].dropna().unique().tolist())

def get_persona_default():
    """Primera persona en orden de archivo de datos.csv (no alfabético)."""
    df = cargar_datos()
    if df.empty:
        return ''
    return str(df['Nombre'].iloc[0])


FOTOS_PERSONAS_PATH = Path("fotos_personas.csv")

# La foto puede venir como archivo local, URL o imagen incrustada (data:).
# En Render solo la imagen incrustada sobrevive (el disco es temporal), así que
# el navegador la reduce y la manda como data: URL para guardarla en Neon.
FOTO_MAX_BYTES = 3_000_000


def _es_data_url(foto):
    return str(foto or '').strip().lower().startswith('data:')


def _error_foto(foto):
    """Devuelve el mensaje de error si la foto no es aceptable."""
    if _es_data_url(foto) and len(str(foto)) > FOTO_MAX_BYTES:
        return 'La imagen es demasiado grande: elegí una foto más chica'
    return ''



def _cargar_fotos_personas():
    """Devuelve dict nombre(lower)->url foto. Archivo opcional nombre;foto."""
    out = {}
    try:
        with open(FOTOS_PERSONAS_PATH, 'r', encoding='utf-8-sig', newline='') as f:
            import csv as _csv
            reader = _csv.DictReader(f, delimiter=';')
            for row in reader:
                nom = str((row or {}).get('nombre') or '').strip()
                if nom:
                    out[nom.lower()] = str((row or {}).get('foto') or '').strip()
    except FileNotFoundError:
        pass
    except Exception:
        pass
    return out


def _guardar_foto_persona(nombre, foto):
    nombre = str(nombre or '').strip()
    if not nombre:
        return
    foto = str(foto or '').strip()
    rows = []
    fieldnames = ['nombre', 'foto']
    try:
        with open(FOTOS_PERSONAS_PATH, 'r', encoding='utf-8-sig', newline='') as f:
            import csv as _csv
            reader = _csv.DictReader(f, delimiter=';')
            if reader.fieldnames:
                fieldnames = [str(c).strip() for c in reader.fieldnames]
            for row in reader:
                if str((row or {}).get('nombre') or '').strip().lower() != nombre.lower():
                    rows.append({k: str((row or {}).get(k) or '') for k in fieldnames})
    except FileNotFoundError:
        pass
    # quitar existente y agregar si hay foto
    rows = [r for r in rows if str(r.get('nombre') or '').strip().lower() != nombre.lower()]
    if foto:
        row = {k: '' for k in fieldnames}
        if 'nombre' not in fieldnames:
            fieldnames = ['nombre', 'foto'] + [k for k in fieldnames if k not in ('nombre', 'foto')]
        row['nombre'] = nombre
        row['foto'] = foto
        rows.append(row)
    with open(FOTOS_PERSONAS_PATH, 'w', newline='', encoding='utf-8-sig') as f:
        import csv as _csv
        w = _csv.DictWriter(f, fieldnames=fieldnames, delimiter=';')
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, '') for k in fieldnames})


def _borrar_foto_persona(nombre):
    nombre = str(nombre or '').strip()
    if not nombre:
        return
    rows = []
    fieldnames = ['nombre', 'foto']
    try:
        with open(FOTOS_PERSONAS_PATH, 'r', encoding='utf-8-sig', newline='') as f:
            import csv as _csv
            reader = _csv.DictReader(f, delimiter=';')
            if reader.fieldnames:
                fieldnames = [str(c).strip() for c in reader.fieldnames]
            for row in reader:
                if str((row or {}).get('nombre') or '').strip().lower() != nombre.lower():
                    rows.append({k: str((row or {}).get(k) or '') for k in fieldnames})
    except FileNotFoundError:
        return
    with open(FOTOS_PERSONAS_PATH, 'w', newline='', encoding='utf-8-sig') as f:
        import csv as _csv
        w = _csv.DictWriter(f, fieldnames=fieldnames, delimiter=';')
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, '') for k in fieldnames})


# ---------- Fuente de datos: elegir xlsx (modo A) o volver a CSV ----------
def _elegir_xlsx_dialogo():
    """Abre el diálogo nativo de Windows (tkinter) en un subproceso aparte.
    Devuelve la ruta elegida o '' si se cancela."""
    import subprocess
    import sys
    codigo = (
        "import tkinter as tk\n"
        "from tkinter import filedialog\n"
        "r = tk.Tk()\n"
        "r.withdraw()\n"
        "r.attributes('-topmost', True)\n"
        "p = filedialog.askopenfilename(title='Elegir datos (.xlsx)',\n"
        "    filetypes=[('Excel', '*.xlsx')], initialdir='.')\n"
        "print(p)\n"
    )
    try:
        res = subprocess.run([sys.executable, '-c', codigo],
                             capture_output=True, text=True, timeout=600)
    except Exception:
        return ''
    salida = (res.stdout or '').strip()
    return salida.splitlines()[-1].strip() if salida else ''


@app.route('/api/foto_local')
def api_foto_local():
    """Sirve una foto local por su ruta para poder previsualizarla."""
    ruta = str(request.args.get('ruta') or '').strip().strip('"')
    if not ruta:
        return jsonify({'error': 'Falta ruta'}), 400
    p = Path(ruta).expanduser()
    if not p.is_file():
        return jsonify({'error': 'La foto no existe o se movió'}), 404
    if p.suffix.lower() not in ('.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp'):
        return jsonify({'error': 'Formato de imagen no permitido'}), 400
    return send_file(str(p))


@app.route('/api/persona_foto', methods=['POST'])
def api_persona_foto():
    """Guarda (o borra) la foto de una persona: única fuente para el panel,
    Persona 1/2, el clan y el informe."""
    data = request.get_json(force=True, silent=True) or {}
    nombre = str(data.get('nombre') or '').strip()
    if not nombre:
        return jsonify({'error': 'Falta el nombre'}), 400
    foto = str(data.get('foto') or '').strip()
    err_foto = _error_foto(foto)
    if err_foto:
        return jsonify({'error': err_foto}), 413
    ct = _cuenta_actual()
    if foto:
        es_url = bool(_re.match(r'^(?:https?:|data:|/)', foto, _re.I))
        if not es_url and not Path(foto).expanduser().is_file():
            return jsonify({'error': 'La foto no existe o se movió'}), 400
        # Con sesión, la imagen incrustada ya queda en el perfil (Neon); no se
        # copia al CSV local para no inflarlo.
        if not (_es_data_url(foto) and ct):
            _guardar_foto_persona(nombre, foto)
    else:
        _borrar_foto_persona(nombre)
    if ct:
        try:
            previo = next((p for p in (_perfiles_cuenta_actual() or [])
                           if str(p.get('nombre') or '').strip().lower() == nombre.lower()), None)
            if previo is not None:
                perfil = dict(previo)
                dj = dict(_dj(previo))
                dj['foto'] = foto
                perfil['datos_json'] = dj
                perfil['foto'] = foto
                _auth.subir_perfil(ct['id'], perfil)
                g.perfiles_cuenta = None
        except Exception:
            pass
    return jsonify({'ok': True, 'nombre': nombre, 'foto': _foto_persona_para(nombre)})


def _validar_xlsx(path):
    """Devuelve '' si el xlsx tiene las 4 hojas mutables; si no, el error."""
    try:
        from openpyxl import load_workbook
        wb = load_workbook(path, read_only=True)
        nombres = list(wb.sheetnames)
        wb.close()
    except Exception as e:
        return f'no se pudo abrir el archivo: {e}'
    faltan = [t for t in _TABLAS_MUTABLES if t not in nombres]
    if faltan:
        return f'faltan hojas: {", ".join(faltan)}'
    return ''


def _fuente_json():
    p = _FUENTE['path']
    return {'activo': p.name if p else None,
            'tipo': 'xlsx' if p else 'csv',
            'entorno': 'render' if _es_render() else 'local',
            'datos_csv_propio': _datos_csv_utilizables(),
            'xlsx': sorted(x.name for x in Path('.').glob('*.xlsx')
                           if not x.name.startswith('~$'))}


@app.route('/api/fuente')
def api_fuente_get():
    return jsonify(_fuente_json())


@app.route('/api/fuente', methods=['POST'])
def api_fuente_post():
    """Fija la fuente. JSON {'path': 'datos_publicos.xlsx'} o {'path': null} = CSV."""
    try:
        data = request.get_json(force=True) or {}
    except Exception:
        data = {}
    path = (data.get('path') or '').strip()
    if not path:
        set_fuente(None)
        return jsonify(_fuente_json())
    p = Path(path)
    if not p.exists():
        return jsonify({'error': f'no existe: {path}'}), 400
    err = _validar_xlsx(p)
    if err:
        return jsonify({'error': err}), 400
    set_fuente(p)
    return jsonify(_fuente_json())


@app.route('/api/fuente/elegir', methods=['POST'])
def api_fuente_elegir():
    """Abre el diálogo nativo y activa el xlsx elegido."""
    ruta = _elegir_xlsx_dialogo()
    if not ruta:
        out = _fuente_json()
        out['cancelado'] = True
        return jsonify(out)
    p = Path(ruta)
    err = _validar_xlsx(p)
    if err:
        return jsonify({'error': err}), 400
    set_fuente(p)
    return jsonify(_fuente_json())

def _cuenta_perfil_desde_payload(data, nombre, previo=None):
    """Valida el payload de Agregar/Modificar y arma el perfil para Neon."""
    es_transito = bool(data.get('transito')) and not data.get('inconscientes')
    if es_transito:
        incon, incon_l = [], []
    else:
        incon, incon_l_dec, err = _validar_puertas(data.get('inconscientes'), 'Inconscientes')
        if err:
            return None, err
        incon_l, err = _validar_lineas(data.get('inconscientes_lineas'), 'Líneas inconscientes')
        if err:
            return None, err
        if incon_l is None:
            incon_l = incon_l_dec or [None] * len(incon)
        else:
            incon_l = [e if e is not None else (incon_l_dec[i] if incon_l_dec and i < len(incon_l_dec) else None)
                       for i, e in enumerate(incon_l)]
    consc, consc_l_dec, err = _validar_puertas(data.get('conscientes'), 'Conscientes')
    if err:
        return None, err
    consc_l, err = _validar_lineas(data.get('conscientes_lineas'), 'Líneas conscientes')
    if err:
        return None, err
    if consc_l is None:
        consc_l = consc_l_dec or [None] * len(consc)
    else:
        consc_l = [e if e is not None else (consc_l_dec[i] if consc_l_dec and i < len(consc_l_dec) else None)
                   for i, e in enumerate(consc_l)]
    previo = previo or {}
    test = _dj(previo).get('test') or {}
    foto = str(data.get('foto') or '').strip() or str(_dj(previo).get('foto') or '').strip() or str(previo.get('foto') or '').strip()
    err_foto = _error_foto(foto)
    if err_foto:
        return None, err_foto
    perfil = _perfil_de_lineas(consc_l[0] if consc_l else None, incon_l[0] if incon_l else None)
    return {
        'nombre': nombre,
        'fecha': str(data.get('fecha') or '').strip() or previo.get('fecha') or '',
        'hora': str(data.get('hora') or '').strip() or previo.get('hora') or '',
        'lugar': str(data.get('lugar') or '').strip() or previo.get('lugar') or '',
        'lat': previo.get('lat'), 'lon': previo.get('lon'), 'tz': previo.get('tz'),
        'tz_name': previo.get('tz_name') or '',
        'foto': foto,
        'visibilidad': data.get('visibilidad') or previo.get('visibilidad') or 'privado',
        'datos_json': {'inconscientes': incon, 'conscientes': consc,
                       'inconscientes_lineas': incon_l, 'conscientes_lineas': consc_l,
                       'perfil': perfil, 'test': test, 'foto': foto},
    }, None


def _cuenta_persona_post(ct, data):
    nombre = str(data.get('nombre', '') or '').strip()
    if not nombre:
        return jsonify({'error': 'El nombre es obligatorio'}), 400
    perfiles = _perfiles_cuenta_actual() or []
    if any(str(p.get('nombre') or '').strip().lower() == nombre.lower() for p in perfiles):
        return jsonify({'error': f'"{nombre}" ya existe'}), 409
    perfil, err = _cuenta_perfil_desde_payload(data, nombre)
    if err:
        return jsonify({'error': err}), 400
    _auth.subir_perfil(ct['id'], perfil)
    g.perfiles_cuenta = None
    return jsonify({'ok': True, 'nombre': nombre, 'personas': get_personas(),
                    'perfil': perfil['datos_json'].get('perfil')}), 201


def _cuenta_persona_put(ct, nombre_viejo, data):
    viejo = str(nombre_viejo or '').strip()
    nuevo = str(data.get('nombre', '') or '').strip() or viejo
    perfiles = _perfiles_cuenta_actual() or []
    previo = next((p for p in perfiles
                   if str(p.get('nombre') or '').strip().lower() == viejo.lower()), None)
    if previo is None:
        return jsonify({'error': f'"{viejo}" no existe'}), 404
    if nuevo != viejo and any(str(p.get('nombre') or '').strip().lower() == nuevo.lower() for p in perfiles):
        return jsonify({'error': f'"{nuevo}" ya existe'}), 409
    perfil, err = _cuenta_perfil_desde_payload(data, nuevo, previo)
    if err:
        return jsonify({'error': err}), 400
    if nuevo != viejo:
        _auth.borrar_perfil(ct['id'], viejo)
    _auth.subir_perfil(ct['id'], perfil)
    g.perfiles_cuenta = None
    return jsonify({'ok': True, 'nombre': nuevo, 'personas': get_personas(),
                    'perfil': perfil['datos_json'].get('perfil')})


@app.route('/')
def index():
    svg_content = cargar_svg()
    # Etapa 1: una sola lectura de datos.csv para personas + default (antes eran 2 lecturas)
    df = cargar_datos()
    try:
        if df.empty:
            personas, persona_default = [], ''
        else:
            personas = sorted(df['Nombre'].dropna().unique().tolist())
            persona_default = str(df['Nombre'].iloc[0])
    except Exception:
        personas = get_personas()
        persona_default = get_persona_default()
    centros = cargar_centros()
    canales = cargar_canales()
    puertas = cargar_puertas()
    return render_template('index.html', 
                         svg_content=svg_content,
                         personas=personas,
                         persona_default=persona_default,
                         vinculos=cargar_vinculos(),
                         centros=centros,
                         canales=canales,
                         puertas=puertas)

@app.route('/lab')
def lab():
    if not (Path(app.template_folder) / 'lab.html').exists():
        return "Lab no incluido en este clon.", 404
    return render_template('lab.html')

@app.route('/filtro')
def filtro():
    return render_template('filtro.html')

@app.route('/api/personas')
def api_personas():
    return jsonify({'personas': get_personas()})

PUB_CSV_PATH = Path("personas_publicas.csv")

def cargar_publicas():
    """personas_publicas.csv (independiente de datos.csv). Soporta formato
    original de 5 columnas y ampliado con cálculo. Cacheado por mtime."""
    def _load():
        try:
            df = pd.read_csv(PUB_CSV_PATH, sep=';', dtype=str, encoding='utf-8-sig')
        except FileNotFoundError:
            return []
        df = df.fillna('')
        cols = set(df.columns)
        def _ints(s, sep):
            out = []
            for x in str(s).split(sep):
                x = x.strip()
                if x.lstrip('-').isdigit():
                    out.append(int(x))
            return out
        filas = []
        for _, r in df.iterrows():
            g = lambda k: str(r.get(k, '') or '').strip()
            pin = _ints(g('puertas_incon'), ',')
            pco = _ints(g('puertas_con'), ',')
            lin = _ints(g('lineas_incon'), ',')
            lco = _ints(g('lineas_con'), ',')
            canales = [x.strip() for x in g('canales').replace(',', '|').split('|') if x.strip()]
            centros = [x.strip() for x in g('centros').replace(',', '|').split('|') if x.strip()]
            todas = sorted(set(pin) | set(pco))
            filas.append({
                'nombre': g('nombre'), 'categoria': g('categoria'),
                'fecha': g('fecha'), 'hora': g('hora'), 'lugar': g('lugar'),
                'nombre_base': g('nombre_base') or g('nombre'),
                'copia': g('copia') or '1/1', 'hora_usada': g('hora_usada') or g('hora'),
                'lat': g('lat'), 'lon': g('lon'), 'tz': g('tz'),
                'perfil': g('perfil'), 'tipo': g('tipo'), 'autoridad': g('autoridad'),
                'definicion': g('definicion'),
                'puertas_incon': pin, 'puertas_con': pco,
                'lineas_incon': lin, 'lineas_con': lco,
                'canales': canales, 'centros': centros,
                'todas_puertas': todas,
                'puertas_mixtas': sorted(set(pin) & set(pco)),
                'warnings': g('warnings'),
            })
        return [f for f in filas if f['nombre']]
    return _cache_get(PUB_CSV_PATH, _load)

@app.route('/publicas')
def publicas():
    filas = cargar_publicas()
    cats = []
    for f in filas:
        if f['categoria'] and f['categoria'] not in cats:
            cats.append(f['categoria'])
    conteo = {c: sum(1 for f in filas if f['categoria'] == c) for c in cats}
    return render_template('publicas.html',
                           svg_content=cargar_svg(),
                           categorias=[{'cat': c, 'n': conteo[c]} for c in cats])

PUBLICAS_XLSX = ['datos_publicos.xlsx','publicos_hoy.xlsx','influyentes_historia.xlsx',
                  'historia_destacados.xlsx','politicos_uy.xlsx','actores_hollywood.xlsx']

def cargar_publicas_canales():
    """Lista de públicos (de las planillas xlsx) con nombre, canales, tipo, perfil y foto.
    Deduplica por nombre (primera aparición)."""
    import openpyxl
    seen = set()
    out = []
    bios_largas = cargar_bios_largas()
    for p in PUBLICAS_XLSX:
        path = Path(p)
        if not path.exists():
            continue
        try:
            wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        except Exception:
            continue
        if 'fichas' not in wb.sheetnames:
            continue
        ws = wb['fichas']
        hdr = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
        def col(name):
            return hdr.index(name) if name in hdr else None
        ci_nombre = col('nombre')
        ci_canales = col('canales')
        ci_tipo = col('tipo')
        ci_perfil = col('perfil')
        ci_foto = col('foto')
        ci_desc = col('descripcion')
        ci_pin = col('puertas_incon')
        ci_pco = col('puertas_con')
        ci_lin = col('lineas_incon')
        ci_lco = col('lineas_con')
        if ci_nombre is None:
            continue
        for r in ws.iter_rows(min_row=2, values_only=True):
            if not r or not r[ci_nombre]:
                continue
            nombre = str(r[ci_nombre]).strip()
            if not nombre or nombre in seen:
                continue
            seen.add(nombre)
            canales_raw = str(r[ci_canales] or '') if ci_canales is not None else ''
            canales = [x.strip() for x in canales_raw.replace(',', '|').split('|') if x.strip()]
            tipo = str(r[ci_tipo]).strip() if ci_tipo is not None and r[ci_tipo] is not None else ''
            perfil = str(r[ci_perfil]).strip() if ci_perfil is not None and r[ci_perfil] is not None else ''
            foto = str(r[ci_foto]).strip() if ci_foto is not None and r[ci_foto] is not None else ''
            if foto:
                foto = '/publicos/' + Path(foto).name
            desc = str(r[ci_desc]).strip() if ci_desc is not None and r[ci_desc] is not None else ''
            def _ints(v):
                out=[]
                for x in str(v or '').split(','):
                    x=x.strip()
                    if x.lstrip('-').isdigit():
                        out.append(int(x))
                return out
            pin = _ints(r[ci_pin] if ci_pin is not None else '')
            pco = _ints(r[ci_pco] if ci_pco is not None else '')
            lin = _ints(r[ci_lin] if ci_lin is not None else '')
            lco = _ints(r[ci_lco] if ci_lco is not None else '')
            todas = sorted(set(pin) | set(pco))
            out.append({'nombre': nombre, 'canales': canales, 'tipo': tipo,
                        'perfil': perfil, 'foto': foto, 'bio': desc,
                        'bio_larga': bios_largas.get(_norm_lugar(nombre), ''),
                        'puertas_incon': pin, 'puertas_con': pco,
                        'lineas_incon': lin, 'lineas_con': lco,
                        'todas_puertas': todas})
        wb.close()
    return out

@app.route('/api/publicas_canales')
def api_publicas_canales():
    return jsonify(cargar_publicas_canales())

@app.route('/api/publicas')
def api_publicas():
    cat = (request.args.get('categoria') or '').strip()
    filas = cargar_publicas()
    if cat:
        filas = [f for f in filas if f['categoria'] == cat]
    return jsonify([{'nombre': f['nombre'], 'perfil': f['perfil'],
                     'copia': f['copia'], 'hora_usada': f['hora_usada'],
                     'fecha': f['fecha'], 'lugar': f['lugar'],
                     'tipo': f['tipo']} for f in filas])

@app.route('/api/publica/<path:nombre>')
def api_publica(nombre):
    for f in cargar_publicas():
        if f['nombre'] == nombre:
            return jsonify(f)
    return jsonify({'error': 'Persona pública no encontrada'}), 404

@app.route('/api/puertas_personas')
def api_puertas_personas():
    """Todas las personas con sus puertas (+ líneas y perfil si se conocen)."""
    df = cargar_datos()
    resultado = {}
    for nombre, grupo in df.groupby('Nombre', sort=False):
        gi = grupo[grupo['C/I'].str.strip().str.lower() == 'inconsciente']
        gc = grupo[grupo['C/I'].str.strip().str.lower() != 'inconsciente']
        incon = [int(x) for x in gi['Puerta'].tolist()]
        consc = [int(x) for x in gc['Puerta'].tolist()]
        incon_l = [None if pd.isna(x) else int(x) for x in gi['Linea'].tolist()]
        consc_l = [None if pd.isna(x) else int(x) for x in gc['Linea'].tolist()]
        perfil = _perfil_de_lineas(consc_l[0] if consc_l else None, incon_l[0] if incon_l else None)
        resultado[str(nombre)] = {
            'inconscientes': incon,  # orden de archivo (planeta si se cargó con Calcular)
            'conscientes': consc,
            'inconscientes_lineas': incon_l,
            'conscientes_lineas': consc_l,
            'perfil': perfil,
            'todas': sorted(set(incon) | set(consc)),
        }
    return jsonify(resultado)

def _validar_puertas(valores, campo, n=13):
    """Valida lista clásica de n puertas (13 en Agregar; n=None = cualquier
    cantidad no vacía, para Modificar personas con filas duplicadas/viejas).
    Acepta enteros 1-64 o decimales 'puerta.linea' (ej. '41.1'). Devuelve ([puertas], [lineas], error)."""
    if not isinstance(valores, list):
        return None, None, f'{campo}: se esperaba una lista de {n} puertas' if n else f'{campo}: se esperaba una lista de puertas'
    if n is not None and len(valores) != n:
        return None, None, f'{campo}: deben ser {n} puertas (recibidas {len(valores)})'
    if n is None and not valores:
        return None, None, f'{campo}: sin puertas'
    puertas, lineas = [], []
    for v in valores:
        try:
            if isinstance(v, bool):
                raise ValueError()
            s = str(v).strip()
            if '.' in s:
                ent, dec = s.split('.', 1)
                n = int(ent)
                l = int(dec.strip()) if dec.strip().isdigit() else None
                if l is not None and not 1 <= l <= 6:
                    return None, None, f'{campo}: línea fuera de rango en "{v}" (1-6)'
            else:
                n = int(float(s)) if isinstance(v, float) else int(s)
                if isinstance(v, float) and not float(v).is_integer():
                    raise ValueError()
                l = None
        except (ValueError, TypeError, AttributeError):
            return None, None, f'{campo}: valor inválido "{v}" (enteros 1-64 o puerta.línea 1-6)'
        if not 1 <= n <= 64:
            return None, None, f'{campo}: puerta fuera de rango "{n}" (1-64)'
        puertas.append(n)
        lineas.append(l)
    # Si se enviaron líneas por separado, tienen prioridad sobre el decimal.
    return puertas, lineas, None

def _validar_lineas(valores, campo):
    """Valida lista opcional de 13 líneas (1-6, vacías = desconocida). Devuelve (lista|None, error)."""
    if valores is None or valores == [] or valores == '':
        return None, None
    if not isinstance(valores, list):
        return None, f'{campo}: se esperaba una lista de 13 líneas'
    if len(valores) != 13:
        return None, f'{campo}: deben ser 13 líneas (recibidas {len(valores)})'
    out = []
    for v in valores:
        if v in (None, '', 'nan'):
            out.append(None)
            continue
        try:
            if isinstance(v, bool):
                raise ValueError()
            n = int(float(str(v).strip()))
        except (ValueError, TypeError, AttributeError):
            return None, f'{campo}: valor inválido "{v}" (líneas 1-6 o vacío)'
        if not 1 <= n <= 6:
            return None, f'{campo}: línea fuera de rango "{n}" (1-6)'
        out.append(n)
    return out, None

@app.route('/api/persona', methods=['POST'])
def api_agregar_persona():
    data = request.get_json(force=True, silent=True) or {}
    _ct = _cuenta_actual()
    if _ct:
        return _cuenta_persona_post(_ct, data)
    if _es_render():
        return jsonify({'error': 'Entrá a tu cuenta para guardar: en Render los datos se guardan en Neon.'}), 401
    nombre = str(data.get('nombre', '') or '').strip()
    if not nombre:
        return jsonify({'error': 'El nombre es obligatorio'}), 400
    if nombre in get_personas():
        return jsonify({'error': f'"{nombre}" ya existe'}), 409
    es_transito = bool(data.get('transito')) and not data.get('inconscientes')
    if es_transito:
        incon, incon_l = [], []
    else:
        incon, incon_l_dec, err = _validar_puertas(data.get('inconscientes'), 'Inconscientes')
        if err:
            return jsonify({'error': err}), 400
        incon_l, err = _validar_lineas(data.get('inconscientes_lineas'), 'Líneas inconscientes')
        if err:
            return jsonify({'error': err}), 400
        if incon_l is None:
            incon_l = incon_l_dec
        else:
            incon_l = [e if e is not None else d for e, d in zip(incon_l, incon_l_dec)]
    consc, consc_l_dec, err = _validar_puertas(data.get('conscientes'), 'Conscientes')
    if err:
        return jsonify({'error': err}), 400
    consc_l, err = _validar_lineas(data.get('conscientes_lineas'), 'Líneas conscientes')
    if err:
        return jsonify({'error': err}), 400
    if consc_l is None:
        consc_l = consc_l_dec
    else:
        consc_l = [e if e is not None else d for e, d in zip(consc_l, consc_l_dec)]
    hay_lineas = any(x is not None for x in (incon_l + consc_l))
    # Respetar la cabecera actual ('Nombre;Puerta;Linea;C/I'): se escribe
    # en el mismo orden y con los mismos nombres; si no hay columna de línea y
    # hay líneas para guardar, se agrega 'Linea' antes de C/I migrando las filas.
    try:
        with open(CSV_PATH, 'r', encoding='utf-8-sig') as f:
            cab = [c.strip() for c in f.readline().strip().split(';')]
        low_cab = [c.lower() for c in cab]
        idx = {
            'nombre': next((i for i, c in enumerate(low_cab) if c == 'nombre'), None),
            'puerta': next((i for i, c in enumerate(low_cab) if 'puerta' in c), None),
            'linea': next((i for i, c in enumerate(low_cab) if 'linea' in c.replace('í', 'i')), None),
            'ci': next((i for i, c in enumerate(low_cab) if c.replace(' ', '') in ('c/i', 'c-i', 'ci')), None),
        }
        if hay_lineas and idx['linea'] is None and idx['ci'] is not None:
            resto = open(CSV_PATH, 'r', encoding='utf-8-sig').read().splitlines()[1:]
            cab.insert(idx['ci'], 'Linea')
            with open(CSV_PATH, 'w', newline='', encoding='utf-8-sig') as f:
                f.write(';'.join(cab) + '\n')
                for lin in resto:
                    if lin.strip():
                        partes = lin.split(';')
                        if len(partes) == len(cab) - 1:
                            partes.insert(idx['ci'], '')
                            f.write(';'.join(partes) + '\n')
                        else:
                            f.write(lin + '\n')
            idx = {'nombre': idx['nombre'], 'puerta': idx['puerta'], 'linea': idx['ci'], 'ci': idx['ci'] + 1}
            _cache_invalidate(CSV_PATH)
        con_linea = hay_lineas
    except FileNotFoundError:
        cab = ['Nombre', 'Puerta', 'Linea', 'C/I'] if hay_lineas else ['Nombre', 'Puerta', 'C/I']
        with open(CSV_PATH, 'w', newline='', encoding='utf-8-sig') as f:
            f.write(';'.join(cab) + '\n')
        _cache_invalidate(CSV_PATH)
        low_cab = [c.lower() for c in cab]
        idx = {'nombre': 0, 'puerta': 1,
               'linea': 2 if hay_lineas else None,
               'ci': 3 if hay_lineas else 2}
        con_linea = hay_lineas
    def _fila(puerta, linea, estado):
        n = max((v for v in idx.values() if v is not None), default=-1) + 1
        fila = [''] * max(n, len(cab))
        fila[idx['nombre']] = nombre
        fila[idx['puerta']] = puerta
        if con_linea and idx['linea'] is not None:
            fila[idx['linea']] = linea if linea is not None else ''
        fila[idx['ci']] = estado
        return fila[:len(cab)]
    with open(CSV_PATH, 'a', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f, delimiter=';')
        for i, p in enumerate(incon):
            w.writerow(_fila(p, incon_l[i] if i < len(incon_l) else None, 'Inconsciente'))
        for i, p in enumerate(consc):
            w.writerow(_fila(p, consc_l[i] if i < len(consc_l) else None, 'Consciente'))
    _cache_invalidate(CSV_PATH)
    # Foto opcional de la persona (URL local o remota).
    if 'foto' in data:
        _f = str(data.get('foto') or '').strip()
        if _f:
            _guardar_foto_persona(nombre, _f)
        else:
            _borrar_foto_persona(nombre)
    # Vínculo opcional con otra persona -> vinculos.csv (referente + tipo).
    vinc_tipo = str(data.get('vinculo_tipo', '') or '').strip()
    vinc_ref = str(data.get('vinculo_referente', '') or '').strip()
    if vinc_tipo or vinc_ref:
        if not vinc_tipo or not vinc_ref:
            return jsonify({'error': 'Vínculo incompleto: elegir tipo y persona'}), 400
        _guardar_vinculo(nombre, vinc_ref, vinc_tipo,
                         fecha=str(data.get('fecha', '') or '').strip(),
                         hora=str(data.get('hora', '') or '').strip(),
                         lugar=str(data.get('lugar', '') or '').strip())
    elif str(data.get('fecha', '') or '').strip() or str(data.get('hora', '') or '').strip() or str(data.get('lugar', '') or '').strip():
        # Sin vínculo igual se guardan fecha/hora/lugar para poder modificarlos después.
        _anexar_fila_vinculo(nombre,
                             fecha=str(data.get('fecha', '') or '').strip(),
                             hora=str(data.get('hora', '') or '').strip(),
                             lugar=str(data.get('lugar', '') or '').strip())
    perfil = _perfil_de_lineas(consc_l[0] if consc_l else None, incon_l[0] if incon_l else None)
    return jsonify({'ok': True, 'nombre': nombre, 'personas': get_personas(), 'perfil': perfil}), 201

@app.route('/api/persona/<path:nombre>', methods=['PUT'])
def api_modificar_persona(nombre):
    """Modifica una persona existente: sustituye sus filas en datos.csv en la
    misma posición de la primera aparición y actualiza su fila en vinculos.csv."""
    viejo = str(nombre or '').strip()
    if not viejo:
        return jsonify({'error': 'Falta el nombre'}), 400
    data = request.get_json(force=True, silent=True) or {}
    _ct = _cuenta_actual()
    if _ct:
        return _cuenta_persona_put(_ct, nombre, data)
    nuevo = str(data.get('nombre', '') or '').strip() or viejo
    personas = get_personas()
    if viejo not in personas:
        return jsonify({'error': f'"{viejo}" no existe'}), 404
    if nuevo != viejo and nuevo in personas:
        return jsonify({'error': f'"{nuevo}" ya existe'}), 409
    incon, incon_l_dec, err = _validar_puertas(data.get('inconscientes'), 'Inconscientes', n=None)
    if err:
        return jsonify({'error': err}), 400
    incon_l, err = _validar_lineas(data.get('inconscientes_lineas'), 'Líneas inconscientes')
    if err:
        return jsonify({'error': err}), 400
    if incon_l is None:
        incon_l = incon_l_dec
    else:
        incon_l = [e if e is not None else d for e, d in zip(incon_l, incon_l_dec)]
    consc, consc_l_dec, err = _validar_puertas(data.get('conscientes'), 'Conscientes', n=None)
    if err:
        return jsonify({'error': err}), 400
    consc_l, err = _validar_lineas(data.get('conscientes_lineas'), 'Líneas conscientes')
    if err:
        return jsonify({'error': err}), 400
    if consc_l is None:
        consc_l = consc_l_dec
    else:
        consc_l = [e if e is not None else d for e, d in zip(consc_l, consc_l_dec)]
    hay_lineas = any(x is not None for x in (incon_l + consc_l))
    try:
        with open(CSV_PATH, 'r', encoding='utf-8-sig') as f:
            cab = [c.strip() for c in f.readline().strip().split(';')]
        low_cab = [c.lower() for c in cab]
        idx = {
            'nombre': next((i for i, c in enumerate(low_cab) if c == 'nombre'), None),
            'puerta': next((i for i, c in enumerate(low_cab) if 'puerta' in c), None),
            'linea': next((i for i, c in enumerate(low_cab) if 'linea' in c.replace('í', 'i')), None),
            'ci': next((i for i, c in enumerate(low_cab) if c.replace(' ', '') in ('c/i', 'c-i', 'ci')), None),
        }
        if hay_lineas and idx['linea'] is None and idx['ci'] is not None:
            resto = open(CSV_PATH, 'r', encoding='utf-8-sig').read().splitlines()[1:]
            cab.insert(idx['ci'], 'Linea')
            with open(CSV_PATH, 'w', newline='', encoding='utf-8-sig') as f:
                f.write(';'.join(cab) + '\n')
                for lin in resto:
                    if lin.strip():
                        partes = lin.split(';')
                        if len(partes) == len(cab) - 1:
                            partes.insert(idx['ci'], '')
                            f.write(';'.join(partes) + '\n')
                        else:
                            f.write(lin + '\n')
            idx = {'nombre': idx['nombre'], 'puerta': idx['puerta'], 'linea': idx['ci'], 'ci': idx['ci'] + 1}
            _cache_invalidate(CSV_PATH)
        con_linea = hay_lineas
    except FileNotFoundError:
        return jsonify({'error': 'Sin datos'}), 404
    if idx.get('nombre') is None or idx.get('puerta') is None or idx.get('ci') is None:
        return jsonify({'error': 'Cabecera de datos.csv no reconocida'}), 500
    def _fila(puerta, linea, estado):
        n = max((v for v in idx.values() if v is not None), default=-1) + 1
        fila = [''] * max(n, len(cab))
        fila[idx['nombre']] = nuevo
        fila[idx['puerta']] = puerta
        if con_linea and idx['linea'] is not None:
            fila[idx['linea']] = linea if linea is not None else ''
        fila[idx['ci']] = estado
        return fila[:len(cab)]
    nuevas = ([_fila(p, incon_l[i] if i < len(incon_l) else None, 'Inconsciente') for i, p in enumerate(incon)]
              + [_fila(p, consc_l[i] if i < len(consc_l) else None, 'Consciente') for i, p in enumerate(consc)])
    try:
        with open(CSV_PATH, 'r', encoding='utf-8-sig', newline='') as f:
            lector = csv.reader(f, delimiter=';')
            filas = [r for r in lector]
    except FileNotFoundError:
        return jsonify({'error': 'Sin datos'}), 404
    if not filas:
        return jsonify({'error': 'Sin datos'}), 404
    cab_leida = filas[0]
    cuerpo = [r for r in filas[1:] if any(str(c or '').strip() for c in r)]
    pos = [i for i, r in enumerate(cuerpo)
           if len(r) > (idx['nombre'] or 0) and str(r[idx['nombre']] or '').strip() == viejo]
    if not pos:
        return jsonify({'error': f'"{viejo}" no existe'}), 404
    primera = pos[0]
    cuerpo = [r for i, r in enumerate(cuerpo) if i not in set(pos)]
    for k, nr in enumerate(nuevas):
        cuerpo.insert(min(primera + k, len(cuerpo)), nr)
    with open(CSV_PATH, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f, delimiter=';')
        w.writerow(cab_leida)
        w.writerows(cuerpo)
    _cache_invalidate(CSV_PATH)
    # Vinculos: actualiza fecha/hora/lugar y renombre (nombre + referentes).
    # Si la persona no tiene fila y hay datos, se crea para no perderlos.
    try:
        fecha = str(data.get('fecha', '') or '').strip()
        hora = str(data.get('hora', '') or '').strip()
        lugar = str(data.get('lugar', '') or '').strip()
        vt = str(data.get('vinculo_tipo', '') or '').strip()
        vr = str(data.get('vinculo_referente', '') or '').strip()
        toca_vinc = ('fecha' in data) or ('hora' in data) or ('lugar' in data) or bool(vt or vr) or (nuevo != viejo)
        hay_datos = bool(fecha or hora or lugar or (vt and vr))
        if toca_vinc and VINCULOS_PATH.exists():
            sep = ';'
            with open(VINCULOS_PATH, 'r', encoding='utf-8-sig', newline='') as f:
                muestra = f.read(4096)
                if muestra.count('\t') > muestra.count(';'):
                    sep = '\t'
            with open(VINCULOS_PATH, 'r', encoding='utf-8-sig', newline='') as f:
                lector = csv.reader(f, delimiter=sep)
                vfilas = [r for r in lector]
            if vfilas:
                vhead = vfilas[0]
                mapa = _cols_vinculos(pd.DataFrame(columns=vhead))
                # mapa trae NOMBRES de columna -> pasar a índices posicionales.
                pos = {k: (vhead.index(v) if v in vhead else None) for k, v in mapa.items()}
                vcuerpo = vfilas[1:]
                vl = viejo.strip().lower()
                coincidio = False
                for r in vcuerpo:
                    def _get(col):
                        return str(r[col] or '').strip() if col is not None and col < len(r) else ''
                    def _set(col, val):
                        if col is not None:
                            while len(r) <= col:
                                r.append('')
                            r[col] = val
                    if pos.get('nombre') is not None and _get(pos['nombre']).lower() == vl:
                        coincidio = True
                        _set(pos['nombre'], nuevo)
                        if 'fecha' in data and pos.get('fecha') is not None:
                            _set(pos['fecha'], fecha)
                        if 'hora' in data and pos.get('hora') is not None:
                            _set(pos['hora'], hora)
                        if 'lugar' in data and pos.get('lugar') is not None:
                            _set(pos['lugar'], lugar)
                        if vt and pos.get('vinculo') is not None:
                            _set(pos['vinculo'], vt)
                        if vr and pos.get('referente') is not None:
                            _set(pos['referente'], vr)
                    elif pos.get('referente') is not None and _get(pos['referente']).lower() == vl:
                        _set(pos['referente'], nuevo)
                with open(VINCULOS_PATH, 'w', newline='', encoding='utf-8-sig') as f:
                    w = csv.writer(f, delimiter=sep)
                    w.writerow(vhead)
                    w.writerows(vcuerpo)
                _cache_invalidate(VINCULOS_PATH)
                if not coincidio and hay_datos:
                    _anexar_fila_vinculo(nuevo, fecha=fecha, hora=hora, lugar=lugar,
                                         referente=vr if (vt and vr) else '',
                                         vinculo_tipo=vt if (vt and vr) else '')
        elif toca_vinc and hay_datos:
            _anexar_fila_vinculo(nuevo, fecha=fecha, hora=hora, lugar=lugar,
                                 referente=vr if (vt and vr) else '',
                                 vinculo_tipo=vt if (vt and vr) else '')
    except Exception:
        pass
    # Renombre: propaga el nombre nuevo a los CSV asociados para no dejar huérfanos.
    if nuevo != viejo:
        _renombrar_en_csv(TEST_CSV_PATH, viejo, nuevo, ('nombre',))
        _renombrar_en_csv(CLAN_PATH, viejo, nuevo, ('P1', 'p1', 'familiar'))
        _renombrar_en_csv(CONOCIDOS_PATH, viejo, nuevo, ('p1', 'P1'))
        _renombrar_en_csv(IA_CSV_PATH, viejo, nuevo, ('nombre',))
        _renombrar_en_csv(INFORME_CSV_PATH, viejo, nuevo, ('nombre',))
    if 'foto' in data:
        if nuevo != viejo:
            _borrar_foto_persona(viejo)
        _f = str(data.get('foto') or '').strip()
        if _f:
            _guardar_foto_persona(nuevo, _f)
        else:
            _borrar_foto_persona(nuevo)
    perfil = _perfil_de_lineas(consc_l[0] if consc_l else None, incon_l[0] if incon_l else None)
    return jsonify({'ok': True, 'nombre': nuevo, 'personas': get_personas(), 'perfil': perfil})

@app.route('/api/persona/<path:nombre>', methods=['DELETE'])
def api_eliminar_persona(nombre):
    """Elimina a la persona de datos.csv, vinculos.csv, test.csv y clan.csv.

    Referencias de terceros hacia ella se limpian (referente+vínculo vacíos,
    conservando sus propios datos). No se puede deshacer (respaldar antes)."""
    viejo = str(nombre or '').strip()
    if not viejo:
        return jsonify({'error': 'Falta el nombre'}), 400
    _ct = _cuenta_actual()
    if _ct:
        n = _auth.borrar_perfil(_ct['id'], viejo)
        if not n:
            return jsonify({'error': f'"{viejo}" no existe'}), 404
        g.perfiles_cuenta = None
        return jsonify({'ok': True, 'nombre': viejo, 'filas_datos': n, 'filas_vinculos': 0,
                        'referencias_limpiadas': 0, 'filas_test': 0, 'filas_clan': 0,
                        'filas_ia': 0, 'personas': get_personas()})
    if _es_render():
        return jsonify({'error': 'Entrá a tu cuenta: en Render los datos viven en Neon.'}), 401
    if viejo not in get_personas():
        return jsonify({'error': f'"{viejo}" no existe'}), 404
    eliminadas = 0
    try:
        with open(CSV_PATH, 'r', encoding='utf-8-sig', newline='') as f:
            filas = [r for r in csv.reader(f, delimiter=';')]
        if filas:
            cab = [str(c or '').strip().lower() for c in filas[0]]
            inombre = next((i for i, c in enumerate(cab) if c == 'nombre'), None)
            if inombre is None:
                return jsonify({'error': 'Cabecera de datos.csv no reconocida'}), 500
            cuerpo = [r for r in filas[1:] if not (inombre < len(r) and str(r[inombre] or '').strip() == viejo)]
            eliminadas = sum(1 for r in filas[1:] if inombre < len(r) and str(r[inombre] or '').strip() == viejo)
            with open(CSV_PATH, 'w', newline='', encoding='utf-8-sig') as f:
                w = csv.writer(f, delimiter=';')
                w.writerow(filas[0])
                w.writerows(cuerpo)
            _cache_invalidate(CSV_PATH)
    except FileNotFoundError:
        return jsonify({'error': 'Sin datos'}), 404
    vinc_borrados, refs_limpias = 0, 0
    try:
        if VINCULOS_PATH.exists():
            sep = ';'
            with open(VINCULOS_PATH, 'r', encoding='utf-8-sig', newline='') as f:
                muestra = f.read(4096)
                if muestra.count('\t') > muestra.count(';'):
                    sep = '\t'
            with open(VINCULOS_PATH, 'r', encoding='utf-8-sig', newline='') as f:
                vfilas = [r for r in csv.reader(f, delimiter=sep)]
            if vfilas:
                vhead = vfilas[0]
                mapa = _cols_vinculos(pd.DataFrame(columns=vhead))
                pos = {k: (vhead.index(v) if v in vhead else None) for k, v in mapa.items()}
                vl = viejo.strip().lower()
                resto = []
                for r in vfilas[1:]:
                    def _get(col):
                        return str(r[col] or '').strip() if col is not None and col < len(r) else ''
                    if pos.get('nombre') is not None and _get(pos['nombre']).lower() == vl:
                        vinc_borrados += 1
                        continue
                    if pos.get('referente') is not None and _get(pos['referente']).lower() == vl:
                        while len(r) <= max(pos['referente'], pos.get('vinculo') if pos.get('vinculo') is not None else 0):
                            r.append('')
                        r[pos['referente']] = ''
                        if pos.get('vinculo') is not None:
                            r[pos['vinculo']] = ''
                        refs_limpias += 1
                    resto.append(r)
                with open(VINCULOS_PATH, 'w', newline='', encoding='utf-8-sig') as f:
                    w = csv.writer(f, delimiter=sep)
                    w.writerow(vhead)
                    w.writerows(resto)
                _cache_invalidate(VINCULOS_PATH)
    except Exception:
        pass
    test_borrados = _borrar_test(viejo)
    clan_borrados = _borrar_clan(viejo)
    ia_borrados = _borrar_ia(viejo)
    _borrar_foto_persona(viejo)
    with _IA_LOCK:
        _IA_EN_PROCESO.discard(viejo.lower())
    return jsonify({'ok': True, 'nombre': viejo, 'filas_datos': eliminadas,
                    'filas_vinculos': vinc_borrados, 'referencias_limpiadas': refs_limpias,
                    'filas_test': test_borrados, 'filas_clan': clan_borrados,
                    'filas_ia': ia_borrados,
                    'personas': get_personas()})

def _test_de(nombre):
    """Test de autoconocimiento: de Neon si hay cuenta, si no de test.csv."""
    perfiles = _perfiles_cuenta_actual()
    if perfiles is not None:
        clave = str(nombre or '').strip().lower()
        for p in perfiles:
            if str(p.get('nombre') or '').strip().lower() == clave:
                t = _dj(p).get('test') or {}
                return t if isinstance(t, dict) else {}
        return {}
    return _leer_test(nombre) or {}


def _datos_persona(nombre):
    df = cargar_datos()
    datos_persona = df[df['Nombre'] == nombre].copy()

    if datos_persona.empty:
        return None


@app.route('/api/personas_batch', methods=['POST'])
def api_personas_batch():
    try:
        data = request.get_json(force=True, silent=True) or {}
    except Exception:
        return jsonify({'error': 'JSON invalido'}), 400
    nombres = data.get('personas') or data.get('nombres') or []
    if isinstance(nombres, str):
        nombres = [nombres]
    nombres = [str(n or '').strip() for n in (nombres or []) if str(n or '').strip()][:60]
    out = {}
    try:
        df_all = cargar_datos()
    except Exception:
        df_all = None
    for n in nombres:
        try:
            d = _datos_persona_dict(n, _df=df_all)
            out[n] = d if d else {'error': 'Persona no encontrada'}
        except Exception as e:
            out[n] = {'error': str(e)}
    return jsonify(out)


def _datos_persona_dict(nombre, _df=None):
    df = _df if _df is not None else cargar_datos()
    datos_persona = df[df['Nombre'] == nombre].copy()

    if datos_persona.empty:
        return None

    inconscientes, conscientes = [], []
    inconscientes_lineas, conscientes_lineas = [], []

    for _, row in datos_persona.iterrows():
        puerta = int(row['Puerta'])
        linea = None if pd.isna(row.get('Linea')) else int(row.get('Linea'))
        estado = str(row['C/I']).strip().lower()

        if estado == 'inconsciente':
            inconscientes.append(puerta)
            inconscientes_lineas.append(linea)
        else:
            conscientes.append(puerta)
            conscientes_lineas.append(linea)

    set_inconscientes = set(inconscientes)
    set_conscientes = set(conscientes)
    puertas_mixtas = sorted(set_inconscientes & set_conscientes)
    todas_puertas = sorted(set_inconscientes | set_conscientes)
    perfil = _perfil_de_lineas(conscientes_lineas[0] if conscientes_lineas else None,
                               inconscientes_lineas[0] if inconscientes_lineas else None)

    return {
        'puertas_inconscientes': inconscientes,
        'puertas_conscientes': conscientes,
        'inconscientes_lineas': inconscientes_lineas,
        'conscientes_lineas': conscientes_lineas,
        'perfil': perfil,
        'puertas_mixtas': puertas_mixtas,
        'todas_puertas': todas_puertas,
        'foto': _foto_persona_para(nombre)
    }


@app.route('/api/persona/<nombre>')
def get_persona_data(nombre):
    d = _datos_persona_dict(nombre)
    if not d:
        return jsonify({'error': 'Persona no encontrada'}), 404
    # S/NS: solo hay emojis Ser/No-Ser si el cuestionario está respondido.
    try:
        _t = _test_de(nombre)
        d['tiene_sns'] = bool(str(_t.get('sernoser_resp') or '').strip().strip('|'))
    except Exception:
        d['tiene_sns'] = False
    return jsonify(d)

@app.route('/api/persona_completa/<path:nombre>')
def get_persona_completa(nombre):
    """Todos los datos de entrada de una persona en una sola llamada (Cargar P1).

    Une puertas (datos.csv), nacimiento/vínculo/bio (vinculos.csv) y test
    (test.csv). El nacimiento se completa por campo: si falta en vinculos.csv
    se toma de test.csv (y viceversa)."""
    nombre = str(nombre or '').strip()
    if not nombre:
        return jsonify({'error': 'Falta el nombre'}), 400
    d = _datos_persona_dict(nombre)
    if not d:
        return jsonify({'error': 'Persona no encontrada'}), 404
    clave = nombre.lower()
    propias = [v for v in cargar_vinculos()
               if str(v.get('nombre') or '').strip().lower() == clave]

    def _punt(x):
        return sum(1 for k in ('fecha', 'hora', 'lugar') if str(x.get(k) or '').strip())

    vinc = {}
    for v in propias:
        if not vinc or _punt(v) > _punt(vinc):
            vinc = v
    vinc_tipo, vinc_ref, bio = '', '', ''
    for v in propias:
        if not (vinc_tipo and vinc_ref):
            t = str(v.get('vinc_ref') or '').strip()
            r = str(v.get('referente') or '').strip()
            if t and r:
                vinc_tipo, vinc_ref = t, r
        if not bio:
            bio = str(v.get('bio') or '').strip()

    test = _test_de(nombre)
    fecha = str(vinc.get('fecha') or '').strip() or str(test.get('fecha') or '').strip()
    hora = str(vinc.get('hora') or '').strip() or str(test.get('hora') or '').strip()
    lugar = str(vinc.get('lugar') or '').strip() or str(test.get('lugar') or '').strip()
    foto = ''
    _ct = _cuenta_actual()
    if _ct:
        for _p in (_perfiles_cuenta_actual() or []):
            if str(_p.get('nombre') or '').strip().lower() == nombre.lower():
                foto = str(_p.get('foto') or '').strip() or str(_dj(_p).get('foto') or '').strip()
                break
    if not foto:
        foto = _cargar_fotos_personas().get(nombre.lower(), '')
    return jsonify({
        'nombre': nombre,
        'fecha': fecha,
        'hora': hora,
        'lugar': lugar,
        'lat': '',
        'lon': '',
        'tz': '',
        'foto': foto,
        'bio': bio,
        'puertas_inconscientes': d.get('puertas_inconscientes', []),
        'puertas_conscientes': d.get('puertas_conscientes', []),
        'inconscientes_lineas': d.get('inconscientes_lineas', []),
        'conscientes_lineas': d.get('conscientes_lineas', []),
        'perfil': d.get('perfil'),
        'vinculo_tipo': vinc_tipo,
        'vinculo_referente': vinc_ref,
        'test': test,
    })

def load_gate_info():
    # Cacheado por mtime de razgos.xlsx (evita pd.read_excel en cada request)
    try:
        _mtime = Path('razgos.xlsx').stat().st_mtime
    except FileNotFoundError:
        _mtime = None
    if _CACHE_GATE['mtime'] == _mtime and _CACHE_GATE['val'] is not None:
        return _CACHE_GATE['val']
    # Load razgos.xlsx: real headers are on row 3 (0-indexed)
    df = pd.read_excel('razgos.xlsx', header=3)
    # Find gate number column
    gate_col = None
    for col in df.columns:
        if 'Puerta' in str(col):
            gate_col = col
            break
    if not gate_col:
        return {}
    gate_info = {}
    for _, row in df.iterrows():
        try:
            gate_num = int(row[gate_col])
        except (ValueError, TypeError):
            continue
        info = {
            'nombre':          str(row.get('Nombre de la Puerta', '') or '').strip(),
            'concepto':        str(row.get('Concepto Clave', '') or '').strip(),
            'centro':          str(row.get('Centro', '') or '').strip(),
            'circuito':        str(row.get('Circuito / Grupo', '') or '').strip(),
            'caracteristicas': str(row.get('Características de la Persona', '') or '').strip(),
            'miedos':          str(row.get('Miedos y Ansiedades', '') or '').strip(),
            'dinamica_amor':   str(row.get('Dinámica del Amor (Anexo)', '') or '').strip(),
        }
        # Remove empty / nan entries
        gate_info[gate_num] = {k: v for k, v in info.items()
                               if v and v.lower() != 'nan'}
    _CACHE_GATE['mtime'] = _mtime
    _CACHE_GATE['val'] = gate_info
    return gate_info

@app.route('/api/gate_info')
def api_gate_info():
    info = load_gate_info()
    return jsonify(info)

_CACHE_SERNOSER = {'mtime': None, 'val': None}

@app.route('/api/sernoser_puertas')
def api_sernoser_puertas():
    """Preguntas NoSer por puerta desde sernoser_puertas.csv (';' como resto de CSV RAVE: puerta;pregunta_noser)."""
    import csv as _csv
    from pathlib import Path as _Path
    p = _Path('sernoser_puertas.csv')
    try:
        mt = p.stat().st_mtime
    except FileNotFoundError:
        return jsonify({'error': 'falta sernoser_puertas.csv'}), 404
    if _CACHE_SERNOSER['mtime'] == mt and _CACHE_SERNOSER['val'] is not None:
        return jsonify(_CACHE_SERNOSER['val'])
    out = {}
    with open(p, encoding='utf-8-sig') as f:
        for row in _csv.DictReader(f, delimiter=';'):
            try:
                g = int(str(row.get('puerta') or '').strip())
            except (ValueError, TypeError):
                continue
            q = str(row.get('pregunta_noser') or '').strip()
            if q:
                out[g] = q
    _CACHE_SERNOSER['mtime'] = mt
    _CACHE_SERNOSER['val'] = out
    return jsonify(out)
_CACHE_SERNOSER_EMO = {'mtime': None, 'val': None}

@app.route('/api/sernoser_emojis')
def api_sernoser_emojis():
    """Emojis por estado desde sernoser_emojis.csv (; puerta;concepto;emoji_noser;estado_noser;estado_normal;emoji_maestria;estado_maestria)."""
    import csv as _csv
    from pathlib import Path as _Path
    p = _Path('sernoser_emojis.csv')
    try:
        mt = p.stat().st_mtime
    except FileNotFoundError:
        return jsonify({'error': 'falta sernoser_emojis.csv'}), 404
    if _CACHE_SERNOSER_EMO['mtime'] == mt and _CACHE_SERNOSER_EMO['val'] is not None:
        return jsonify(_CACHE_SERNOSER_EMO['val'])
    out = {}
    with open(p, encoding='utf-8-sig') as f:
        for row in _csv.DictReader(f, delimiter=';'):
            try:
                g = int(str(row.get('puerta') or '').strip())
            except (ValueError, TypeError):
                continue
            out[g] = {k: str(row.get(k) or '').strip() for k in
                      ('concepto', 'emoji_noser', 'estado_noser', 'emoji_normal', 'estado_normal',
                       'emoji_maestria', 'estado_maestria')}
    _CACHE_SERNOSER_EMO['mtime'] = mt
    _CACHE_SERNOSER_EMO['val'] = out
    return jsonify(out)

_PUERTA_CENTRO_SN = {64:'Corona',61:'Corona',63:'Corona',47:'Ajna',24:'Ajna',4:'Ajna',17:'Ajna',43:'Ajna',11:'Ajna',62:'Garganta',23:'Garganta',56:'Garganta',35:'Garganta',12:'Garganta',45:'Garganta',33:'Garganta',8:'Garganta',20:'Garganta',31:'Garganta',16:'Garganta',7:'G',1:'G',13:'G',10:'G',25:'G',15:'G',46:'G',2:'G',21:'Ego',40:'Ego',26:'Ego',51:'Ego',48:'Bazo',57:'Bazo',44:'Bazo',50:'Bazo',32:'Bazo',28:'Bazo',18:'Bazo',36:'Plexo',22:'Plexo',37:'Plexo',49:'Plexo',30:'Plexo',55:'Plexo',6:'Plexo',5:'Sacro',14:'Sacro',29:'Sacro',59:'Sacro',9:'Sacro',3:'Sacro',42:'Sacro',27:'Sacro',34:'Sacro',53:'Raiz',60:'Raiz',52:'Raiz',19:'Raiz',39:'Raiz',41:'Raiz',58:'Raiz',38:'Raiz',54:'Raiz'}

@app.route('/api/puerta_centro')
def api_puerta_centro():
    """Mapa puerta -> centro (para agrupar preguntas Ser/NoSer sin guardar el centro en el CSV)."""
    return jsonify(_PUERTA_CENTRO_SN)


# ---------- Preguntas IA (cuadro de texto flotante en index) ----------
# Proveedores: groq (nube rápida, gratis), gemini, cerebras, openrouter, ollama (local).
# Configuración por variables de entorno (.env local o Render -> Environment):
#   IA_PROVIDER = groq | gemini | cerebras | openrouter | ollama (vacío = auto por keys)
#   IA_MODEL    = override del modelo del proveedor elegido
#   IA_TIMEOUT  = segundos por proveedor (default: 30 nube, 120 ollama local)
#   IA_RACE_TIMEOUT = tope total de la carrera entre proveedores (default 60)
#   IA_RACE=0     = secuencial en vez de carrera (prueba en orden hasta que uno responde)
#   GROQ_API_KEY      (gratis en https://console.groq.com/keys, rapidísimo)
#   GEMINI_API_KEY    (https://aistudio.google.com/apikey)
#   CEREBRAS_API_KEY / OPENROUTER_API_KEY / OLLAMA_HOST (default http://localhost:11434)
# Sin key del proveedor, /api/ia_estado devuelve configurado=false.
_IA_PROVEEDORES = {
    'groq': {'base': 'https://api.groq.com/openai/v1', 'key_env': 'GROQ_API_KEY',
             'model_env': 'GROQ_MODEL', 'default_model': 'openai/gpt-oss-20b',
             'fallbacks': ['qwen/qwen3.6-27b', 'openai/gpt-oss-120b',
                           'moonshotai/kimi-k2-instruct']},
    'cerebras': {'base': 'https://api.cerebras.ai/v1', 'key_env': 'CEREBRAS_API_KEY',
                 'model_env': 'CEREBRAS_MODEL', 'default_model': 'llama3.1-8b',
                 'fallbacks': ['llama-3.3-70b']},
    'openrouter': {'base': 'https://openrouter.ai/api/v1', 'key_env': 'OPENROUTER_API_KEY',
                   'model_env': 'OPENROUTER_MODEL',
                   'default_model': 'meta-llama/llama-3.3-70b-instruct:free',
                   'fallbacks': []},
    'ollama': {'base': None, 'key_env': None, 'model_env': 'OLLAMA_MODEL',
               'default_model': 'llama3.1:8b', 'fallbacks': []},
}


def _ia_config(prov_pedido=None):
    prov = (prov_pedido or os.environ.get('IA_PROVIDER') or '').strip().lower()
    if prov not in ('groq', 'gemini', 'cerebras', 'openrouter', 'ollama'):
        # Auto: primer proveedor con key configurada (groq primero = más rápido).
        prov = ''
        for cand in ('groq', 'gemini', 'cerebras', 'openrouter'):
            spec = _IA_PROVEEDORES.get(cand, {})
            ke = spec.get('key_env')
            if cand == 'gemini':
                if (os.environ.get('GEMINI_API_KEY') or '').strip():
                    prov = cand
                    break
            elif ke and (os.environ.get(ke) or '').strip():
                prov = cand
                break
        if not prov:
            prov = 'ollama'
    if prov == 'gemini':
        model = (os.environ.get('IA_MODEL') or os.environ.get('GEMINI_MODEL')
                 or 'gemini-3.6-flash').strip() or 'gemini-3.6-flash'
        api_key = (os.environ.get('GEMINI_API_KEY') or '').strip()
        timeout_s = int(os.environ.get('IA_TIMEOUT') or 10)
        return {'proveedor': prov, 'api_key': api_key, 'model': model,
                'timeout_s': timeout_s, 'configurado': bool(api_key)}
    spec = _IA_PROVEEDORES[prov]
    api_key = (os.environ.get(spec['key_env']) or '').strip() if spec['key_env'] else ''
    model = ((os.environ.get('IA_MODEL') or os.environ.get(spec['model_env'])
              or spec['default_model']).strip() or spec['default_model'])
    timeout_s = int(os.environ.get('IA_TIMEOUT') or (120 if prov == 'ollama' else 30))
    if prov == 'ollama':
        base = (os.environ.get('OLLAMA_HOST') or 'http://localhost:11434').strip().rstrip('/')
        return {'proveedor': prov, 'api_key': '', 'model': model, 'base': base,
                'timeout_s': timeout_s, 'configurado': True}
    return {'proveedor': prov, 'api_key': api_key, 'model': model, 'base': spec['base'],
            'timeout_s': timeout_s, 'configurado': bool(api_key)}


@app.route('/api/ia_estado')
def api_ia_estado():
    cfg = _ia_config()
    disp = [{'id': c['proveedor'], 'model': c['model']} for c in _candidatos_ia()]
    return jsonify({'proveedor': cfg['proveedor'], 'configurado': cfg['configurado'],
                    'model': cfg['model'], 'timeout_s': cfg['timeout_s'],
                    'proveedores_disponibles': disp})


@app.route('/api/ia_base')
def api_ia_base():
    try:
        _txt = Path(__file__).with_name('base_informe_ia.txt').read_text(encoding='utf-8', errors='replace')[:8000]
    except Exception:
        _txt = ''
    return jsonify({'base': _txt})


@app.route('/api/ia_modelos')
def api_ia_modelos():
    """Lista modelos disponibles para el proveedor configurado (diagnóstico)."""
    cfg = _ia_config()
    if cfg['proveedor'] == 'gemini':
        if not cfg['api_key']:
            return jsonify({'error': 'Sin GEMINI_API_KEY.'}), 503
        url = f'https://generativelanguage.googleapis.com/v1beta/models?key={_urlparse.quote(cfg["api_key"])}'
        try:
            req = _urlrequest.Request(url, headers=_GEO_UA)
            with _urlrequest.urlopen(req, timeout=20) as resp:
                data = _json.loads(resp.read().decode('utf-8', 'replace'))
        except Exception as e:
            detalle = str(e)
            try:
                detalle = e.read().decode('utf-8', 'replace')[:300] or detalle
            except Exception:
                pass
            return jsonify({'error': detalle}), 502
        nombres = []
        for m in (data.get('models') or []):
            n = str(m.get('name') or '').replace('models/', '')
            metodos = m.get('supportedGenerationMethods') or []
            if 'generateContent' in metodos:
                nombres.append(n)
        return jsonify({'proveedor': 'gemini', 'modelos': sorted(nombres), 'default': cfg['model']})
    # Proveedores OpenAI-compatibles (groq/cerebras/openrouter/ollama): GET /models.
    headers = dict(_GEO_UA)
    if cfg['api_key']:
        headers['Authorization'] = f"Bearer {cfg['api_key']}"
    if cfg['proveedor'] == 'openrouter':
        headers['HTTP-Referer'] = 'http://localhost:5000/'
        headers['X-Title'] = 'DisenioHumano'
    try:
        req = _urlrequest.Request(f"{cfg['base']}/models", headers=headers)
        with _urlrequest.urlopen(req, timeout=20) as resp:
            data = _json.loads(resp.read().decode('utf-8', 'replace'))
    except Exception as e:
        detalle = str(e)
        try:
            detalle = e.read().decode('utf-8', 'replace')[:300] or detalle
        except Exception:
            pass
        return jsonify({'error': detalle}), 502
    nombres = sorted(str(m.get('id') or '') for m in (data.get('data') or []) if m.get('id'))
    return jsonify({'proveedor': cfg['proveedor'], 'modelos': nombres, 'default': cfg['model']})


def _chat_openai_compat(cfg, model, system_txt, contexto_txt, pregunta, historial, max_tokens=1024):
    """Chat contra API OpenAI-compatible (groq/cerebras/openrouter/ollama). Devuelve texto."""
    mensajes = [{'role': 'system', 'content': system_txt}]
    if contexto_txt:
        mensajes.append({'role': 'user', 'content':
                         f'CONTEXTO DE DISEÑO HUMANO (datos visibles en pantalla):\n{contexto_txt[:12000]}'})
    if historial and isinstance(historial, list):
        for m in historial[-6:]:
            if isinstance(m, dict) and str(m.get('texto') or '').strip():
                mensajes.append({'role': 'user' if m.get('rol') == 'user' else 'assistant',
                                 'content': str(m.get('texto'))[:1000]})
    mensajes.append({'role': 'user', 'content': pregunta})
    body = {'model': model, 'messages': mensajes, 'temperature': 0.7, 'max_tokens': max_tokens}
    headers = {'Content-Type': 'application/json', **_GEO_UA}
    if cfg['api_key']:
        headers['Authorization'] = f"Bearer {cfg['api_key']}"
    if cfg['proveedor'] == 'openrouter':
        headers['HTTP-Referer'] = 'http://localhost:5000/'
        headers['X-Title'] = 'DisenioHumano'
    req = _urlrequest.Request(f"{cfg['base']}/chat/completions",
                              data=_json.dumps(body).encode('utf-8'),
                              headers=headers, method='POST')
    try:
        with _urlrequest.urlopen(req, timeout=cfg['timeout_s']) as resp:
            data = _json.loads(resp.read().decode('utf-8', 'replace'))
    except Exception as e:
        detalle = str(e)
        codigo = None
        try:
            body_err = e.read().decode('utf-8', 'replace')
            codigo = getattr(e, 'code', None)
            try:
                dj = _json.loads(body_err)
                detalle = ((dj.get('error') or {}).get('message')) or body_err[:300]
            except Exception:
                detalle = body_err[:300] or detalle
        except Exception:
            pass
        raise RuntimeError(f'{cfg["proveedor"]}/{model}: {detalle}', codigo)
    try:
        txt = (data['choices'][0]['message'].get('content') or '').strip()
        if txt:
            return txt
        return f'Sin respuesta de la IA (revisar modelo {model}). Detalle: {str(data)[:300]}'
    except (IndexError, KeyError, TypeError, AttributeError):
        if isinstance(data, dict) and data.get('error'):
            err = data['error']
            raise RuntimeError(f'{cfg["proveedor"]}/{model}: {err.get("message", err)}', None)
        raise RuntimeError(f'Respuesta inesperada de {cfg["proveedor"]}: {str(data)[:300]}', None)


def _llamar_gemini(api_key, model, system_txt, contexto_txt, pregunta, historial, max_tokens=1024):
    """Llama a Gemini con stdlib (sin dependencias nuevas). Devuelve texto."""
    model = (_re.sub(r'[^a-zA-Z0-9._-]', '', model or '') or 'gemini-3.6-flash')
    url = f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={_urlparse.quote(api_key)}'
    partes = []
    if contexto_txt:
        partes.append(f'CONTEXTO DE DISEÑO HUMANO (datos visibles en pantalla):\n{contexto_txt[:12000]}')
    if historial and isinstance(historial, list):
        hist_txt = '\n'.join(
            f"{'Usuario' if (m.get('rol') == 'user') else 'IA'}: {str(m.get('texto') or '')[:1000]}"
            for m in historial[-6:] if isinstance(m, dict)
        )
        if hist_txt:
            partes.append(f'HISTORIAL RECIENTE:\n{hist_txt}')
    partes.append(f'PREGUNTA ACTUAL:\n{pregunta}')
    body = {
        'system_instruction': {'parts': [{'text': system_txt}]},
        'contents': [{'role': 'user', 'parts': [{'text': '\n\n---\n\n'.join(partes)}]}],
        'generationConfig': {'temperature': 0.7, 'maxOutputTokens': max_tokens},
    }
    req = _urlrequest.Request(
        url, data=_json.dumps(body).encode('utf-8'),
        headers={'Content-Type': 'application/json', **_GEO_UA}, method='POST')
    try:
        with _urlrequest.urlopen(req, timeout=10) as resp:
            data = _json.loads(resp.read().decode('utf-8', 'replace'))
    except Exception as e:
        # Leer el cuerpo del HTTPError: Google explica el motivo real
        # (ej. "models/xxx is not found for API version v1beta").
        detalle = str(e)
        try:
            body_err = e.read().decode('utf-8', 'replace')
            try:
                dj = _json.loads(body_err)
                detalle = ((dj.get('error') or {}).get('message')) or body_err[:300]
            except Exception:
                detalle = body_err[:300] or detalle
        except Exception:
            pass
        raise RuntimeError(f'Error llamando a Gemini ({model}): {detalle}')
    try:
        cands = data.get('candidates') or []
        parts = (cands[0].get('content') or {}).get('parts') or []
        txt = ''.join(p.get('text', '') for p in parts).strip()
        if txt:
            return txt
        return f'Sin respuesta de la IA (revisar modelo {model}). Detalle: {str(data)[:300]}'
    except (IndexError, AttributeError, KeyError):
        if data.get('error'):
            raise RuntimeError(f"Gemini: {data['error'].get('message', data['error'])}")
        raise RuntimeError(f'Respuesta inesperada de Gemini: {str(data)[:300]}')


def _candidatos_ia(prov_pedido=None):
    """Configs a probar en orden: pedido (o auto) primero, luego el resto configurado."""
    orden = []
    primero = (prov_pedido or '').strip().lower()
    if primero not in ('groq', 'gemini', 'cerebras', 'openrouter', 'ollama'):
        primero = _ia_config()['proveedor']
    orden.append(primero)
    for cand in ('groq', 'gemini', 'cerebras', 'openrouter', 'ollama'):
        if cand not in orden and _ia_config(cand)['configurado']:
            orden.append(cand)
    return [_ia_config(p) for p in orden]


def _es_error_reintentable(msg):
    """Timeout / sobredemanda / rate-limit: vale probar con otro proveedor."""
    ml = (msg or '').lower()
    return any(k in ml for k in ('timed out', 'timeout', 'timedout', 'temporarily',
                                 'try again', 'tryagain', 'overload', 'overloaded',
                                 'high demand', 'capacity', 'unavailable',
                                 '429', '503', '502', '500', 'rate limit', 'ratelimit',
                                 'too many requests', 'server error', 'connection'))


def _intentar_uno(cfgp, system_txt, contexto_txt, pregunta, historial, max_tokens=1024):
    """Un intento por proveedor (con fallback de modelo si lo dieron de baja).
    Devuelve (respuesta, modelo_usado, aviso|None). Sin sleeps: pensado para carrera."""
    if cfgp['proveedor'] == 'gemini':
        modelos = [cfgp['model']] + [m for m in ('gemini-3.6-flash', 'gemini-2.5-flash',
                      'gemini-2.0-flash', 'gemini-1.5-flash') if m != cfgp['model']]
        ultimo = None
        for m in modelos:
            try:
                r = _llamar_gemini(cfgp['api_key'], m, system_txt, contexto_txt,
                                   pregunta, historial, max_tokens=max_tokens)
                av = f"Modelo {cfgp['model']} no disponible; se usó {m}." if m != cfgp['model'] else None
                return r, m, av
            except RuntimeError as e:
                ultimo = e.args[0] if e.args else str(e)
                ml = ultimo.lower()
                if '404' in ultimo or 'not found' in ml:
                    continue
                raise RuntimeError(ultimo)
        raise RuntimeError(ultimo or 'Sin respuesta')
    modelos = [cfgp['model']] + [m for m in _IA_PROVEEDORES[cfgp['proveedor']]['fallbacks']
                                 if m != cfgp['model']]
    ultimo = None
    for m in modelos:
        try:
            r = _chat_openai_compat(cfgp, m, system_txt, contexto_txt, pregunta, historial,
                                    max_tokens=max_tokens)
            av = f"Modelo {cfgp['model']} no disponible; se usó {m}." if m != cfgp['model'] else None
            return r, m, av
        except RuntimeError as e:
            ultimo = e.args[0] if e.args else str(e)
            ml = ultimo.lower()
            if getattr(e, 'args', (None, None))[1] == 404 or any(
                    k in ml for k in ('not found', 'decommission', 'model_not',
                                      'no endpoints', 'does not exist')):
                continue
            raise RuntimeError(ultimo)
    raise RuntimeError(ultimo or 'Sin respuesta')


def _carrera_proveedores(candidatos, system_txt, contexto_txt, pregunta, historial, max_tokens=1024):
    """Dispara a todos los candidatos en paralelo; gana el primero que responde bien."""
    import concurrent.futures as _cf
    tope = int(os.environ.get('IA_RACE_TIMEOUT') or 60)
    errores = {}
    pool = _cf.ThreadPoolExecutor(max_workers=len(candidatos),
                                  thread_name_prefix='ia_race')
    try:
        futs = {pool.submit(_intentar_uno, c, system_txt, contexto_txt, pregunta, historial,
                            max_tokens=max_tokens): c
                for c in candidatos}
        try:
            for fut in _cf.as_completed(futs, timeout=tope):
                c = futs[fut]
                try:
                    respuesta, modelo, aviso = fut.result()
                    return c, modelo, respuesta, aviso
                except Exception as e:
                    errores[c['proveedor']] = str(e)
        except _cf.TimeoutError:
            pass
    finally:
        # No esperar a los lentos: el ganador ya respondió (los hilos mueren solos
        # cuando su urlopen agota su propio timeout).
        try:
            pool.shutdown(wait=False, cancel_futures=True)
        except TypeError:
            pool.shutdown(wait=False)
    detalle = '; '.join(f'{p}: {errores.get(p, "timeout")[:120]}' for p in
                        [c['proveedor'] for c in candidatos])
    raise RuntimeError(f'Ningún proveedor respondió en {tope}s ({detalle})')


def _resolver_pregunta(candidatos, cfg, system_txt, contexto, pregunta, historial, max_tokens=1024):
    """Resuelve sincronico (corre dentro del worker del job). Devuelve (dict, status)."""
    if len(candidatos) > 1 and (os.environ.get('IA_RACE') or '1') != '0':
        # Carrera: todos en paralelo, gana el primero que responde bien.
        try:
            cfgp, modelo_usado, respuesta, aviso = _carrera_proveedores(
                candidatos, system_txt, contexto, pregunta, historial, max_tokens=max_tokens)
        except RuntimeError as e:
            return ({'error': str(e)}), 502
        out = {'respuesta': respuesta, 'model': modelo_usado, 'proveedor': cfgp['proveedor'],
               'timeout_s': int(os.environ.get('IA_RACE_TIMEOUT') or 60)}
        if aviso:
            out['aviso'] = aviso
        if cfgp['proveedor'] != cfg['proveedor']:
            out['aviso'] = ((out.get('aviso') or '') + f" ({cfg['proveedor']} falló; respondió {cfgp['proveedor']}).").strip()
        return (out), 200
    if len(candidatos) > 1:
        # Secuencial (IA_RACE=0): probar en orden hasta el primero que responde.
        errores = {}
        for cfgp in candidatos:
            try:
                respuesta, modelo_usado, aviso = _intentar_uno(
                    cfgp, system_txt, contexto, pregunta, historial, max_tokens=max_tokens)
                out = {'respuesta': respuesta, 'model': modelo_usado,
                       'proveedor': cfgp['proveedor'], 'timeout_s': cfgp['timeout_s']}
                if aviso:
                    out['aviso'] = aviso
                if cfgp['proveedor'] != cfg['proveedor']:
                    out['aviso'] = ((out.get('aviso') or '') + f" ({cfg['proveedor']} falló; respondió {cfgp['proveedor']}).").strip()
                return (out), 200
            except Exception as e:
                errores[cfgp['proveedor']] = str(e)
        detalle = '; '.join(f'{p}: {m[:150]}' for p, m in errores.items())
        return ({'error': f'Ningún proveedor respondió ({detalle})'}), 502
    if cfg['proveedor'] != 'gemini':
        modelos = [cfg['model']] + [m for m in _IA_PROVEEDORES[cfg['proveedor']]['fallbacks']
                                    if m != cfg['model']]
        modelo_usado, respuesta, ultimo_error = modelos[0], None, None
        for m in modelos:
            try:
                respuesta = _chat_openai_compat(cfg, m, system_txt, contexto,
                                                pregunta, historial, max_tokens=max_tokens)
                modelo_usado, ultimo_error = m, None
                break
            except RuntimeError as e:
                ultimo_error = e.args[0] if e.args else str(e)
                ml = ultimo_error.lower()
                # Solo reintentar si el modelo no existe / fue dado de baja.
                if getattr(e, 'args', (None, None))[1] == 404 or any(
                        k in ml for k in ('not found', 'decommission', 'model_not',
                                          'no endpoints', 'does not exist')):
                    continue
                return ({'error': ultimo_error}), 502
        if respuesta is None:
            return ({'error': (ultimo_error or 'Sin respuesta') + ' Revisá /api/ia_modelos.'}), 502
        out = {'respuesta': respuesta, 'model': modelo_usado, 'proveedor': cfg['proveedor'],
               'timeout_s': cfg['timeout_s']}
        if modelo_usado != cfg['model']:
            out['aviso'] = f"Modelo {cfg['model']} no disponible; se usó {modelo_usado}."
        return (out), 200
    ultimo_error = None
    err_transitorio = None
    modelos = [cfg['model']] + [m for m in ('gemini-3.6-flash', 'gemini-2.5-flash', 'gemini-2.0-flash', 'gemini-1.5-flash') if m != cfg['model']]
    modelo_usado = modelos[0]
    respuesta = None

    def _es_transitorio(msg):
        ml = (msg or '').lower()
        return any(k in ml for k in ('high demand', 'overload', 'try again later',
                                     '429', '503', 'rate limit', 'ratelimit',
                                     'temporarily', 'unavailable', 'capacity'))

    for m in modelos:
        for intento in (1, 2):
            try:
                respuesta = _llamar_gemini(cfg['api_key'], m, system_txt,
                                           contexto, pregunta, historial, max_tokens=max_tokens)
                modelo_usado = m
                ultimo_error = None
                break
            except RuntimeError as e:
                ultimo_error = str(e)
                if _es_transitorio(ultimo_error) and intento == 1:
                    err_transitorio = ultimo_error
                    _time.sleep(3)  # pico de demanda: suele liberarse en segundos
                    continue
                break
        if respuesta is not None:
            break
        # Falla definitiva (ej. key inválida): no seguir probando modelos.
        if ultimo_error and '404' not in ultimo_error and 'not found' not in ultimo_error.lower() \
                and not _es_transitorio(ultimo_error):
            return ({'error': ultimo_error}), 502
    if respuesta is None:
        # Prevalece el error de sobredemanda (accionable: reintentar) sobre los 404 del fallback.
        msg = err_transitorio or ultimo_error or 'Sin respuesta'
        return ({'error': msg + ' Si persiste, revisá /api/ia_modelos para otro modelo con capacidad.'}), 502
    out = {'respuesta': respuesta, 'model': modelo_usado, 'proveedor': 'gemini',
           'timeout_s': cfg['timeout_s']}
    if modelo_usado != cfg['model']:
        out['aviso'] = f"Modelo {cfg['model']} no disponible; se usó {modelo_usado}."
    return (out), 200


import threading as _threading
import uuid as _uuid
import concurrent.futures as _cfutures

_JOBS = {}
_JOBS_LOCK = _threading.Lock()
_JOB_POOL = _cfutures.ThreadPoolExecutor(max_workers=4, thread_name_prefix='ia_job')
_JOB_TTL_S = 600


def _limpiar_jobs():
    ahora = _time.time()
    for jid in [k for k, j in _JOBS.items() if ahora - j.get('t0', ahora) > _JOB_TTL_S]:
        _JOBS.pop(jid, None)


def _ejecutar_job(job_id, candidatos, cfg, system_txt, contexto, pregunta, historial, modo='chat'):
    max_tok = 2000 if modo in ('briefing', 'interpretar') else 1024
    try:
        out, status = _resolver_pregunta(candidatos, cfg, system_txt, contexto,
                                         pregunta, historial, max_tokens=max_tok)
    except Exception as e:
        out, status = {'error': f'Error interno del worker: {e}'}, 500
    with _JOBS_LOCK:
        j = _JOBS.get(job_id)
        if j is not None and j.get('estado') == 'pendiente':
            j.update({'estado': 'ok' if status == 200 else 'error', **out})


@app.route('/api/pregunta_ia', methods=['POST'])
def api_pregunta_ia():
    data = request.get_json(force=True, silent=True) or {}
    prov_pedido = str(data.get('proveedor') or '').strip().lower()
    if prov_pedido not in ('groq', 'gemini', 'cerebras', 'openrouter', 'ollama'):
        prov_pedido = None
    candidatos = _candidatos_ia(prov_pedido)
    cfg = candidatos[0]
    if not cfg['configurado']:
        nombres_key = {'groq': 'GROQ_API_KEY (https://console.groq.com/keys, gratis)',
                       'gemini': 'GEMINI_API_KEY (https://aistudio.google.com/apikey)',
                       'cerebras': 'CEREBRAS_API_KEY (https://cloud.cerebras.ai/)',
                       'openrouter': 'OPENROUTER_API_KEY (https://openrouter.ai/keys)',
                       'ollama': 'OLLAMA_HOST (¿Ollama corriendo en local?)'}
        return jsonify({'error': f"IA no configurada: definí {nombres_key.get(cfg['proveedor'], 'la API key')} en el servidor."}), 503
    pregunta = str(data.get('pregunta') or '').strip()
    modo = str(data.get('modo') or 'chat').strip().lower()
    if not pregunta:
        return jsonify({'error': 'Escribí una pregunta.'}), 400
    # El briefing manda la declaración completa con los datos ya insertados.
    max_preg = 4000 if modo in ('briefing', 'interpretar') else 2000
    if len(pregunta) > max_preg:
        return jsonify({'error': f'Pregunta muy larga (máx {max_preg} caracteres).'}), 400
    contexto = str(data.get('contexto') or '')[:12000]
    # Si el frontend no mandó contexto, armar uno mínimo server-side con P1/P2.
    if not contexto:
        try:
            nom_a = str(data.get('persona_a') or '').strip()
            nom_b = str(data.get('persona_b') or '').strip()
            lineas_ctx = []
            if nom_a:
                df = cargar_datos()
                g = df[df['Nombre'] == nom_a]
                if not g.empty:
                    lineas_ctx.append(f'Persona 1 {nom_a}: puertas {sorted(set(int(x) for x in g["Puerta"].tolist()))}')
            if nom_b:
                df = cargar_datos()
                g = df[df['Nombre'] == nom_b]
                if not g.empty:
                    lineas_ctx.append(f'Persona 2 {nom_b}: puertas {sorted(set(int(x) for x in g["Puerta"].tolist()))}')
            contexto = '\n'.join(lineas_ctx)
            if not nom_a:
                lineas_ctx.append('Persona 1: no informada por el navegador.')
            if not nom_b:
                lineas_ctx.append('Persona 2: no informada por el navegador.')
            lineas_ctx.append('Tránsito: no informado por el navegador.')
            contexto = '\n'.join(lineas_ctx)
        except Exception:
            pass
    system_txt = (
        'Sos un asistente de Diseño Humano. Respondé en español, simple y corto '
        '(máx ~150 palabras salvo que pidan informe). Usá SOLO el contexto dado; '
        'si falta Persona 2 o tránsito, decilo y respondé con lo visible. '
        'No inventes puertas/canales. Citá puertas como "puerta 10" y canales como "10-57".'
    )
    # Informe diario (nueva declaración): 2 párrafos prosa max 500 palabras, con diseño
    # natal (Tipo/Autoridad/Centros/Puertas) y tránsitos Hoy vs Ayer ya insertados.
    system_txt_briefing = (
        'Sos un analista experto en Diseño Humano. El usuario te manda su diseño natal '
        '(Tipo, Autoridad, Centros definidos/abiertos, Puertas activas) y los tránsitos de hoy '
        '(puerta.línea + planeta) en comparación con los de ayer. '
        'Generá un informe diario práctico de dos párrafos en prosa, max 500 palabras, '
        'en tono directo y enfocado en la acción: 1) qué nuevos canales o centros se encienden '
        'hoy y qué tareas u oportunidades habilitan, 2) qué energía de ayer se retira y qué cambio '
        'de ritmo o actitud requiere, y 3) una guía clave de 2 oraciones con Estrategia y Autoridad '
        'sin engancharse en el No-Ser. La Estrategia sale del Tipo (Manifestador: Informar/Paz; '
        'Generador: Responder/Satisfacción; Proyector: Esperar invitación/Éxito; Reflector: Esperar '
        'la Luna/Sorpresa) y el No-Ser es lo contrario. No inventes puertas, planetas, '
        'canales ni centros que no estén en el prompt ni en el contexto.'
    )
    if modo == 'briefing':
        system_txt = system_txt_briefing
    if modo == 'interpretar':
        system_txt = system_txt_briefing
    job_id = _uuid.uuid4().hex[:12]
    with _JOBS_LOCK:
        _limpiar_jobs()
        _JOBS[job_id] = {'estado': 'pendiente', 't0': _time.time(),
                         'proveedores': [c['proveedor'] for c in candidatos],
                         'pregunta': pregunta[:120]}
    _JOB_POOL.submit(_ejecutar_job, job_id, candidatos, cfg, system_txt,
                     contexto, pregunta, data.get('historial'), modo)
    if len(candidatos) > 1:
        tope = int(os.environ.get('IA_RACE_TIMEOUT') or 60)
    else:
        tope = cfg['timeout_s']
    return jsonify({'job_id': job_id, 'estado': 'pendiente',
                    'proveedores': [c['proveedor'] for c in candidatos],
                    'timeout_s': tope})




@app.route('/api/pregunta_resultado')
def api_pregunta_resultado():
    jid = (request.args.get('id') or '').strip()
    with _JOBS_LOCK:
        _limpiar_jobs()
        j = _JOBS.get(jid)
        j = dict(j) if j else None
    if not j:
        return jsonify({'error': 'Job desconocido o expirado.'}), 404
    t0 = j.pop('t0', _time.time())
    j['espera_s'] = round(_time.time() - t0, 1)
    return jsonify(j)


@app.route('/api/pregunta_cancelar', methods=['POST'])
def api_pregunta_cancelar():
    data = request.get_json(force=True, silent=True) or {}
    jid = str(data.get('job_id') or data.get('id') or '').strip()
    with _JOBS_LOCK:
        _JOBS.pop(jid, None)
    return jsonify({'ok': True})


# --- Autoconocimiento: test minimo + informe ---
@app.route('/autoconocimiento')
def pagina_autoconocimiento():
    return render_template('autoconocimiento.html')


ENEATIPOS_PATH = Path("eneatipos.csv")
DOSHAS_PATH = Path("doshas.csv")
NUMERO_PATH = Path("numerologia.csv")
NATAL_PATH = Path("natal.csv")
NATAL_PLANETAS_PATH = Path("natal_planetas.csv")


_ENEA = {('ira', 'combativo'): 8, ('ira', 'sumiso'): 1, ('ira', 'reservado'): 9,
         ('verguenza', 'combativo'): 3, ('verguenza', 'sumiso'): 2, ('verguenza', 'reservado'): 4,
         ('miedo', 'combativo'): 7, ('miedo', 'sumiso'): 6, ('miedo', 'reservado'): 5}


def _mapa_csv(path):
    def _load():
        try:
            df = _leer_csv_robusto(path, sep=';')
            df.columns = [str(c).strip().lower() for c in df.columns]
            m = {}
            for _, r in df.iterrows():
                k = str(r.get('clave', '')).strip().lower()
                if k:
                    m[k] = {'titulo': str(r.get('titulo', '') or '').strip(),
                            'detalle': str(r.get('detalle', '') or '').strip()}
            return m
        except FileNotFoundError:
            return {}
    return _cache_get(path, _load)
_SIGNOS = [(20, 1, 'Capricornio', 'Acuario'), (19, 2, 'Acuario', 'Piscis'), (21, 3, 'Piscis', 'Aries'),
          (20, 4, 'Aries', 'Tauro'), (21, 5, 'Tauro', 'Geminis'), (21, 6, 'Geminis', 'Cancer'),
          (23, 7, 'Cancer', 'Leo'), (23, 8, 'Leo', 'Virgo'), (23, 9, 'Virgo', 'Libra'),
          (23, 10, 'Libra', 'Escorpio'), (22, 11, 'Escorpio', 'Sagitario'), (22, 12, 'Sagitario', 'Capricornio')]


def _num_vida(fecha):
    d = ''.join(ch for ch in (fecha or '') if ch.isdigit())
    if not d:
        return None
    while len(d) > 1 and d not in ('11', '22', '33'):
        d = str(sum(int(x) for x in d))
    return d


def _num_destino(nombre):
    t = unicodedata.normalize('NFD', (nombre or '').upper())
    t = ''.join(c for c in t if c.isalpha())
    if not t:
        return None
    v = {'A': 1, 'B': 2, 'C': 3, 'D': 4, 'E': 5, 'F': 6, 'G': 7, 'H': 8, 'I': 9, 'J': 1, 'K': 2,
         'L': 3, 'M': 4, 'N': 5, 'O': 6, 'P': 7, 'Q': 8, 'R': 9, 'S': 1, 'T': 2, 'U': 3, 'V': 4,
         'W': 5, 'X': 6, 'Y': 7, 'Z': 8}
    s = sum(v.get(c, 0) for c in t)
    d = str(s)
    while len(d) > 1 and d not in ('11', '22', '33'):
        d = str(sum(int(x) for x in d))
    return d


def _signo_de_longitud(lon):
    signos = ['Aries', 'Tauro', 'Geminis', 'Cancer', 'Leo', 'Virgo', 'Libra',
              'Escorpio', 'Sagitario', 'Capricornio', 'Acuario', 'Piscis']
    try:
        return signos[int(float(lon) % 360 // 30) % 12]
    except Exception:
        return None


_SIGNO_SIMBOLO = {'Aries': '♈', 'Tauro': '♉', 'Geminis': '♊', 'Cancer': '♋',
                  'Leo': '♌', 'Virgo': '♍', 'Libra': '♎', 'Escorpio': '♏',
                  'Sagitario': '♐', 'Capricornio': '♑', 'Acuario': '♒', 'Piscis': '♓'}


def _fecha_a_ddmmaaaa(fecha):
    f = str(fecha or '').strip()
    if len(f) >= 10 and f[4] == '-' and f[7] == '-':
        return f"{f[8:10]}/{f[5:7]}/{f[0:4]}"
    return f


_CARTA_CACHE = {}
def _carta_natal(data):
    """Carta con Sol, Luna, Ascendente y planetas en signo. Reusa nacimiento de Agregar persona."""
    if not SWE_DISPONIBLE:
        return {'error': 'Sin cálculo astrológico en este servidor.'}
    d = dict(data or {})
    d['fecha'] = _fecha_a_ddmmaaaa(d.get('fecha'))
    # Caché por (fecha,hora,lugar,lat,lon): el clan pedía la misma carta N veces.
    try:
        _ck = (str(d.get('fecha') or ''), str(d.get('hora') or ''),
               str(d.get('lugar') or '').strip().lower(),
               str(d.get('lat') or ''), str(d.get('lon') or ''))
        if _ck in _CARTA_CACHE:
            return dict(_CARTA_CACHE[_ck])
    except Exception:
        _ck = None
    jd, warnings, etiqueta, err = _parse_nacimiento(d)
    if err:
        return {'error': err, 'solo_solar': True}
    try:
        pids = [('Sol', swe.SUN), ('Luna', swe.MOON), ('Mercurio', swe.MERCURY),
                ('Venus', swe.VENUS), ('Marte', swe.MARS), ('Jupiter', swe.JUPITER),
                ('Saturno', swe.SATURN), ('Urano', swe.URANUS), ('Neptuno', swe.NEPTUNE),
                ('Pluton', swe.PLUTO)]
        planetas = []
        for nombre, pid in pids:
            lon = swe.calc_ut(jd, pid, swe.FLG_SWIEPH)[0][0] % 360
            planetas.append({'planeta': nombre, 'signo': _signo_de_longitud(lon)})
        asc = None
        try:
            lat = float(d.get('lat')) if d.get('lat') not in (None, '') else None
            lon = float(d.get('lon')) if d.get('lon') not in (None, '') else None
        except (ValueError, TypeError):
            lat, lon = None, None
        if lat is None:
            try:
                lat, lon, _tz, _nota, _e = _lugar_a_coords(d.get('lugar', ''))
            except Exception:
                lat, lon = None, None
        if lat is not None and lon is not None:
            try:
                cusps, ascmc = swe.houses(jd, lat, lon)
                asc = _signo_de_longitud(ascmc[0] % 360)
            except Exception:
                asc = None
        try:
            if _ck is not None and len(_CARTA_CACHE) > 2048:
                _CARTA_CACHE.clear()
        except Exception:
            pass
        mapa = {p['planeta']: p['signo'] for p in planetas}
        _out = {'planetas': planetas, 'sol': mapa.get('Sol'), 'luna': mapa.get('Luna'),
                'asc': asc, 'etiqueta': etiqueta, 'warnings': warnings}
        try:
            if _ck is not None:
                _CARTA_CACHE[_ck] = dict(_out)
        except Exception:
            pass
        return _out
    except Exception as e:
        return {'error': f'No se pudo calcular la carta: {e}', 'solo_solar': True}


def _signo_solar(fecha):
    try:
        p = str(fecha).split('-')
        if len(p) != 3:
            return None
        m, dia = int(p[1]), int(p[2])
        for corte, mes, antes, despues in _SIGNOS:
            if m == mes:
                return despues if dia >= corte else antes
    except Exception:
        pass
    return None


@app.route('/api/test')
def api_leer_test():
    """Devuelve el test corto guardado en test.csv para ?persona=. 404 si no hay."""
    nombre = (request.args.get('persona') or '').strip()
    if not nombre:
        return jsonify({'error': 'Falta persona'}), 400
    t = _test_de(nombre)
    if not t:
        return jsonify({'error': 'Sin test guardado'}), 404
    return jsonify(t)

@app.route('/api/sernoser', methods=['POST'])
def api_guardar_sernoser():
    """Guarda el autotest Ser/No-Ser en test.csv (misma fila del otro test, sin borrarlo)."""
    data = request.get_json(force=True, silent=True) or {}
    nombre = str(data.get('nombre') or data.get('persona') or '').strip()
    if not nombre:
        return jsonify({'error': 'Falta persona'}), 400
    try:
        alin = int(data.get('alin'))
    except (ValueError, TypeError):
        return jsonify({'error': 'Alineación inválida'}), 400
    from datetime import datetime as _dt
    base = _leer_test(nombre) or {'nombre': nombre}
    base['nombre'] = nombre
    base['sernoser_fecha'] = _dt.now().strftime('%Y-%m-%d %H:%M')
    base['sernoser_alin'] = str(max(0, min(100, alin)))
    base['sernoser_fugas'] = str(data.get('fugas') or '')[:2000]
    base['sernoser_resp'] = str(data.get('resp') or '')[:4000]
    # Asegurar columnas nuevas en la cabecera existente.
    try:
        if TEST_CSV_PATH.exists():
            leidas = _leer_test_rows()
            if leidas and leidas[0]:
                head = list(leidas[0])
                faltan = [c for c in TEST_CSV_COLS if str(c).lower() not in [str(x or '').strip().lower() for x in head]]
                if faltan:
                    head = head + faltan
                    with open(TEST_CSV_PATH, 'w', newline='', encoding='utf-8-sig') as f:
                        w = csv.writer(f, delimiter=';')
                        w.writerow(head)
                        w.writerows(leidas[1:])
    except Exception:
        pass
    if _upsert_test(base):
        return jsonify({'ok': True})
    return jsonify({'error': 'No se pudo guardar'}), 500

@app.route('/api/autoconocimiento', methods=['POST'])
def api_autoconocimiento():
    data = request.get_json(force=True, silent=True) or {}
    triada = str(data.get('triada') or '').strip().lower()
    modo = str(data.get('modo') or '').strip().lower()
    enea = _ENEA.get((triada, modo))
    dosha_votos = [str(data.get(k) or '') for k in ('cuerpo', 'diges', 'sueno')]
    dosha = {v: dosha_votos.count(v) for v in ('vata', 'pitta', 'kapha')}
    dom = max(dosha, key=lambda k: dosha[k]) if any(dosha.values()) else 'a definir'
    neuro = []
    if str(data.get('foco')) in ('pierdo', 'ambos'):
        neuro.append('atencion dispersa (explorar TDAH)')
    if str(data.get('foco')) in ('hiper', 'ambos'):
        neuro.append('hiperenfoque')
    if str(data.get('sensorial')) == 'mucho':
        neuro.append('sobrecarga sensorial (explorar TEA/TDAH)')
    if str(data.get('rutina')) == 'rutina':
        neuro.append('necesidad de rutina')
    if str(data.get('rutina')) == 'aburro':
        neuro.append('busqueda de novedad')
    if str(data.get('social')) in ('lectura', 'ambos2'):
        neuro.append('lectura social literal')
    if str(data.get('social')) in ('intenso', 'ambos2'):
        neuro.append('intereses intensos / altas capacidades a explorar')
    vida = _num_vida(data.get('fecha'))
    destino = _num_destino(data.get('nombre_num') or data.get('nombre'))
    carta = _carta_natal(data)
    sol = (carta.get('sol') if isinstance(carta, dict) else None) or _signo_solar(data.get('fecha'))
    luna = carta.get('luna') if isinstance(carta, dict) else None
    asc = carta.get('asc') if isinstance(carta, dict) else None
    planetas = carta.get('planetas') if isinstance(carta, dict) else None
    aviso_carta = ''
    if isinstance(carta, dict) and carta.get('error'):
        aviso_carta = str(carta.get('error'))
    elif isinstance(carta, dict) and carta.get('warnings'):
        aviso_carta = '; '.join(carta.get('warnings'))
    m_enea, m_dosha, m_num, m_nat = _mapa_csv(ENEATIPOS_PATH), _mapa_csv(DOSHAS_PATH), _mapa_csv(NUMERO_PATH), _mapa_csv(NATAL_PATH)
    m_plan = _mapa_csv(NATAL_PLANETAS_PATH)
    e = m_enea.get(str(enea or ''), {})
    d = m_dosha.get(dom, {})
    nv = m_num.get(str(vida or ''), {})
    nd = m_num.get(str(destino or ''), {})
    s = m_nat.get(str(sol or '').lower(), {})
    sl = m_nat.get(str(luna or '').lower(), {}) if luna else {}
    sa = m_nat.get(str(asc or '').lower(), {}) if asc else {}
    detalle_planetas = ''
    if planetas:
        # Texto propio por planeta+signo (natal_planetas.csv). Sin repetir detalle:
        # Sol/Luna/Ascendente ya se describen arriba.
        lineas = []
        for p in planetas:
            if p.get('planeta') in ('Sol', 'Luna'):
                continue
            clave_p = f"{str(p.get('planeta') or '').lower()}_{str(p.get('signo') or '').lower()}"
            det = str(m_plan.get(clave_p, {}).get('detalle', '') or '').strip()
            if not det:
                det = str(m_nat.get(str(p.get('signo') or '').lower(), {}).get('detalle', '') or '').strip()
            if det:
                lineas.append(f"- {p['planeta']} en {p['signo']}: {det}")
            else:
                lineas.append(f"- {p['planeta']} en {p['signo']}")
        if lineas:
            detalle_planetas = 'Qué significa para ti, planeta por planeta:\n' + '\n'.join(lineas)
    # Secciones que no se respondieron se omiten del informe.
    hay_enea = bool(enea)
    hay_dosha = any(str(data.get(k) or '') for k in ('cuerpo', 'diges', 'sueno'))
    hay_neuro = any(str(data.get(k) or '') for k in ('foco', 'sensorial', 'rutina', 'social'))
    hay_num = bool(str(data.get('fecha') or '').strip() or str(data.get('nombre_num') or data.get('nombre') or '').strip())
    hay_natal = bool(str(data.get('fecha') or '').strip())
    partes = []
    if hay_enea:
        partes.append(f"Tu eneatipo es el {enea} {e.get('titulo', '')}. Esto significa que {e.get('detalle', '')}")
    if hay_dosha:
        partes.append(f"Tu energía base es {dom} {d.get('titulo', '')}. Esto significa que {d.get('detalle', '')}")
    if hay_neuro:
        if neuro:
            partes.append('En tus respuestas aparecen estos rasgos a explorar con un profesional, '
                          'no son un diagnóstico: ' + ', '.join(neuro) + '.')
        else:
            partes.append('En tus respuestas no aparecen rasgos marcados para explorar.')
    if hay_num:
        partes.append(f"Tu numerología es vida {vida or '?'} y destino {destino or '?'}. "
                      f"El número de vida sale de tu fecha de nacimiento y marca {nv.get('detalle', '')} "
                      f"El número de destino sale de tu nombre y marca {nd.get('detalle', '')}")
    if hay_natal:
        partes.append(f"Tu carta natal tiene el Sol en {sol or '?'} {s.get('detalle', '')} "
                      f"La Luna está en {luna or 'por definir, falta hora o lugar'} {sl.get('detalle', '') if luna else ''} "
                      f"El Ascendente está en {asc or 'por definir, falta lugar y hora exactos'} {sa.get('detalle', '') if asc else ''} "
                      f"{detalle_planetas + ' ' if detalle_planetas else ''}"
                      f"{aviso_carta}")
    informe = "\n\n".join(p for p in partes if str(p or '').strip())
    guardado = False
    if informe:
        guardado = bool(_upsert_test({
            'nombre': str(data.get('nombre') or '').strip(),
            'fecha': str(data.get('fecha') or ''), 'hora': str(data.get('hora') or ''),
            'lugar': str(data.get('lugar') or ''),
            'triada': triada, 'modo': modo,
            'foco': str(data.get('foco') or ''), 'sensorial': str(data.get('sensorial') or ''),
            'rutina': str(data.get('rutina') or ''), 'social': str(data.get('social') or ''),
            'cuerpo': str(data.get('cuerpo') or ''), 'diges': str(data.get('diges') or ''),
            'sueno': str(data.get('sueno') or ''), 'busco': '',
            'eneatipo': str(enea or ''), 'dosha_dom': (dom if hay_dosha else ''),
            'vida': str(vida or ''), 'destino': str(destino or ''),
            'solar': str(sol or ''), 'luna': str(luna or ''), 'asc': str(asc or ''),
            'informe': informe,
        }))
    else:
        informe = 'Sin datos suficientes para el informe.'
    return jsonify({'eneatipo': enea, 'eneatipo_txt': e.get('titulo', ''), 'dosha': dosha,
                    'dosha_dom': dom, 'neuro': neuro, 'vida': vida,
                    'destino': destino, 'solar': sol, 'luna': luna, 'asc': asc,
                    'planetas': planetas, 'informe': informe, 'guardado': guardado})


# ---------- Clan por P1 (clan.csv: P1;rol;familiar) ----------
def _leer_clan_df():
    import csv as _csv
    def _load():
        if _FUENTE['path'] is not None:
            df = _leer_xlsx_hoja(_FUENTE['path'], 'clan')
            df.columns = [str(c).strip() for c in df.columns]
            return [{str(k): str(r.get(k, '') or '').strip() for k in df.columns}
                    for _, r in df.iterrows()]
        if not CLAN_PATH.exists():
            return []
        try:
            with open(CLAN_PATH, 'r', encoding='utf-8-sig', newline='') as f:
                sep = ';'
                head = f.readline()
                if '\t' in head and ';' not in head:
                    sep = '\t'
                f.seek(0)
                return list(_csv.DictReader(f, delimiter=sep))
        except Exception:
            return []
    _src, _key = _cache_arg(CLAN_PATH, 'clan')
    return _cache_get(_src, _load, key=_key)


def _borrar_clan(p1):
    """Elimina las filas del clan.csv cuyo P1 sea el indicado. Devuelve cuántas borró."""
    try:
        if not CLAN_PATH.exists():
            return 0
        plow = str(p1 or '').strip().lower()
        filas = _leer_clan_df()
        resto = []
        for r in filas:
            kp1 = str(r.get('P1') or r.get('p1') or '').strip()
            if kp1.lower() == plow:
                continue
            resto.append({'P1': kp1, 'rol': str(r.get('rol') or ''), 'familiar': str(r.get('familiar') or '')})
        borradas = len(filas) - len(resto)
        if not borradas:
            return 0
        with open(CLAN_PATH, 'w', encoding='utf-8-sig', newline='') as f:
            w = csv.DictWriter(f, fieldnames=['P1', 'rol', 'familiar'], delimiter=';')
            w.writeheader()
            w.writerows(resto)
        return borradas
    except Exception:
        return 0


@app.route('/api/clan')
def api_clan_get():
    if _perfiles_cuenta_actual() is not None:
        return jsonify({'m': {}, 'mayores': [], 'menores': [], 'parejas': [], 'hijos': [],
                        'solo_local': True})
    p1 = (request.args.get('p1') or '').strip()
    if not p1:
        return jsonify({'m': {}, 'mayores': [], 'menores': [], 'parejas': [], 'hijos': []})
    filas = _leer_clan_df()
    m, mayores, menores, parejas, hijos = {}, [], [], [], []
    plow = p1.lower()
    for r in filas:
        try:
            kp1 = str(r.get('P1') or r.get('p1') or '').strip()
        except Exception:
            continue
        if kp1.lower() != plow:
            continue
        rol = str(r.get('rol') or '').strip()
        fam = str(r.get('familiar') or '').strip()
        if not rol or not fam:
            continue
        if rol.startswith('mayor_'):
            mayores.append(fam)
        elif rol.startswith('menor_'):
            menores.append(fam)
        elif rol.startswith('pareja_'):
            parejas.append(fam)
        elif rol.startswith('hijo_'):
            hijos.append(fam)
        else:
            m[rol] = fam
    return jsonify({'m': m, 'mayores': mayores, 'menores': menores, 'parejas': parejas, 'hijos': hijos})


@app.route('/api/clan', methods=['POST'])
def api_clan_post():
    import csv as _csv
    if _perfiles_cuenta_actual() is not None:
        return jsonify({'ok': True, 'solo_local': True})
    try:
        data = request.get_json(force=True) or {}
    except Exception:
        return jsonify({'error': 'JSON invalido'}), 400
    p1 = str(data.get('p1') or '').strip()
    if not p1:
        return jsonify({'error': 'falta p1'}), 400
    m = data.get('m') or {}
    mayores = data.get('mayores') or []
    menores = data.get('menores') or []
    parejas = data.get('parejas') or []
    hijos = data.get('hijos') or []
    plow = p1.lower()
    filas = _leer_clan_df()
    nuevas = []
    for r in filas:
        try:
            kp1 = str(r.get('P1') or r.get('p1') or '').strip()
        except Exception:
            continue
        if kp1.lower() != plow:
            nuevas.append({'P1': kp1, 'rol': str(r.get('rol') or ''), 'familiar': str(r.get('familiar') or '')})
    for rol, fam in (m or {}).items():
        fam = str(fam or '').strip()
        if not fam:
            continue
        nuevas.append({'P1': p1, 'rol': str(rol), 'familiar': fam})
    for i, n in enumerate(mayores or []):
        n = str(n or '').strip()
        if n:
            nuevas.append({'P1': p1, 'rol': f'mayor_{i+1}', 'familiar': n})
    for i, n in enumerate(menores or []):
        n = str(n or '').strip()
        if n:
            nuevas.append({'P1': p1, 'rol': f'menor_{i+1}', 'familiar': n})
    for i, n in enumerate(parejas or []):
        n = str(n or '').strip()
        if n:
            nuevas.append({'P1': p1, 'rol': f'pareja_{i+1}', 'familiar': n})
    for i, n in enumerate(hijos or []):
        n = str(n or '').strip()
        if n:
            nuevas.append({'P1': p1, 'rol': f'hijo_{i+1}', 'familiar': n})
    # Auto-guardar demás personas con sus respectivos padres (solo crea el
    # bloque P1=familiar si aún no existe, para no pisar datos manuales):
    # - cada hermano (mayor/menor): mismos padre/madre/abuelos que P1
    # - padre: padre=ap_abuelo, madre=ap_abuela
    # - madre: padre=am_abuelo, madre=am_abuela
    try:
        existentes = set(str(r.get('P1') or '').strip().lower() for r in nuevas)
        ap_ab = str((m or {}).get('ap_abuelo') or '').strip()
        ap_aa = str((m or {}).get('ap_abuela') or '').strip()
        am_aa = str((m or {}).get('am_abuela') or '').strip()
        am_ab = str((m or {}).get('am_abuelo') or '').strip()
        padre = str((m or {}).get('padre') or '').strip()
        madre = str((m or {}).get('madre') or '').strip()

        def _agregar_bloque(nuevo_p1, roles):
            if not nuevo_p1 or nuevo_p1.strip().lower() in existentes:
                return
            nuevas.append({'P1': nuevo_p1, 'rol': 'p1', 'familiar': nuevo_p1})
            for rol, fam in roles:
                fam = str(fam or '').strip()
                if fam:
                    nuevas.append({'P1': nuevo_p1, 'rol': rol, 'familiar': fam})
            existentes.add(nuevo_p1.strip().lower())

        hermanos = [str(n or '').strip() for n in list(mayores or []) + list(menores or [])]
        for h in hermanos:
            if not h:
                continue
            _agregar_bloque(h, [('ap_abuelo', ap_ab), ('ap_abuela', ap_aa),
                                ('am_abuela', am_aa), ('am_abuelo', am_ab),
                                ('padre', padre), ('madre', madre)])
        if padre:
            _agregar_bloque(padre, [('padre', ap_ab), ('madre', ap_aa),
                                    ('pareja', madre)])
        if madre:
            _agregar_bloque(madre, [('padre', am_ab), ('madre', am_aa),
                                    ('pareja', padre)])
    except Exception:
        pass
    try:
        with open(CLAN_PATH, 'w', encoding='utf-8-sig', newline='') as f:
            w = _csv.DictWriter(f, fieldnames=['P1', 'rol', 'familiar'], delimiter=';')
            w.writeheader()
            w.writerows(nuevas)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    try:
        _cache_invalidate(CLAN_PATH)
    except Exception:
        pass
    return jsonify({'ok': True})


# ---------- Análisis avanzado del clan ----------
_CLAN_DEFENSA = {'6-59', '27-50'}
_CLAN_EGO = {'19-49', '40-37', '54-32', '26-44', '21-45'}
_CLAN_PUENTES = {1: {4}, 4: {1}, 2: {5}, 5: {2}, 3: {6}, 6: {3}}
_CLAN_ROL_LINEA = {1: 'Investigador', 2: 'Ermitaño', 3: 'Mártir', 4: 'Oportunista', 5: 'Hereje', 6: 'Modelo'}


def _clan_lineas_perfil(perfil):
    """Líneas 1-6 del perfil (acepta '5/1' o '5-1')."""
    out = []
    for x in str(perfil or '').replace('-', '/').split('/'):
        try:
            n = int(str(x).strip())
        except Exception:
            continue
        if 1 <= n <= 6 and n not in out:
            out.append(n)
    return out


def _clan_canales_par(puertas_a, puertas_b):
    """Canales que aparecen al juntar dos personas (electromagnético, compañía, dominio)."""
    A = set(int(p) for p in (puertas_a or []))
    B = set(int(p) for p in (puertas_b or []))
    out = []
    for k in sorted(set(_hd_norm_canal(c) for c in _HD_CANAL_CENTROS)):
        try:
            x, y = [int(z) for z in k.split('-')]
        except Exception:
            continue
        a1, a2 = x in A, y in A
        b1, b2 = x in B, y in B
        if (a1 and b2) or (a2 and b1):
            out.append({'canal': k, 'tipo': 'electromagnetico'})
        elif a1 and a2 and b1 and b2:
            out.append({'canal': k, 'tipo': 'compania'})
        elif (a1 and a2 and not (b1 or b2)) or (b1 and b2 and not (a1 or a2)):
            out.append({'canal': k, 'tipo': 'dominio'})
    return out


def _clan_analisis(p1):
    """Análisis agregado del clan: repeticiones, compensaciones, parejas, circuitos,
    puentes de perfil, roles generacionales, evolución y Penta."""
    p1 = str(p1 or '').strip()
    filas = _leer_clan_df()
    plow = p1.lower()
    miembros, vistos = [], set()

    def _add(nombre, rol):
        nombre = str(nombre or '').strip()
        if not nombre or nombre.lower() in vistos:
            return
        vistos.add(nombre.lower())
        miembros.append({'nombre': nombre, 'rol': str(rol or '').strip()})

    if p1:
        _add(p1, 'p1')
    for r in filas:
        try:
            kp1 = str(r.get('P1') or r.get('p1') or '').strip()
        except Exception:
            continue
        if kp1.lower() != plow:
            continue
        _add(r.get('familiar'), r.get('rol'))

    fichas = {}
    try:
        _df_all = cargar_datos()
        _vinc_all = cargar_vinculos()
    except Exception:
        _df_all = _vinc_all = None
    for m in miembros:
        try:
            f, err = _ficha_basica_para_persona(m['nombre'], _df=_df_all, _vinc=_vinc_all)
        except Exception:
            f, err = None, 'error'
        if f and not err:
            fichas[m['nombre']] = f

    puertas_por, canales_por = {}, {}
    for nombre, f in fichas.items():
        for p in (f.get('puertas') or []):
            try:
                puertas_por.setdefault(int(p), set()).add(nombre)
            except Exception:
                pass
        for c in (f.get('canales') or []):
            canales_por.setdefault(_hd_norm_canal(c), set()).add(nombre)

    repeticiones = []
    for p in sorted(puertas_por):
        personas = sorted(puertas_por[p])
        if len(personas) >= 2:
            repeticiones.append({'puerta': p, 'personas': personas})
    repeticiones.sort(key=lambda x: (-len(x['personas']), x['puerta']))

    compensaciones = []
    todos = sorted(fichas)
    for p in sorted(puertas_por):
        definida = sorted(puertas_por[p])
        abierta = [n for n in todos if n not in puertas_por[p]]
        if definida and abierta:
            compensaciones.append({'puerta': p, 'definida_en': definida, 'abierta_en': abierta})
    compensaciones.sort(key=lambda x: (-len(x['definida_en']), x['puerta']))

    # Pares: P1 con cada integrante + parejas declaradas por rol.
    por_rol = {}
    for m in miembros:
        por_rol.setdefault(m['rol'], m['nombre'])
    pares = []
    if p1:
        for m in miembros:
            if m['nombre'] != p1:
                pares.append((p1, m['nombre']))
    for a, b in [('ap_abuelo', 'ap_abuela'), ('am_abuelo', 'am_abuela'),
                 ('padre', 'madre'), ('p1', 'pareja')]:
        if a in por_rol and b in por_rol:
            pares.append((por_rol[a], por_rol[b]))
    canales_pareja, vistos_pares = [], set()
    for a, b in pares:
        if a not in fichas or b not in fichas or a == b:
            continue
        k = tuple(sorted((a, b)))
        if k in vistos_pares:
            continue
        vistos_pares.add(k)
        ch = _clan_canales_par(fichas[a].get('puertas'), fichas[b].get('puertas'))
        if ch:
            canales_pareja.append({'entre': [a, b], 'canales': ch})

    canales_clan = set(canales_por)
    for par in canales_pareja:
        for c in par['canales']:
            canales_clan.add(c['canal'])
    defensa = sorted(c for c in canales_clan if c in _CLAN_DEFENSA)
    ego = sorted(c for c in canales_clan if c in _CLAN_EGO)

    def _personas_de(lista):
        return sorted({n for c in lista for n in canales_por.get(c, set())})

    puentes = []
    nombres = sorted(fichas)
    for i, a in enumerate(nombres):
        la = _clan_lineas_perfil(fichas[a].get('perfil'))
        for b in nombres[i + 1:]:
            lb = _clan_lineas_perfil(fichas[b].get('perfil'))
            res = []
            for x in la:
                for y in lb:
                    if y in _CLAN_PUENTES.get(x, set()):
                        res.append([x, y])
            if res:
                puentes.append({'entre': [a, b], 'lineas': res})

    generacion = {
        'ap_abuelo': 'G1', 'ap_abuela': 'G1', 'am_abuelo': 'G1', 'am_abuela': 'G1',
        'padre': 'G2', 'madre': 'G2', 'p1': 'G3', 'pareja': 'G3',
    }
    roles_generacionales = []
    for m in miembros:
        f = fichas.get(m['nombre'])
        if not f:
            continue
        lineas = _clan_lineas_perfil(f.get('perfil'))
        rol = m['rol']
        gen = generacion.get(rol)
        if not gen:
            if rol.startswith(('mayor_', 'menor_', 'pareja_')):
                gen = 'G3'
            elif rol.startswith('hijo_'):
                gen = 'G4'
            else:
                gen = ''
        roles_generacionales.append({
            'persona': m['nombre'], 'rol': rol, 'generacion': gen,
            'perfil': f.get('perfil'), 'lineas': lineas,
            'rol_linea': [_CLAN_ROL_LINEA.get(x, '') for x in lineas],
        })

    planificacion = ('37-40' in canales_clan) or (37 in puertas_por and 40 in puertas_por)
    mutacion = ('3-60' in canales_clan) or (3 in puertas_por and 60 in puertas_por) or (55 in puertas_por)
    claves = []
    if planificacion:
        claves.append('37-40')
    if '3-60' in canales_clan:
        claves.append('3-60')
    if 55 in puertas_por:
        claves.append('55')
    fase = 'mixta' if (planificacion and mutacion) else ('planificacion' if planificacion else ('mutacion' if mutacion else 'indefinida'))

    penta = None
    if len(fichas) >= 3:
        union = set()
        for f in fichas.values():
            union.update(int(p) for p in (f.get('puertas') or []))
        canales_penta = _hd_canales_de_puertas(union)
        penta = {
            'integrantes': sorted(fichas),
            'canales': canales_penta,
            'centros': sorted(_hd_centros_definidos(canales_penta)),
        }

    integrantes = []
    for m in miembros:
        f = fichas.get(m['nombre']) or {}
        integrantes.append({
            'nombre': m['nombre'], 'rol': m['rol'],
            'perfil': f.get('perfil'), 'tipo': f.get('tipo'),
            'autoridad': f.get('autoridad'), 'definicion': f.get('definicion'),
        })

    return {
        'p1': p1,
        'integrantes': integrantes,
        'repeticiones': repeticiones,
        'compensaciones': compensaciones,
        'canales_pareja': canales_pareja,
        'circuitos': {
            'defensa': {'canales': defensa, 'personas': _personas_de(defensa)},
            'ego': {'canales': ego, 'personas': _personas_de(ego)},
        },
        'puentes': puentes,
        'roles_generacionales': roles_generacionales,
        'evolucion': {'fase': fase, 'claves': claves},
        'penta': penta,
    }


@app.route('/api/clan_analisis')
def api_clan_analisis():
    p1 = (request.args.get('p1') or '').strip()
    if not p1:
        return jsonify({'error': 'falta p1'}), 400
    try:
        return jsonify(_clan_analisis(p1))
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/fichas_batch', methods=['POST'])
def api_fichas_batch():
    """Fichas básicas de N personas en 1 request (el clan pedía 1 fetch por integrante)."""
    try:
        data = request.get_json(force=True, silent=True) or {}
    except Exception:
        return jsonify({'error': 'JSON invalido'}), 400
    nombres = data.get('personas') or data.get('nombres') or []
    if isinstance(nombres, str):
        nombres = [nombres]
    nombres = [str(n or '').strip() for n in (nombres or []) if str(n or '').strip()][:60]
    if not nombres:
        return jsonify({})
    out = {}
    try:
        _df_all = cargar_datos()
    except Exception:
        _df_all = None
    try:
        _vinc_all = cargar_vinculos()
    except Exception:
        _vinc_all = None
    for n in nombres:
        try:
            ficha, err = _ficha_basica_para_persona(n, _df=_df_all, _vinc=_vinc_all)
            out[n] = {'error': err} if err else ficha
        except Exception as e:
            out[n] = {'error': str(e)}
    return jsonify(out)


# ---------- Conocidos por P1 (conocidos.csv: p1;nombre;estado) ----------
# estado: activo | muerto | sin_contacto | no_conozco
# muerto es global (vale para todo P1). Los demás solo para su P1.
# Lo no listado = activo.
CONOCIDOS_VALIDOS = ('activo', 'muerto', 'sin_contacto', 'no_conozco')

def _leer_conocidos_todo():
    def _load():
        filas = []
        try:
            if not CONOCIDOS_PATH.exists():
                return filas
            import csv as _csv
            with open(CONOCIDOS_PATH, 'r', encoding='utf-8-sig', newline='') as f:
                rd = _csv.DictReader(f, delimiter=';')
                cols = [c.strip().lower() for c in (rd.fieldnames or [])]
                for r in rd:
                    if 'p1' in cols or 'P1' in (rd.fieldnames or []):
                        p1 = str(r.get('p1') or r.get('P1') or '').strip()
                        n = str(r.get('nombre') or '').strip()
                        e = str(r.get('estado') or '').strip().lower()
                    else:
                        # formato viejo global: todo de Jorge
                        p1 = 'Jorge'
                        n = str(r.get('nombre') or '').strip()
                        e = str(r.get('estado') or '').strip().lower()
                    if n and e in CONOCIDOS_VALIDOS:
                        filas.append({'p1': p1, 'nombre': n, 'estado': e})
        except Exception:
            pass
        return filas
    return _cache_get(CONOCIDOS_PATH, _load)


def _leer_conocidos(p1=''):
    plow = str(p1 or '').strip().lower()
    mapa = {}
    for r in _leer_conocidos_todo():
        e = r['estado']
        rp1 = str(r.get('p1') or '').strip()
        n = r['nombre']
        if e == 'muerto':
            mapa[n.lower()] = {'nombre': n, 'estado': e, 'p1': rp1}
        elif plow and rp1.lower() == plow:
            mapa[n.lower()] = {'nombre': n, 'estado': e, 'p1': rp1}
    return mapa


@app.route('/api/conocidos')
def api_conocidos_get():
    if _perfiles_cuenta_actual() is not None:
        return jsonify({})
    p1 = (request.args.get('p1') or '').strip()
    return jsonify(_leer_conocidos(p1))


@app.route('/api/conocidos', methods=['POST'])
def api_conocidos_post():
    import csv as _csv
    if _perfiles_cuenta_actual() is not None:
        return jsonify({'ok': True, 'solo_local': True})
    try:
        data = request.get_json(force=True) or {}
    except Exception:
        return jsonify({'error': 'JSON invalido'}), 400
    p1 = str(data.get('p1') or '').strip()
    nombre = str(data.get('nombre') or '').strip()
    estado = str(data.get('estado') or 'activo').strip().lower()
    if not nombre:
        return jsonify({'error': 'falta nombre'}), 400
    if estado not in CONOCIDOS_VALIDOS:
        return jsonify({'error': 'estado invalido'}), 400
    if estado != 'muerto' and not p1:
        return jsonify({'error': 'falta p1'}), 400
    filas = [r for r in _leer_conocidos_todo()]
    # quitar duplicado mismo p1+nombre (muerto: quita todos los de ese nombre)
    nl = nombre.lower()
    nuevas = []
    for r in filas:
        if r['nombre'].lower() != nl:
            nuevas.append(r)
            continue
        if estado == 'muerto':
            continue  # se reemplaza por el global
        if str(r.get('p1') or '').strip().lower() != p1.lower():
            nuevas.append(r)
    nuevas.append({'p1': '' if estado == 'muerto' else p1, 'nombre': nombre, 'estado': estado})
    try:
        with open(CONOCIDOS_PATH, 'w', encoding='utf-8-sig', newline='') as f:
            w = _csv.DictWriter(f, fieldnames=['p1', 'nombre', 'estado'], delimiter=';')
            w.writeheader()
            for v in sorted(nuevas, key=lambda x: (x['nombre'].lower(), x['p1'].lower())):
                w.writerow(v)
        _cache_invalidate(CONOCIDOS_PATH)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    return jsonify({'ok': True})


# ---------- Fase 1 Nube Neon (aditivo, no rompe CSV local) ----------
@app.route('/nube_test')
def pagina_nube_test():
    return render_template('nube_test.html')


@app.route('/api/nube/health')
def api_nube_health():
    try:
        import nube_db as _nube
        ok = _nube.disponible()
        if ok:
            try:
                _nube.init_db()
                return jsonify({'ok': True, 'db': True})
            except Exception as e:
                return jsonify({'ok': False, 'db': False, 'error': str(e)[:300]}), 500
        return jsonify({'ok': True, 'db': False, 'msg': 'Sin DATABASE_URL: solo navegador'})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)[:300]}), 500


# ---------- Keep-alive Render + Neon ----------
@app.route('/health')
@app.route('/api/health')
def api_health_keepalive():
    """Endpoint ligero para pings externos (Render no duerme, Neon no suspende)."""
    db_ok = None
    err = None
    try:
        import nube_db as _nube
        if _nube.disponible():
            try:
                db_ok = _nube.ping()
            except Exception:
                _nube.init_db()
                db_ok = _nube.ping()
        else:
            db_ok = None
    except Exception as e:
        err = str(e)[:200]
        db_ok = False
    payload = {'ok': True, 'service': 'diseno-humano', 'db': db_ok}
    if err:
        payload['error'] = err
    return jsonify(payload), 200


# ---------- Fase 3: registro de visitas (IP completa para pais posterior) ----------
_VIS_TASA = {}
@app.route('/api/visita/inicio', methods=['POST'])
def api_visita_inicio():
    """Crea una fila de visita (la llama el navegador tras cargar la portada)."""
    try:
        import time as _t
        import visitas_db as _vis
        if not _vis.disponible():
            return jsonify({'ok': False, 'sin_db': True})
        ip = _vis.ip_real(request)
        ahora = _t.time()
        ultimo = _VIS_TASA.get(ip, 0)
        if ahora - ultimo < 10:
            return jsonify({'ok': False, 'tasa': True})
        _VIS_TASA[ip] = ahora
        if len(_VIS_TASA) > 2000:
            _VIS_TASA.clear()
        _yo_token = _os_mod.environ.get('YO_TOKEN', 'alma-yo-secreto')
        data = request.get_json(force=True, silent=True) or {}
        es_propia = (request.cookies.get('alma_yo') == _yo_token) or (request.args.get('yo') == _yo_token) or (str(data.get('yo') or '') == _yo_token)
        vid = _vis.registrar(
            ip,
            str(data.get('path') or request.referrer or '/')[:200],
            (request.headers.get('User-Agent') or '')[:300],
            (request.referrer or '')[:300],
            es_propia=es_propia,
        )
        resp = jsonify({'ok': True, 'id': vid})
        if es_propia:
            resp.set_cookie('alma_yo', _yo_token, max_age=60*60*24*365, samesite='Lax')
        # Limpieza ocasional (1 de cada ~50) para no llenar Neon.
        try:
            import random as _r
            if _r.randint(1, 50) == 1:
                _vis.limpiar(90)
        except Exception:
            pass
        return resp
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)[:200]}), 500


@app.route('/api/visita/fin', methods=['POST'])
def api_visita_fin():
    """Actualiza la duracion en segundos (beacon al salir/ocultar la pagina)."""
    try:
        import visitas_db as _vis
        # sendBeacon puede llegar sin JSON (texto): aceptar ambas formas.
        data = request.get_json(force=True, silent=True) or {}
        if not isinstance(data, dict):
            data = {}
        vid = data.get('id')
        try:
            vid = int(vid)
        except (ValueError, TypeError):
            vid = None
        try:
            seg = int(data.get('segundos') or data.get('seg') or 0)
        except (ValueError, TypeError):
            seg = 0
        if not vid:
            return jsonify({'ok': False}), 400
        return jsonify({'ok': _vis.cerrar(vid, seg, _vis.ip_real(request))})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)[:200]}), 500



@app.route('/api/nube/guardar', methods=['POST'])
def api_nube_guardar():
    data = request.get_json(force=True, silent=True) or {}
    device_id = str(data.get('device_id') or '').strip()[:64]
    if not device_id:
        return jsonify({'error': 'Falta device_id (se genera en navegador)'}), 400
    try:
        import nube_db as _nube
        if not _nube.disponible():
            return jsonify({'error': 'Neon no configurado (falta DATABASE_URL en Render)'}), 503
        _nube.init_db()
        _nube.guardar_perfil(device_id, str(data.get('email') or '').strip()[:120], {
            'nombre': str(data.get('nombre') or '').strip(),
            'fecha': str(data.get('fecha') or ''), 'hora': str(data.get('hora') or ''),
            'lugar': str(data.get('lugar') or ''), 'lat': data.get('lat'),
            'lon': data.get('lon'), 'tz': data.get('tz'),
            'tz_name': str(data.get('tz_name') or ''),
            'datos_json': data.get('datos_json') or {},
            'visibilidad': str(data.get('visibilidad') or 'privado'),
        })
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'error': str(e)[:300]}), 500


@app.route('/api/nube/mis')
def api_nube_mis():
    device_id = (request.args.get('device_id') or '').strip()
    if not device_id:
        return jsonify({'error': 'Falta device_id'}), 400
    try:
        import nube_db as _nube
        if not _nube.disponible():
            return jsonify({'perfiles': [], 'solo_navegador': True})
        _nube.init_db()
        return jsonify({'perfiles': _nube.mis_perfiles(device_id)})
    except Exception as e:
        return jsonify({'error': str(e)[:300]}), 500


# ---------- Fase 2: cuenta (email + contrasena) ----------
import auth_db as _auth

_COOKIE = 'dh_sesion'
_COOKIE_DIAS = 30


def _cuenta_actual():
    try:
        if not _auth.disponible():
            return None
        return _auth.cuenta_de_token(request.cookies.get(_COOKIE) or '')
    except Exception:
        return None


def _poner_cookie(resp, token):
    resp.set_cookie(_COOKIE, token, max_age=_COOKIE_DIAS * 86400, httponly=True,
                    samesite='Lax', secure=bool(request.is_secure))
    return resp


@app.route('/cuenta')
def pagina_cuenta():
    return render_template('cuenta.html')


@app.route('/alma')
def pagina_alma():
    """Vista móvil de RAVE para el APK AlmaVista."""
    return render_template('alma_vista.html')


# ---------- Panel admin secreto (solo URL larga, sin login) ----------
# No figura en ningún menú ni enlaza desde otra página. Cabecera noindex.
_ADMIN_PANEL_PATH = '/admin/dh-9f3a7c1e5b2d4f6a8c0e/panel'
import os as _os_mod

_ADMIN_DIR = _os_mod.path.dirname(_os_mod.path.abspath(__file__))
_IPS_PROPIAS_FILE = _os_mod.path.join(_ADMIN_DIR, 'ips_propias.txt')
_EMAILS_PROPIOS_FILE = _os_mod.path.join(_ADMIN_DIR, 'emails_propios.txt')

def _leer_lista(path):
    try:
        with open(path, encoding='utf-8') as f:
            return {x.strip() for x in f if x.strip()}
    except FileNotFoundError:
        return set()

def _ips_propias():
    s = _leer_lista(_IPS_PROPIAS_FILE)
    env = _os_mod.environ.get('MIS_IPS', '')
    if env:
        s |= {x.strip() for x in env.split(',') if x.strip()}
    return s

def _emails_propios():
    s = _leer_lista(_EMAILS_PROPIOS_FILE)
    env = _os_mod.environ.get('MIS_EMAILS', '')
    if env:
        s |= {x.strip().lower() for x in env.split(',') if x.strip()}
    s.add('jorgetuso@gmail.com')
    return {e.lower() for e in s}

def _marcar_ip(ip):
    ip = (ip or '').strip()
    if not ip:
        return False
    s = _leer_lista(_IPS_PROPIAS_FILE)
    if ip in s:
        return True
    try:
        with open(_IPS_PROPIAS_FILE, 'a', encoding='utf-8') as f:
            f.write(ip + '\n')
        return True
    except Exception:
        return False


@app.route('/descargar-alma')
def descargar_alma():
    """Cuenta la descarga del APK de Alma y redirige al archivo."""
    try:
        import visitas_db as _vis
        _vis.registrar_descarga(_vis.ip_real(request), 'Alma.apk',
                                (request.headers.get('User-Agent') or '')[:300])
    except Exception:
        pass
    from flask import redirect as _redir
    return _redir('https://aurahumana.onrender.com/static/alma/Alma.apk', code=302)


@app.route('/robots.txt')
def robots_txt():
    body = "User-agent: *\nAllow: /\nSitemap: https://aurahumana.onrender.com/sitemap.xml\n"
    return Response(body, mimetype='text/plain')

@app.route('/sitemap.xml')
def sitemap_xml():
    urls = ["https://aurahumana.onrender.com/"]
    body = ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' +
            ''.join(f'  <url><loc>{u}</loc></url>\n' for u in urls) +
            '</urlset>\n')
    return Response(body, mimetype='application/xml')

@app.route(_ADMIN_PANEL_PATH)
def admin_panel():
    """Dashboard de actividad de Alma: cuentas, matches, mensajes, bloqueos, reportes."""
    def esc(v):
        s = '' if v is None else str(v)
        return (s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                .replace('"', '&quot;'))

    def tabla(cols, filas):
        if not filas:
            return '<p class="vacio">Sin datos todavía.</p>'
        h = ''.join(f'<th>{esc(c)}</th>' for c in cols)
        cuerpo = ''.join('<tr>' + ''.join(f'<td>{esc(c)}</td>' for c in f) + '</tr>' for f in filas)
        return f'<table><thead><tr>{h}</tr></thead><tbody>{cuerpo}</tbody></table>'

    def barras(filas):
        if not filas:
            return '<p class="vacio">Sin datos todavia.</p>'
        tope = max((f[1] or 0) for f in filas) or 1
        out = []
        for etiqueta, valor in filas:
            pct = int(round((valor or 0) * 100 / tope))
            out.append(f'<div class="fila"><span class="etq">{esc(etiqueta)}</span>'
                       f'<span class="barra"><i style="width:{pct}%"></i></span>'
                       f'<span class="val">{esc(valor)}</span></div>')
        return '<div class="barras">' + ''.join(out) + '</div>'

    def tarjetas_html(lista):
        return ''.join(f'<div class="tarjeta"><b>{esc(v)}</b><span>{esc(t)}</span></div>' for t, v in lista)

    def tabla_visitas(cols, filas, ips_prop):
        if not filas:
            return '<p class="vacio">Sin datos todavia.</p>'
        h = ''.join(f'<th>{esc(c)}</th>' for c in cols)
        cuerpo = ''
        ncol = len(cols)
        for f in filas:
            ip = f[1] if len(f) > 1 else ''
            es_propia = (ip in ips_prop) or (len(f) > 8 and bool(f[8]))
            cls = 'propia' if es_propia else ''
            atr = f' class="{cls}"' if cls else ''
            celdas = list(f)[:ncol]
            if es_propia and len(celdas) > 1:
                celdas[1] = f"{ip} (yo)"
            cuerpo += '<tr' + atr + '>' + ''.join(f'<td>{esc(c)}</td>' for c in celdas) + '</tr>'
        return f'<table><thead><tr>{h}</tr></thead><tbody>{cuerpo}</tbody></table>'

    def num(cur, sql, args=()):
        try:
            cur.execute(sql, args)
            r = cur.fetchone()
            return r[0] if r and r[0] is not None else 0
        except Exception:
            return 0

    ips_propias = _ips_propias()
    emails_propios = _emails_propios()
    ocultar_yo = (request.args.get('ocultar') == 'yo')

    try:
        from nube_db import _conn as _c
        _buscar_init()
        c = _c()
        try:
            cur = c.cursor()
            total_cuentas = num(cur, "SELECT count(*) FROM cuentas")
            con_perfil = num(cur, "SELECT count(DISTINCT cuenta_id) FROM perfiles_cuenta")
            publicos = num(cur, "SELECT count(*) FROM perfiles_cuenta WHERE visibilidad='publico'")
            sesiones = num(cur, "SELECT count(*) FROM sesiones WHERE expira > now()")
            n_mensajes = num(cur, "SELECT count(*) FROM buscar_mensajes")
            no_leidos = num(cur, "SELECT count(*) FROM buscar_mensajes WHERE leido_at IS NULL")
            n_votos = num(cur, "SELECT count(*) FROM buscar_votos")
            n_matches = num(cur, "SELECT count(*) FROM buscar_votos v WHERE v.valor='=' AND EXISTS "
                                 "(SELECT 1 FROM buscar_votos w WHERE w.de_cuenta=v.a_cuenta "
                                 "AND w.de_nombre=v.a_nombre AND w.a_nombre=v.de_nombre AND w.valor='=')") // 2
            n_bloqueos = num(cur, "SELECT count(*) FROM buscar_bloqueos")
            n_reportes = num(cur, "SELECT count(*) FROM buscar_reportes")
            msg_24h = num(cur, "SELECT count(*) FROM buscar_mensajes WHERE created_at > now() - interval '24 hours'")

            cur.execute("SELECT id, email, created_at FROM cuentas ORDER BY id DESC LIMIT 25")
            ult_cuentas = cur.fetchall()
            ult_cuentas = [(r[0], ((r[1] or '') + ' (yo)') if ((r[1] or '').lower() in emails_propios) else r[1], r[2]) for r in (ult_cuentas or [])]
            cur.execute("SELECT c.email, count(p.id) FROM cuentas c "
                        "LEFT JOIN perfiles_cuenta p ON p.cuenta_id=c.id "
                        "GROUP BY c.id, c.email ORDER BY count(p.id) DESC, c.id DESC LIMIT 15")
            top_perfiles = cur.fetchall()
            cur.execute("SELECT m.created_at, de.email, a.email, left(m.texto, 90), m.leido_at "
                        "FROM buscar_mensajes m "
                        "JOIN cuentas de ON de.id=m.de_cuenta JOIN cuentas a ON a.id=m.a_cuenta "
                        "ORDER BY m.id DESC LIMIT 30")
            ult_msgs = cur.fetchall()
            cur.execute("SELECT r.created_at, de.email, a.email, left(r.motivo, 120) FROM buscar_reportes r "
                        "JOIN cuentas de ON de.id=r.de_cuenta JOIN cuentas a ON a.id=r.a_cuenta "
                        "ORDER BY r.id DESC LIMIT 20")
            ult_rep = cur.fetchall()
            cur.execute("SELECT b.created_at, de.email, a.email FROM buscar_bloqueos b "
                        "JOIN cuentas de ON de.id=b.de_cuenta JOIN cuentas a ON a.id=b.a_cuenta "
                        "ORDER BY b.created_at DESC LIMIT 20")
            ult_bloq = cur.fetchall()
        finally:
            c.close()
    except Exception as e:
        return Response(f'<h1>Panel admin</h1><p>Error: {esc(e)[:300]}</p>',
                        mimetype='text/html', headers={'X-Robots-Tag': 'noindex'})

    tab = (request.args.get('tab') or 'actividad').strip().lower()
    if tab not in ('actividad', 'visitas'):
        tab = 'actividad'

    if request.args.get('marcar_ip') == '1':
        _ip = (request.headers.get('X-Forwarded-For') or '').split(',')[0].strip() or (request.remote_addr or '')
        _marcar_ip(_ip)
        from flask import redirect as _redir
        return _redir(_ADMIN_PANEL_PATH + '?tab=visitas')

    # ---- Datos de visitas (entradas a la web en Render) ----
    v_tarjetas, v_por_dia, v_paths, v_paises, v_ultimas = [], [], [], [], []
    if tab == 'visitas':
        try:
            import visitas_db as _vis
            try:
                _vis.init_db()
            except Exception:
                pass
            from nube_db import _conn as _c2
            c2 = _c2()
            try:
                cur = c2.cursor()
                _ips_list = sorted(ips_propias)
                _ph = ",".join(["%s"] * len(_ips_list)) if _ips_list else ""
                _excl = (" AND ip NOT IN (" + _ph + ")") if _ips_list else ""
                _args = tuple(_ips_list)
                v_hoy = num(cur, "SELECT count(*) FROM visitas WHERE created_at::date = CURRENT_DATE" + _excl, _args)
                v_24 = num(cur, "SELECT count(*) FROM visitas WHERE created_at > now() - interval '24 hours'" + _excl, _args)
                v_7 = num(cur, "SELECT count(*) FROM visitas WHERE created_at > now() - interval '7 days'" + _excl, _args)
                v_30 = num(cur, "SELECT count(*) FROM visitas WHERE created_at > now() - interval '30 days'" + _excl, _args)
                v_total = num(cur, "SELECT count(*) FROM visitas WHERE 1=1" + _excl, _args)
                v_ips = num(cur, "SELECT count(DISTINCT ip) FROM visitas WHERE created_at > now() - interval '24 hours'" + _excl, _args)
                v_propias = num(cur, "SELECT count(*) FROM visitas WHERE es_propia=TRUE OR ip IN (" + (_ph or "NULL") + ")", _args if _ips_list else ())
                v_media = num(cur, "SELECT round(avg(duracion_seg)) FROM visitas WHERE duracion_seg IS NOT NULL AND duracion_seg > 0 AND created_at > now() - interval '30 days'")
                v_descargas = _vis.descargas_totales()
                v_tarjetas = [
                    ('Hoy', v_hoy), ('Ultimas 24 h', v_24), ('7 dias', v_7), ('30 dias', v_30),
                    ('Total historico', v_total), ('IPs distintas 24 h', v_ips),
                    ('Duracion media', f'{int(v_media)} s'),
                    ('Mias (propias)', v_propias),
                    ('Descargas APK', v_descargas),
                ]
                cur.execute("SELECT created_at::date AS d, count(*) FROM visitas WHERE created_at > now() - interval '14 days' GROUP BY d ORDER BY d DESC LIMIT 14")
                v_por_dia = [(r[0].strftime('%d/%m') if hasattr(r[0], 'strftime') else str(r[0])[:10], r[1]) for r in cur.fetchall()]
                cur.execute("SELECT COALESCE(NULLIF(path,''),'/') AS p, count(*) c FROM visitas WHERE created_at > now() - interval '30 days' GROUP BY p ORDER BY c DESC LIMIT 12")
                v_paths = cur.fetchall()
                cur.execute("SELECT COALESCE(NULLIF(pais,''),'(sin pais)') AS p, count(*) c FROM visitas GROUP BY p ORDER BY c DESC LIMIT 8")
                v_paises = cur.fetchall()
                cur.execute("SELECT to_char(created_at,'DD/MM HH24:MI'), ip, path, COALESCE(pais,''), duracion_seg, left(COALESCE(referer,''), 40), left(COALESCE(user_agent,''), 45), es_propia FROM visitas ORDER BY id DESC LIMIT 40")
                v_ultimas = cur.fetchall()
                v_descargas_dia = _vis.descargas_por_dia(14)
            finally:
                c2.close()
        except Exception as e:
            v_tarjetas = [('Error', str(e)[:80])]

        _v_mostrar = [r for r in v_ultimas if not (ocultar_yo and ((r[1] in ips_propias) or (len(r) > 8 and r[8])))] if ips_propias or True else v_ultimas
        _toggle_url = _ADMIN_PANEL_PATH + '?tab=visitas' + ('' if ocultar_yo else '&ocultar=yo')
        _toggle_txt = 'Mostrar todas' if ocultar_yo else 'Ocultar mis visitas'
        cuerpo = (
            f'<div class="tarjetas">{tarjetas_html(v_tarjetas)}</div>'
            f'<p style="font-size:12px;margin:6px 0 14px;color:#666">IPs propias: {len(ips_propias)}  -  <a href="{_toggle_url}">{_toggle_txt}</a>  -  <a href="{_ADMIN_PANEL_PATH}?tab=visitas&marcar_ip=1">Marcar mi IP actual</a></p>'
            f'<h2>Entradas por dia (ultimos 14)</h2>{barras(v_por_dia)}'
            f'<h2>Descargas APK por dia (ultimos 14)</h2>{barras(v_descargas_dia)}'
            f'<h2>Paginas mas vistas (30 dias)</h2>{barras(v_paths)}'
            f'<h2>Paises</h2>{tabla(["Pais", "Entradas"], v_paises)}'
            f'<h2>Ultimas entradas</h2>'
            f'{tabla_visitas(["Fecha", "IP", "Ruta", "Pais", "Duracion", "Origen", "Navegador"], _v_mostrar, ips_propias)}'
            )
    else:
        cuerpo = (
            f'<div class="tarjetas">{tarjetas_html(tarjetas)}</div>'
            f'<h2>Últimas cuentas</h2>{tabla(["ID", "Correo", "Creada"], ult_cuentas)}'
            f'<h2>Mensajes recientes</h2>{tabla(["Fecha", "De", "Para", "Texto", "Leído"], ult_msgs)}'
            f'<h2>Usuarios con más perfiles</h2>{tabla(["Correo", "Perfiles"], top_perfiles)}'
            f'<h2>Reportes</h2>{tabla(["Fecha", "Reporta", "Reportado", "Motivo"], ult_rep)}'
            f'<h2>Bloqueos</h2>{tabla(["Fecha", "Bloquea", "Bloqueado"], ult_bloq)}'
        )

    html = f"""<!doctype html><html lang="es"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>Alma · dashboard</title>
<style>
body{{font-family:system-ui,Segoe UI,Arial,sans-serif;margin:0;background:#f7f6fc;color:#1c1b2a}}
header{{background:#6c4cf1;color:#fff;padding:16px 20px}}
header h1{{margin:0;font-size:20px}} header p{{margin:4px 0 0;font-size:12px;opacity:.85}}
main{{padding:20px;max-width:1200px;margin:0 auto}}
h2{{font-size:15px;margin:28px 0 10px;color:#4a2fd6}}
.tabs{{background:#fff;display:flex;gap:4px;padding:8px 20px;border-bottom:1px solid #e6e2f7}}
.tabs a{{padding:8px 14px;border-radius:8px;text-decoration:none;color:#4a2fd6;font-size:13px}}
.tabs a.activo{{background:#6c4cf1;color:#fff;font-weight:600}}
.tarjetas{{display:flex;flex-wrap:wrap;gap:10px}}
.tarjeta{{background:#fff;border-radius:10px;padding:12px 16px;min-width:120px;box-shadow:0 1px 3px rgba(0,0,0,.08)}}
.tarjeta b{{display:block;font-size:24px;line-height:1.2}}
.tarjeta span{{font-size:11px;color:#666}}
table{{width:100%;border-collapse:collapse;background:#fff;border-radius:10px;overflow:hidden;
box-shadow:0 1px 3px rgba(0,0,0,.08);font-size:12px}}
th{{background:#eee9ff;text-align:left;padding:8px;font-weight:600}}
td{{padding:7px 8px;border-top:1px solid #f0eefb;vertical-align:top;word-break:break-word}}
tr.propia td{{background:#f3f0ff;color:#6b5a7e;font-style:italic}}
.vacio{{color:#777;font-size:12px}}
.barras{{background:#fff;border-radius:10px;padding:12px 16px;box-shadow:0 1px 3px rgba(0,0,0,.08)}}
.fila{{display:flex;align-items:center;gap:10px;margin:5px 0;font-size:12px}}
.fila .etq{{width:120px;flex:0 0 120px;color:#444}}
.fila .barra{{flex:1;background:#f0eefb;border-radius:6px;height:14px;overflow:hidden}}
.fila .barra i{{display:block;height:100%;background:#6c4cf1;border-radius:6px}}
.fila .val{{width:48px;text-align:right;font-weight:600;color:#4a2fd6}}
</style>
<header><h1>Alma · dashboard</h1><p>Datos en vivo de la base Neon · esta página no está enlazada en el sitio</p></header>
<nav class="tabs">
  <a class="{clase_act}" href="{_ADMIN_PANEL_PATH}?tab=actividad">Actividad</a>
  <a class="{clase_vis}" href="{_ADMIN_PANEL_PATH}?tab=visitas">Visitas (Render)</a>
</nav>
<main>
{cuerpo}
</main></html>"""
    return Response(html, mimetype='text/html',
                    headers={'X-Robots-Tag': 'noindex, nofollow', 'Cache-Control': 'no-store'})


@app.route('/api/cuenta/estado')
def api_cuenta_estado():
    try:
        conf = _auth.disponible()
    except Exception:
        conf = False
    ct = _cuenta_actual() if conf else None
    return jsonify({'configurado': conf, 'logueado': bool(ct),
                    'email': (ct or {}).get('email', '')})


@app.route('/api/cuenta/registro', methods=['POST'])
def api_cuenta_registro():
    data = request.get_json(force=True, silent=True) or {}
    try:
        if not _auth.disponible():
            return jsonify({'error': 'Neon no configurado (falta DATABASE_URL)'}), 503
        _auth.init_db()
        cuenta_id, codigo = _auth.crear_cuenta(data.get('email') or '', data.get('pw') or '')
        token = _auth.crear_sesion(cuenta_id)
        email = _auth._norm_email(data.get('email'))
        try:
            import mail_cuenta
            mail_ok = mail_cuenta.enviar_codigo(email, codigo)
        except Exception:
            mail_ok = False
        return _poner_cookie(jsonify({'ok': True, 'email': email,
                                      'codigo_recuperacion': codigo,
                                      'codigo_enviado': bool(mail_ok)}), token)
    except ValueError as e:
        return jsonify({'error': str(e)}), 409
    except Exception as e:
        return jsonify({'error': str(e)[:300]}), 500


@app.route('/api/cuenta/login', methods=['POST'])
def api_cuenta_login():
    data = request.get_json(force=True, silent=True) or {}
    try:
        if not _auth.disponible():
            return jsonify({'error': 'Neon no configurado (falta DATABASE_URL)'}), 503
        _auth.init_db()
        cuenta_id = _auth.login(data.get('email') or '', data.get('pw') or '')
        if not cuenta_id:
            return jsonify({'error': 'Correo o contraseña incorrectos'}), 401
        token = _auth.crear_sesion(cuenta_id)
        return _poner_cookie(jsonify({'ok': True}), token)
    except Exception as e:
        return jsonify({'error': str(e)[:300]}), 500


@app.route('/api/cuenta/logout', methods=['POST'])
def api_cuenta_logout():
    try:
        _auth.cerrar_sesion(request.cookies.get(_COOKIE) or '')
    except Exception:
        pass
    resp = jsonify({'ok': True})
    resp.delete_cookie(_COOKIE)
    return resp


@app.route('/api/cuenta/recuperar', methods=['POST'])
def api_cuenta_recuperar():
    data = request.get_json(force=True, silent=True) or {}
    try:
        if not _auth.disponible():
            return jsonify({'error': 'Neon no configurado'}), 503
        ok = _auth.recuperar(data.get('email') or '', data.get('codigo') or '', data.get('nueva') or '')
        if not ok:
            return jsonify({'error': 'Correo, código o contraseña inválidos'}), 401
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'error': str(e)[:300]}), 500


@app.route('/api/cuenta/cambiar_correo', methods=['POST'])
def api_cuenta_cambiar_correo():
    data = request.get_json(force=True, silent=True) or {}
    try:
        if not _auth.disponible():
            return jsonify({'error': 'Neon no configurado'}), 503
        try:
            ok = _auth.cambiar_email(data.get('email') or '', data.get('codigo') or '',
                                     data.get('nuevo') or '')
        except ValueError as e:
            return jsonify({'error': str(e)}), 409
        if not ok:
            return jsonify({'error': 'Correo o código inválidos'}), 401
        return jsonify({'ok': True, 'email': _auth._norm_email(data.get('nuevo'))})
    except Exception as e:
        return jsonify({'error': str(e)[:300]}), 500


@app.route('/api/cuenta/mis')
def api_cuenta_mis():
    ct = _cuenta_actual()
    if not ct:
        return jsonify({'error': 'No logueado'}), 401
    try:
        return jsonify({'email': ct['email'], 'perfiles': _auth.perfiles_de(ct['id']),
                        'yo': _auth.get_yo(ct['id'])})
    except Exception as e:
        return jsonify({'error': str(e)[:300]}), 500


@app.route('/api/cuenta/yo', methods=['GET', 'POST'])
def api_cuenta_yo():
    """Yo persistido en Neon: GET lo lee, POST lo fija (y deja pública la persona)."""
    ct = _cuenta_actual()
    if not ct:
        return jsonify({'error': 'No logueado'}), 401
    try:
        if request.method == 'GET':
            return jsonify({'ok': True, 'yo': _auth.get_yo(ct['id'])})
        data = request.get_json(force=True, silent=True) or {}
        nombre = str(data.get('nombre') or data.get('yo') or '').strip()
        if not nombre:
            return jsonify({'error': 'Falta nombre'}), 400
        perfiles = _auth.perfiles_de(ct['id'])
        previo = next((p for p in perfiles
                       if str(p.get('nombre') or '').strip().lower() == nombre.lower()), None)
        if not previo:
            return jsonify({'error': f'"{nombre}" no está en tu cuenta. Usá Agregar para crearla.'}), 404
        _auth.set_yo(ct['id'], previo.get('nombre') or nombre)
        perfil = dict(previo)
        perfil['visibilidad'] = 'publico'
        _auth.subir_perfil(ct['id'], perfil)
        g.perfiles_cuenta = None
        return jsonify({'ok': True, 'yo': previo.get('nombre') or nombre})
    except Exception as e:
        return jsonify({'error': str(e)[:300]}), 500


@app.route('/api/cuenta/subir', methods=['POST'])
def api_cuenta_subir():
    """Fija visibilidad de una persona. Con fase 3 el alta/edición ya guarda en Neon."""
    ct = _cuenta_actual()
    if not ct:
        return jsonify({'error': 'No logueado'}), 401
    data = request.get_json(force=True, silent=True) or {}
    nombre = str(data.get('nombre') or data.get('persona') or '').strip()
    if not nombre:
        return jsonify({'error': 'Falta nombre'}), 400
    try:
        perfiles = _auth.perfiles_de(ct['id'])
        previo = next((p for p in perfiles
                       if str(p.get('nombre') or '').strip().lower() == nombre.lower()), None)
        if not previo:
            return jsonify({'error': f'"{nombre}" no está en tu cuenta. Usá Agregar para crearla.'}), 404
        perfil = dict(previo)
        perfil['visibilidad'] = str(data.get('visibilidad') or previo.get('visibilidad') or 'privado')
        if 'bio' in data:
            dj = perfil.get('datos_json')
            if isinstance(dj, str):
                import json as _jb
                try:
                    dj = _jb.loads(dj)
                except Exception:
                    dj = {}
            if not isinstance(dj, dict):
                dj = {}
            dj['bio'] = str(data.get('bio') or '').strip()[:280]
            perfil['datos_json'] = dj
        _auth.subir_perfil(ct['id'], perfil)
        g.perfiles_cuenta = None
        return jsonify({'ok': True, 'nombre': nombre, 'visibilidad': perfil['visibilidad']})
    except Exception as e:
        return jsonify({'error': str(e)[:300]}), 500


@app.route('/api/cuenta/bajar', methods=['POST'])
def api_cuenta_bajar():
    """Con fase 3 las personas ya viven en Neon por cuenta: no hay que copiarlas al servidor."""
    ct = _cuenta_actual()
    if not ct:
        return jsonify({'error': 'No logueado'}), 401
    try:
        perfiles = _auth.perfiles_de(ct['id'])
    except Exception as e:
        return jsonify({'error': str(e)[:300]}), 500
    nombres = [str(p.get('nombre') or '').strip() for p in perfiles if str(p.get('nombre') or '').strip()]
    return jsonify({'ok': True, 'creadas': [], 'ya_estaban': nombres,
                    'errores': [], 'personas': nombres, 'en_nube': True})


@app.route('/api/cuenta/borrar', methods=['POST'])
def api_cuenta_borrar():
    ct = _cuenta_actual()
    if not ct:
        return jsonify({'error': 'No logueado'}), 401
    data = request.get_json(force=True, silent=True) or {}
    nombre = str(data.get('nombre') or '').strip()
    if not nombre:
        return jsonify({'error': 'Falta nombre'}), 400
    try:
        return jsonify({'ok': True, 'borrados': _auth.borrar_perfil(ct['id'], nombre)})
    except Exception as e:
        return jsonify({'error': str(e)[:300]}), 500


@app.route('/api/cuenta/exportar')
def api_cuenta_exportar():
    """Descarga un CSV (mismo formato que datos.csv) con las personas de la cuenta."""
    import csv as _csv
    import io as _io2
    ct = _cuenta_actual()
    if not ct:
        return jsonify({'error': 'No logueado'}), 401
    try:
        perfiles = _auth.perfiles_de(ct['id'])
    except Exception as e:
        return jsonify({'error': str(e)[:300]}), 500
    buf = _io2.StringIO()
    w = _csv.writer(buf, delimiter=';')
    w.writerow(['Nombre', 'Puerta', 'Linea', 'C/I', 'Fecha', 'Hora', 'Lugar'])
    for p in perfiles:
        dj = _dj(p)
        nombre = str(p.get('nombre') or '').strip()
        if not nombre:
            continue
        fecha, hora, lugar = p.get('fecha') or '', p.get('hora') or '', p.get('lugar') or ''
        for campo, estado in (('inconscientes', 'Inconsciente'), ('conscientes', 'Consciente')):
            lista = dj.get(campo) or []
            lineas = dj.get(campo + '_lineas') or []
            for i, g in enumerate(lista):
                lin = lineas[i] if i < len(lineas) else ''
                w.writerow([nombre, g, '' if lin in (None, '') else lin, estado, fecha, hora, lugar])
    nombre_archivo = f"rave_{str(ct['email']).split('@')[0]}.csv"
    resp = app.response_class('\ufeff' + buf.getvalue(), mimetype='text/csv')
    resp.headers['Content-Disposition'] = f'attachment; filename="{nombre_archivo}"'
    return resp


def _parse_csv_personas(texto):
    """CSV (; o ,) con Nombre;Puerta;Linea;C/I[;Fecha;Hora;Lugar] -> {nombre: {...}}."""
    import csv as _csv
    import io as _io2
    texto = (texto or '').lstrip('\ufeff')
    lineas = [ln for ln in texto.splitlines() if ln.strip()]
    if not lineas:
        return {}, 'CSV vacío'
    muestra = lineas[0]
    sep = max((';', ',', '\t'), key=lambda c: muestra.count(c))
    if muestra.count(sep) == 0:
        sep = ';'
    filas = list(_csv.reader(_io2.StringIO(texto), delimiter=sep))
    if not filas:
        return {}, 'CSV vacío'
    head = [str(c or '').strip().lower().replace('í', 'i') for c in filas[0]]

    def _idx(*nombres):
        for n in nombres:
            if n in head:
                return head.index(n)
        return None

    i_nom = _idx('nombre', 'name')
    i_pue = next((i for i, c in enumerate(head) if 'puerta' in c), None)
    i_lin = next((i for i, c in enumerate(head) if 'linea' in c), None)
    i_ci = _idx('c/i', 'ci', 'c-i')
    i_fec, i_hor = _idx('fecha'), _idx('hora')
    i_lug = _idx('lugar')
    if i_nom is None or i_pue is None or i_ci is None:
        return {}, 'Falta alguna columna: Nombre, Puerta, C/I (formato datos.csv)'
    out = {}
    for r in filas[1:]:
        def _g(i):
            return str(r[i] or '').strip() if (i is not None and i < len(r)) else ''
        nombre = _g(i_nom)
        if not nombre:
            continue
        try:
            puerta = int(float(_g(i_pue).replace(',', '.').split('.')[0]))
        except (ValueError, TypeError):
            continue
        if not 1 <= puerta <= 64:
            continue
        linea = None
        s_lin = _g(i_lin)
        if s_lin:
            try:
                n = int(float(s_lin))
                linea = n if 1 <= n <= 6 else None
            except (ValueError, TypeError):
                linea = None
        estado = 'inconsciente' if _g(i_ci).lower().startswith('incons') else 'consciente'
        base = 'inconscientes' if estado == 'inconsciente' else 'conscientes'
        d = out.setdefault(nombre, {'inconscientes': [], 'conscientes': [],
                                    'inconscientes_lineas': [], 'conscientes_lineas': [],
                                    'fecha': '', 'hora': '', 'lugar': ''})
        d[base].append(puerta)
        d[base + '_lineas'].append(linea)
        if not d['fecha'] and _g(i_fec):
            d['fecha'] = _g(i_fec)
        if not d['hora'] and _g(i_hor):
            d['hora'] = _g(i_hor)
        if not d['lugar'] and _g(i_lug):
            d['lugar'] = _g(i_lug)
    return out, None


@app.route('/api/cuenta/importar', methods=['POST'])
def api_cuenta_importar():
    """Importa un CSV (formato datos.csv) a la cuenta. Acepta archivo o texto JSON."""
    ct = _cuenta_actual()
    if not ct:
        return jsonify({'error': 'No logueado'}), 401
    texto = ''
    try:
        if 'archivo' in request.files:
            texto = request.files['archivo'].read().decode('utf-8', 'replace')
        else:
            data = request.get_json(force=True, silent=True) or {}
            texto = data.get('csv') or ''
    except Exception as e:
        return jsonify({'error': f'No se pudo leer el archivo: {e}'}), 400
    personas, err = _parse_csv_personas(texto)
    if err:
        return jsonify({'error': err}), 400
    if not personas:
        return jsonify({'error': 'No se encontraron personas en el CSV'}), 400
    existentes = {str(p.get('nombre') or '').strip().lower() for p in (_auth.perfiles_de(ct['id']) or [])}
    creadas, actualizadas, errores = [], [], []
    for nombre, d in personas.items():
        payload = {'nombre': nombre,
                   'inconscientes': d['inconscientes'], 'conscientes': d['conscientes'],
                   'inconscientes_lineas': d['inconscientes_lineas'],
                   'conscientes_lineas': d['conscientes_lineas'],
                   'fecha': d['fecha'], 'hora': d['hora'], 'lugar': d['lugar']}
        perfil, e = _cuenta_perfil_desde_payload(payload, nombre)
        if e:
            # Tolera personas con cantidad de puertas distinta de 13 (tránsitos, datos viejos).
            if not d['inconscientes'] or not d['conscientes']:
                errores.append({'nombre': nombre, 'error': e})
                continue
            perfil = {'nombre': nombre, 'fecha': d['fecha'], 'hora': d['hora'], 'lugar': d['lugar'],
                      'lat': None, 'lon': None, 'tz': None, 'tz_name': '',
                      'visibilidad': 'privado',
                      'datos_json': {'inconscientes': d['inconscientes'],
                                     'conscientes': d['conscientes'],
                                     'inconscientes_lineas': d['inconscientes_lineas'],
                                     'conscientes_lineas': d['conscientes_lineas'],
                                     'perfil': _perfil_de_lineas(
                                         (d['conscientes_lineas'] or [None])[0],
                                         (d['inconscientes_lineas'] or [None])[0]),
                                     'test': {}}}
        try:
            _auth.subir_perfil(ct['id'], perfil)
            (actualizadas if nombre.lower() in existentes else creadas).append(nombre)
            existentes.add(nombre.lower())
        except Exception as e2:
            errores.append({'nombre': nombre, 'error': str(e2)[:150]})
    g.perfiles_cuenta = None
    return jsonify({'ok': True, 'creadas': creadas, 'actualizadas': actualizadas,
                    'errores': errores, 'total': len(personas)})


# ---------- Fase 4: Buscar personas (= / X, match, chat, bloqueo, reporte) ----------
_BUSCAR_OK = False
_BUSCAR_RATE = {}


def _buscar_init():
    global _BUSCAR_OK
    if _BUSCAR_OK:
        return
    try:
        from pathlib import Path as _P
        from nube_db import _conn as _c
        sql = (_P(__file__).parent / 'schema_fase4.sql').read_text(encoding='utf-8')
        c = _c()
        try:
            cur = c.cursor()
            cur.execute(sql)
            c.commit()
        finally:
            c.close()
        _BUSCAR_OK = True
    except Exception:
        pass


def _buscar_foto_ok(foto):
    f = str(foto or '').strip()
    if not f or len(f) > 2000:
        return ''
    if f.startswith('/publicos/'):
        return f
    if f.startswith('https://') and len(f) < 500:
        return f
    return ''


def _buscar_limite(clave, max_n, ventana_seg):
    import time as _t
    ahora = _t.time()
    lista = _BUSCAR_RATE.get(clave) or []
    lista = [x for x in lista if ahora - x < ventana_seg]
    if len(lista) >= max_n:
        _BUSCAR_RATE[clave] = lista
        return False
    lista.append(ahora)
    _BUSCAR_RATE[clave] = lista
    return True


def _buscar_familia_tipo(tipo):
    """Familia base del tipo: 'Generador Manifestante' -> 'Generador'."""
    t = str(tipo or '').strip().lower()
    for fam in ('generador', 'proyector', 'manifestador', 'reflector'):
        if t.startswith(fam):
            return fam
    return ''


def _buscar_match_mutuo(cur, mi_cuenta, mi_nombre, su_nombre):
    """= mutuo entre dos personas, aunque el mismo nombre esté público en
    varias cuentas (homónimos de prueba). El par se compara por nombre."""
    cur.execute(
        "SELECT 1 FROM buscar_votos m "
        "JOIN buscar_votos o ON o.de_nombre=m.a_nombre AND o.a_nombre=m.de_nombre "
        "                   AND o.valor='=' AND o.de_cuenta<>m.de_cuenta "
        "WHERE m.de_cuenta=%s AND m.de_nombre=%s AND m.a_nombre=%s AND m.valor='=' "
        "AND EXISTS (SELECT 1 FROM perfiles_cuenta p WHERE p.cuenta_id=o.de_cuenta "
        "            AND p.nombre=o.de_nombre AND p.visibilidad='publico') LIMIT 1",
        (mi_cuenta, mi_nombre, su_nombre))
    return bool(cur.fetchone())


def _buscar_ficha(dj):
    try:
        incon = [int(x) for x in (dj.get('inconscientes') or [])]
        consc = [int(x) for x in (dj.get('conscientes') or [])]
    except Exception:
        incon, consc = [], []
    puertas = sorted(set(incon) | set(consc))
    try:
        canales = _hd_canales_de_puertas(puertas)
    except Exception:
        canales = []
    try:
        centros = _hd_centros_definidos(canales)
        tipo, _aut = _hd_tipo_autoridad(centros, canales)
    except Exception:
        tipo = ''
    perfil = dj.get('perfil') or _perfil_de_lineas(
        (dj.get('conscientes_lineas') or [None])[0] if dj.get('conscientes_lineas') else None,
        (dj.get('inconscientes_lineas') or [None])[0] if dj.get('inconscientes_lineas') else None) or ''
    return {'canales': canales, 'tipo': tipo or '', 'perfil': perfil or '',
            'foto': _buscar_foto_ok(dj.get('foto'))}


@app.route('/buscar')
def pagina_buscar():
    return render_template('buscar.html')


@app.route('/api/buscar/mis')
def api_buscar_mis():
    ct = _cuenta_actual()
    if not ct:
        return jsonify({'error': 'No logueado'}), 401
    try:
        perfiles = _auth.perfiles_de(ct['id'])
    except Exception as e:
        return jsonify({'error': str(e)[:200]}), 500
    pubs = [p.get('nombre') for p in perfiles if (p.get('visibilidad') or '') == 'publico']
    todas = [p.get('nombre') for p in perfiles]
    return jsonify({'mis': pubs, 'todas': todas})


@app.route('/api/buscar/ficha')
def api_buscar_ficha():
    """Ficha pública de una persona: foto, tipo, perfil, canales y centros.
    Solo datos que ya se muestran en el buscador; nunca fecha, hora ni lugar."""
    ct = _cuenta_actual()
    if not ct:
        return jsonify({'error': 'No logueado'}), 401
    try:
        cuenta = int(request.args.get('cuenta') or 0)
    except Exception:
        return jsonify({'error': 'Cuenta inválida'}), 400
    nombre = (request.args.get('nombre') or '').strip()[:80]
    base = (request.args.get('base') or '').strip()[:80]
    if not cuenta or not nombre:
        return jsonify({'error': 'Falta la persona'}), 400
    try:
        _buscar_init()
        from nube_db import _conn as _c
        c = _c()
        try:
            cur = c.cursor()
            cur.execute("SELECT datos_json FROM perfiles_cuenta WHERE cuenta_id=%s AND nombre=%s "
                        "AND visibilidad='publico'", (cuenta, nombre))
            r = cur.fetchone()
            if not r:
                return jsonify({'error': 'Esa persona no es pública'}), 404
            dj = r[0]
            if isinstance(dj, str):
                import json as _j
                try:
                    dj = _j.loads(dj)
                except Exception:
                    dj = {}
            comunes = []
            if base:
                cur.execute("SELECT datos_json FROM perfiles_cuenta WHERE cuenta_id=%s AND nombre=%s "
                            "AND visibilidad='publico'", (ct['id'], base))
                rb = cur.fetchone()
                if rb:
                    djb = rb[0]
                    if isinstance(djb, str):
                        import json as _j2
                        try:
                            djb = _j2.loads(djb)
                        except Exception:
                            djb = {}
                    fb = _buscar_ficha(djb or {})
                    mios = set(_hd_norm_canal(x) for x in fb['canales'])
                    f0 = _buscar_ficha(dj or {})
                    comunes = [x for x in f0['canales'] if _hd_norm_canal(x) in mios]
        finally:
            c.close()
        f = _buscar_ficha(dj or {})
        dd = dj or {}
        return jsonify({'nombre': nombre, 'foto': f['foto'], 'tipo': f['tipo'],
                        'perfil': f['perfil'], 'canales': f['canales'],
                        'centros': sorted(_hd_centros_definidos(f['canales'])),
                        'bio': str((dd or {}).get('bio') or '').strip()[:280],
                        'comunes': comunes,
                        'inconscientes': dd.get('inconscientes') or [],
                        'conscientes': dd.get('conscientes') or [],
                        'inconscientes_lineas': dd.get('inconscientes_lineas') or [],
                        'conscientes_lineas': dd.get('conscientes_lineas') or []})
    except Exception as e:
        return jsonify({'error': str(e)[:300]}), 500


@app.route('/mapa.svg')
def mapa_svg_buscar():
    return Response(cargar_svg(), mimetype='image/svg+xml')


@app.route('/api/buscar/candidatos')
def api_buscar_candidatos():
    ct = _cuenta_actual()
    if not ct:
        return jsonify({'error': 'No logueado'}), 401
    base = (request.args.get('base') or '').strip()
    solo_nuevos = (request.args.get('solo_nuevos') or '1') == '1'
    por_nombre = (request.args.get('q') or '').strip()[:80]
    try:
        _buscar_init()
        from nube_db import _conn as _c
        mias = {str(p.get('nombre') or '').strip().lower(): p for p in _auth.perfiles_de(ct['id'])}
        b = mias.get(base.lower()) if base else None
        if not b:
            return jsonify({'error': 'Elegí tu persona pública base'}), 400
        if (b.get('visibilidad') or '') != 'publico':
            return jsonify({'error': 'Tu persona base debe estar en público (Mi cuenta)'}), 400
        fb = _buscar_ficha(_dj(b))
        set_b = set(_hd_norm_canal(c) for c in fb['canales'])
        c = _c()
        try:
            cur = c.cursor()
            if por_nombre:
                cur.execute("SELECT cuenta_id, nombre, datos_json FROM perfiles_cuenta "
                            "WHERE visibilidad='publico' AND cuenta_id<>%s AND nombre ILIKE %s "
                            "ORDER BY nombre LIMIT 60", (ct['id'], '%' + por_nombre + '%'))
            else:
                cur.execute("SELECT cuenta_id, nombre, datos_json FROM perfiles_cuenta "
                            "WHERE visibilidad='publico' AND cuenta_id<>%s",
                            (ct['id'],))
            filas = cur.fetchall()
            cur.execute("SELECT a_cuenta, a_nombre FROM buscar_votos WHERE de_cuenta=%s AND de_nombre=%s",
                        (ct['id'], b.get('nombre')))
            votados = {(r[0], str(r[1]).lower()) for r in cur.fetchall()}
            cur.execute("SELECT de_cuenta FROM buscar_bloqueos WHERE a_cuenta=%s", (ct['id'],))
            me_bloq = {r[0] for r in cur.fetchall()}
            cur.execute("SELECT a_cuenta FROM buscar_bloqueos WHERE de_cuenta=%s", (ct['id'],))
            yo_bloq = {r[0] for r in cur.fetchall()}
            # Cuentas personales = pocas fichas públicas. En producción cada
            # cuenta tendrá una persona, así que esto solo separa datos de prueba
            # (cuentas con cientos de fichas) de personas reales.
            cur.execute("SELECT cuenta_id, COUNT(*) FROM perfiles_cuenta "
                        "WHERE visibilidad='publico' GROUP BY cuenta_id")
            cuantas = {r[0]: r[1] for r in cur.fetchall()}
        finally:
            c.close()
        con_canales, solo_afines = [], []
        for cid, nom, dj in filas:
            if cid in me_bloq or cid in yo_bloq:
                continue
            if solo_nuevos and (cid, str(nom).lower()) in votados:
                continue
            if isinstance(dj, str):
                try:
                    import json as _j
                    dj = _j.loads(dj)
                except Exception:
                    dj = {}
            f = _buscar_ficha(dj or {})
            chs = [_hd_norm_canal(x) for x in f['canales']]
            comunes = [x for x in chs if x in set_b]
            tipo_match = bool(f['tipo'] and f['tipo'] == fb['tipo'])
            perfil_match = bool(f['perfil'] and f['perfil'] == fb['perfil'])
            fam_match = bool(_buscar_familia_tipo(f['tipo'])
                             and _buscar_familia_tipo(f['tipo']) == _buscar_familia_tipo(fb['tipo']))
            # Sin canales en común solo entra si comparte familia de tipo:
            # así el resultado sigue siendo afinidad, no una lista al azar.
            # En la búsqueda por nombre se muestran todos los que coinciden.
            if not por_nombre and not comunes and not fam_match:
                continue
            prio = (3 if (tipo_match and perfil_match) else
                    2 if tipo_match else 1 if perfil_match else 0)
            diff = len(set(chs)) - len(comunes)
            frio = (len(set(chs)) == len(set_b)) and (len(comunes) == len(set_b))
            item = {'cuenta_id': cid, 'nombre': nom, 'canales': chs,
                    'comunes': len(comunes), 'tipo': f['tipo'], 'perfil': f['perfil'],
                    'foto': f['foto'], 'tipo_match': tipo_match,
                    'centros': sorted(_hd_centros_definidos(f['canales'])),
                    'bio': str((dj or {}).get('bio') or '').strip()[:280],
                    'perfil_match': perfil_match, 'fam_match': fam_match,
                    'prio': prio, 'diff': diff, 'frio': frio,
                    'personal': cuantas.get(cid, 1) <= 3}
            (con_canales if comunes else solo_afines).append(item)

        # Cuentas personales primero (una persona real gana a un catálogo de
        # fichas de prueba); dentro de cada grupo manda la afinidad.
        def _orden(x, sin_canales):
            return (0 if x['personal'] else 1, 0 if sin_canales else 0,
                    -x['comunes'], -x['frio'], -x['prio'], x['diff'], x['nombre'])

        con_canales.sort(key=lambda x: _orden(x, False))
        solo_afines.sort(key=lambda x: _orden(x, True))

        def _sin_repetidos(lista):
            """Un solo resultado por nombre: si hay homónimos en varias cuentas,
            queda el mejor ubicado (prefiere el que tiene foto)."""
            vistos, out = {}, []
            for it in lista:
                k = str(it['nombre']).strip().lower()
                if k not in vistos:
                    vistos[k] = len(out)
                    out.append(it)
                elif it['foto'] and not out[vistos[k]]['foto']:
                    out[vistos[k]] = it
            return out

        con_canales = _sin_repetidos(con_canales)
        solo_afines = _sin_repetidos(solo_afines)
        if por_nombre:
            todos = con_canales + solo_afines
            todos.sort(key=lambda x: (0 if x['personal'] else 1, -x['comunes'], x['nombre']))
            return jsonify({'candidatos': todos[:60], 'afinidad': [],
                            'total': len(todos), 'base': b.get('nombre'),
                            'por_nombre': por_nombre})
        # Una sola lista: personas de cuentas personales primero y, dentro de
        # cada grupo, los que más canales comparten. Así una persona real no
        # queda enterrada por un catálogo de fichas.
        todos = con_canales + solo_afines
        todos.sort(key=lambda x: (0 if x['personal'] else 1, -x['comunes'],
                                  -x['frio'], -x['prio'], x['diff'], x['nombre']))
        return jsonify({'candidatos': todos[:60], 'afinidad': [],
                        'total': len(todos), 'base': b.get('nombre')})
    except Exception as e:
        return jsonify({'error': str(e)[:300]}), 500


@app.route('/api/buscar/votos')
def api_buscar_votos():
    """Votos dados por la cuenta (para revisar a quién se le dio X o =)."""
    ct = _cuenta_actual()
    if not ct:
        return jsonify({'error': 'No logueado'}), 401
    base = (request.args.get('base') or '').strip()
    try:
        _buscar_init()
        from nube_db import _conn as _c
        c = _c()
        try:
            cur = c.cursor()
            if base:
                cur.execute("SELECT a_cuenta, a_nombre, valor FROM buscar_votos "
                            "WHERE de_cuenta=%s AND de_nombre=%s ORDER BY a_nombre",
                            (ct['id'], base))
            else:
                cur.execute("SELECT a_cuenta, a_nombre, valor FROM buscar_votos "
                            "WHERE de_cuenta=%s ORDER BY a_nombre", (ct['id'],))
            votos = [{'cuenta_id': r[0], 'nombre': str(r[1]), 'valor': r[2]}
                     for r in cur.fetchall()]
        finally:
            c.close()
        return jsonify({'votos': votos, 'base': base})
    except Exception as e:
        return jsonify({'error': str(e)[:300]}), 500


@app.route('/api/buscar/voto_borrar', methods=['POST'])
def api_buscar_voto_borrar():
    """Borra un voto para limpiar la lista de votados (se puede volver a votar)."""
    ct = _cuenta_actual()
    if not ct:
        return jsonify({'error': 'No logueado'}), 401
    d = request.get_json(force=True, silent=True) or {}
    try:
        a_cuenta = int(d.get('a_cuenta'))
    except Exception:
        return jsonify({'error': 'Falta destinatario'}), 400
    a_nombre = str(d.get('a_nombre') or '').strip()
    de_nombre = str(d.get('de_nombre') or d.get('base') or '').strip()
    if not a_nombre or not de_nombre:
        return jsonify({'error': 'Falta la persona'}), 400
    try:
        _buscar_init()
        from nube_db import _conn as _c
        c = _c()
        try:
            cur = c.cursor()
            cur.execute("DELETE FROM buscar_votos WHERE de_cuenta=%s AND de_nombre=%s "
                        "AND a_cuenta=%s AND a_nombre=%s",
                        (ct['id'], de_nombre, a_cuenta, a_nombre))
            c.commit()
        finally:
            c.close()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'error': str(e)[:300]}), 500


@app.route('/api/buscar/votar', methods=['POST'])
def api_buscar_votar():
    ct = _cuenta_actual()
    if not ct:
        return jsonify({'error': 'No logueado'}), 401
    if not _buscar_limite(f"voto:{ct['id']}", 100, 3600):
        return jsonify({'error': 'Límite de votos por hora alcanzado'}), 429
    d = request.get_json(force=True, silent=True) or {}
    try:
        a_cuenta = int(d.get('a_cuenta'))
    except Exception:
        return jsonify({'error': 'Falta destinatario'}), 400
    a_nombre = str(d.get('a_nombre') or '').strip()
    de_nombre = str(d.get('de_nombre') or d.get('base') or '').strip()
    valor = str(d.get('valor') or '').strip()
    if valor not in ('=', 'X') or not a_nombre or not de_nombre or a_cuenta == ct['id']:
        return jsonify({'error': 'Voto inválido'}), 400
    try:
        _buscar_init()
        from nube_db import _conn as _c
        c = _c()
        try:
            cur = c.cursor()
            cur.execute("SELECT visibilidad FROM perfiles_cuenta WHERE cuenta_id=%s AND nombre=%s",
                        (ct['id'], de_nombre))
            r = cur.fetchone()
            if not r or (r[0] or '') != 'publico':
                return jsonify({'error': 'Tu persona base debe ser pública'}), 400
            cur.execute("SELECT 1 FROM perfiles_cuenta WHERE cuenta_id=%s AND nombre=%s "
                        "AND visibilidad='publico'", (a_cuenta, a_nombre))
            if not cur.fetchone():
                return jsonify({'error': 'Esa persona ya no es pública'}), 404
            cur.execute("INSERT INTO buscar_votos(de_cuenta,de_nombre,a_cuenta,a_nombre,valor) "
                        "VALUES(%s,%s,%s,%s,%s) ON CONFLICT(de_cuenta,de_nombre,a_cuenta,a_nombre) "
                        "DO UPDATE SET valor=EXCLUDED.valor, updated_at=now()",
                        (ct['id'], de_nombre, a_cuenta, a_nombre, valor))
            match = False
            if valor == '=':
                match = _buscar_match_mutuo(cur, ct['id'], de_nombre, a_nombre)
            c.commit()
        finally:
            c.close()
        return jsonify({'ok': True, 'match': match})
    except Exception as e:
        return jsonify({'error': str(e)[:300]}), 500


@app.route('/api/buscar/matches')
def api_buscar_matches():
    ct = _cuenta_actual()
    if not ct:
        return jsonify({'error': 'No logueado'}), 401
    try:
        _buscar_init()
        from nube_db import _conn as _c
        c = _c()
        try:
            cur = c.cursor()
            cur.execute("SELECT DISTINCT v1.de_nombre, v2.de_cuenta, v1.a_nombre "
                        "FROM buscar_votos v1 "
                        "JOIN buscar_votos v2 ON v2.de_nombre=v1.a_nombre "
                        "AND v2.a_nombre=v1.de_nombre AND v2.valor='=' "
                        "AND v2.de_cuenta<>v1.de_cuenta "
                        "JOIN perfiles_cuenta pv ON pv.cuenta_id=v2.de_cuenta "
                        "AND pv.nombre=v1.a_nombre AND pv.visibilidad='publico' "
                        "WHERE v1.de_cuenta=%s AND v1.valor='='", (ct['id'],))
            pares = cur.fetchall()
            cur.execute("SELECT a_cuenta FROM buscar_bloqueos WHERE de_cuenta=%s", (ct['id'],))
            yo_bloq = {r[0] for r in cur.fetchall()}
            cur.execute("SELECT de_cuenta FROM buscar_bloqueos WHERE a_cuenta=%s", (ct['id'],))
            me_bloq = {r[0] for r in cur.fetchall()}
            cur.execute("SELECT nombre, datos_json FROM perfiles_cuenta WHERE cuenta_id=%s "
                        "AND visibilidad='publico'", (ct['id'],))
            mias_dj = {str(r[0]): r[1] for r in cur.fetchall()}
            cur.execute("SELECT cuenta_id, nombre, datos_json FROM perfiles_cuenta "
                        "WHERE visibilidad='publico' AND cuenta_id<>%s", (ct['id'],))
            otros = {(r[0], str(r[1])): r[2] for r in cur.fetchall()}
        finally:
            c.close()
        import json as _j

        def _dj2(x):
            if isinstance(x, str):
                try:
                    return _j.loads(x)
                except Exception:
                    return {}
            return x or {}
        ms = []
        for mi_nombre, cid, su_nombre in pares:
            if cid in yo_bloq or cid in me_bloq:
                continue
            fb = _buscar_ficha(_dj2(mias_dj.get(mi_nombre)))
            fo = _buscar_ficha(_dj2(otros.get((cid, su_nombre))))
            set_b = set(_hd_norm_canal(x) for x in fb['canales'])
            comunes = len([x for x in fo['canales'] if _hd_norm_canal(x) in set_b])
            ms.append({'cuenta_id': cid, 'nombre': su_nombre, 'mi_nombre': mi_nombre,
                       'comunes': comunes, 'tipo': fo['tipo'], 'perfil': fo['perfil'],
                       'foto': fo['foto']})
        ms.sort(key=lambda x: (-x['comunes'], x['nombre']))
        vistos, unicos = set(), []
        for m in ms:
            k = (str(m['mi_nombre']).strip().lower(), str(m['nombre']).strip().lower())
            if k not in vistos:
                vistos.add(k)
                unicos.append(m)
        return jsonify({'matches': unicos})
    except Exception as e:
        return jsonify({'error': str(e)[:300]}), 500


@app.route('/api/buscar/bloquear', methods=['POST'])
def api_buscar_bloquear():
    ct = _cuenta_actual()
    if not ct:
        return jsonify({'error': 'No logueado'}), 401
    d = request.get_json(force=True, silent=True) or {}
    try:
        a_cuenta = int(d.get('a_cuenta'))
    except Exception:
        return jsonify({'error': 'Falta cuenta'}), 400
    if a_cuenta == ct['id']:
        return jsonify({'error': 'No te puedes bloquear'}), 400
    try:
        _buscar_init()
        from nube_db import _conn as _c
        c = _c()
        try:
            cur = c.cursor()
            cur.execute("INSERT INTO buscar_bloqueos(de_cuenta,a_cuenta) VALUES(%s,%s) ON CONFLICT DO NOTHING",
                        (ct['id'], a_cuenta))
            c.commit()
        finally:
            c.close()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'error': str(e)[:200]}), 500


@app.route('/api/buscar/reportar', methods=['POST'])
def api_buscar_reportar():
    ct = _cuenta_actual()
    if not ct:
        return jsonify({'error': 'No logueado'}), 401
    if not _buscar_limite(f"rep:{ct['id']}", 10, 3600):
        return jsonify({'error': 'Límite de reportes alcanzado'}), 429
    d = request.get_json(force=True, silent=True) or {}
    try:
        a_cuenta = int(d.get('a_cuenta'))
    except Exception:
        return jsonify({'error': 'Falta cuenta'}), 400
    motivo = str(d.get('motivo') or '').strip()[:500]
    if a_cuenta == ct['id']:
        return jsonify({'error': 'No te puedes reportar'}), 400
    if not motivo:
        return jsonify({'error': 'Contanos el motivo en una frase'}), 400
    try:
        _buscar_init()
        from nube_db import _conn as _c
        c = _c()
        try:
            cur = c.cursor()
            cur.execute("INSERT INTO buscar_reportes(de_cuenta,a_cuenta,motivo) VALUES(%s,%s,%s)",
                        (ct['id'], a_cuenta, motivo))
            c.commit()
        finally:
            c.close()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'error': str(e)[:200]}), 500


@app.route('/api/buscar/mensajes', methods=['GET', 'POST'])
def api_buscar_mensajes():
    ct = _cuenta_actual()
    if not ct:
        return jsonify({'error': 'No logueado'}), 401

    def _parse_con(v):
        s = str(v or '').strip()
        if '|' in s:
            s = s.split('|')[0]
        return int(s)
    try:
        _buscar_init()
        from nube_db import _conn as _c
        if request.method == 'GET':
            try:
                con = _parse_con(request.args.get('con'))
            except Exception:
                return jsonify({'error': 'Falta conversación'}), 400
        else:
            if not _buscar_limite(f"msg:{ct['id']}", 60, 3600):
                return jsonify({'error': 'Límite de mensajes por hora alcanzado'}), 429
            d = request.get_json(force=True, silent=True) or {}
            try:
                con = _parse_con(d.get('a_cuenta') or d.get('con'))
            except Exception:
                return jsonify({'error': 'Falta destinatario'}), 400
            if con == ct['id']:
                return jsonify({'error': 'No te puedes escribir'}), 400
        c = _c()
        try:
            cur = c.cursor()
            cur.execute("SELECT 1 FROM buscar_votos m "
                        "JOIN perfiles_cuenta p ON p.cuenta_id=%s AND p.nombre=m.a_nombre "
                        "AND p.visibilidad='publico' "
                        "JOIN buscar_votos o ON o.de_nombre=m.a_nombre AND o.a_nombre=m.de_nombre "
                        "AND o.valor='=' AND o.de_cuenta<>m.de_cuenta "
                        "JOIN perfiles_cuenta po ON po.cuenta_id=o.de_cuenta "
                        "AND po.nombre=o.de_nombre AND po.visibilidad='publico' "
                        "WHERE m.de_cuenta=%s AND m.valor='=' LIMIT 1",
                        (con, ct['id']))
            if not cur.fetchone():
                return jsonify({'error': 'Solo con match (= mutuo) se puede chatear'}), 403
            cur.execute("SELECT 1 FROM buscar_bloqueos WHERE (de_cuenta=%s AND a_cuenta=%s) "
                        "OR (de_cuenta=%s AND a_cuenta=%s) LIMIT 1", (ct['id'], con, con, ct['id']))
            if cur.fetchone():
                return jsonify({'error': 'Conversación bloqueada'}), 403
            if request.method == 'GET':
                # Tics reales: al abrir el chat se marcan como leídos los mensajes
                # dirigidos a mí. El otro usuario ve leido=true en su próxima carga.
                try:
                    cur.execute(
                        "UPDATE buscar_mensajes SET leido_at=now() "
                        "WHERE a_cuenta=%s AND de_cuenta=%s AND leido_at IS NULL",
                        (ct['id'], con))
                    c.commit()
                except Exception:
                    c.rollback()
                cur.execute("SELECT de_cuenta, texto, created_at, leido_at FROM buscar_mensajes "
                            "WHERE (de_cuenta=%s AND a_cuenta=%s) OR (de_cuenta=%s AND a_cuenta=%s) "
                            "ORDER BY id LIMIT 200", (ct['id'], con, con, ct['id']))
                ms = [{'mio': r[0] == ct['id'], 'texto': r[1],
                       'fecha': str(r[2])[:16] if r[2] else '',
                       'leido': bool(r[3])} for r in cur.fetchall()]
                return jsonify({'mensajes': ms})
            texto = str((request.get_json(force=True, silent=True) or {}).get('texto') or '').strip()[:2000]
            if not texto:
                return jsonify({'error': 'Mensaje vacío'}), 400
            cur.execute("INSERT INTO buscar_mensajes(de_cuenta,a_cuenta,texto) VALUES(%s,%s,%s)",
                        (ct['id'], con, texto))
            c.commit()
            return jsonify({'ok': True})
        finally:
            c.close()
    except Exception as e:
        return jsonify({'error': str(e)[:300]}), 500


if __name__ == '__main__':
    puerto = int(os.environ.get('PORT', 5000))
    # Producción: waitress con 8 hilos (Windows), fallback a Flask debug
    try:
        from waitress import serve
        print(f'Sirviendo con waitress en http://0.0.0.0:{puerto} (8 hilos, gzip, cache)')
        serve(app, host='0.0.0.0', port=puerto, threads=8, channel_timeout=120, cleanup_interval=30)
    except ImportError:
        print('waitress no instalado, usando Flask dev (pip install waitress para producción)')
        app.run(host='0.0.0.0', port=puerto, debug=False, use_reloader=False, threaded=True)