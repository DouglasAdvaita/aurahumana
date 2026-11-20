from flask import Blueprint, request, jsonify, render_template
import auth_db as _auth

foro_bp = Blueprint('foro', __name__)
_COOKIE = 'auth_token'

def _cuenta_actual():
    try:
        if not _auth.disponible():
            return None
        return _auth.cuenta_de_token(request.cookies.get(_COOKIE) or '')
    except Exception:
        return None

# ---------- Fase 5: foro público (posts + comentarios, ventana 7 días) ----------
_FORO_OK = False


def _foro_init():
    global _FORO_OK
    if _FORO_OK:
        return
    try:
        from pathlib import Path as _P
        from nube_db import _conn as _c
        sql = (_P(__file__).parent / 'schema_fase5.sql').read_text(encoding='utf-8')
        c = _c()
        try:
            cur = c.cursor()
            cur.execute(sql)
            c.commit()
        finally:
            c.close()
        _FORO_OK = True
    except Exception:
        pass


@foro_bp.route('/panel')
def pagina_panel():
    return render_template('panel.html')


@foro_bp.route('/api/foro/posts', methods=['GET', 'POST'])
def api_foro_posts():
    ct = _cuenta_actual()
    if not ct:
        return jsonify({'error': 'No logueado'}), 401
    try:
        _foro_init()
        from nube_db import _conn as _c
        if request.method == 'GET':
            c = _c()
            try:
                cur = c.cursor()
                cur.execute("SELECT id, autor, texto, created_at, expires_at FROM foro_posts "
                            "WHERE expires_at > now() ORDER BY created_at DESC LIMIT 100")
                posts = [{'id': r[0], 'autor': r[1], 'texto': r[2],
                          'fecha': (r[3].isoformat() if r[3] else ''),
                          'expira': (r[4].isoformat() if r[4] else '')} for r in cur.fetchall()]
                for p in posts:
                    cur.execute("SELECT count(*) FROM foro_comentarios WHERE post_id=%s", (p['id'],))
                    p['comentarios'] = cur.fetchone()[0]
            finally:
                c.close()
            return jsonify({'posts': posts})
        data = request.get_json(force=True, silent=True) or {}
        texto = str(data.get('texto') or '').strip()[:500]
        if not texto:
            return jsonify({'error': 'Texto vacío'}), 400
        c = _c()
        try:
            cur = c.cursor()
            cur.execute("SELECT 1 FROM foro_posts WHERE cuenta_id=%s AND created_at > now() - interval '24 hours'",
                        (ct['id'],))
            if cur.fetchone():
                return jsonify({'error': 'Ya publicaste hoy. Volvé mañana.'}), 429
            autor = str(ct.get('email') or '').split('@')[0] or 'usuario'
            cur.execute("INSERT INTO foro_posts(cuenta_id,autor,texto) VALUES(%s,%s,%s) RETURNING id",
                        (ct['id'], autor, texto))
            pid = cur.fetchone()[0]
            c.commit()
        finally:
            c.close()
        return jsonify({'ok': True, 'id': pid})
    except Exception as e:
        return jsonify({'error': str(e)[:300]}), 500


@foro_bp.route('/api/foro/comentarios', methods=['GET', 'POST'])
def api_foro_comentarios():
    ct = _cuenta_actual()
    if not ct:
        return jsonify({'error': 'No logueado'}), 401
    try:
        _foro_init()
        from nube_db import _conn as _c
        if request.method == 'GET':
            try:
                pid = int(request.args.get('post_id'))
            except Exception:
                return jsonify({'error': 'Falta post'}), 400
            c = _c()
            try:
                cur = c.cursor()
                cur.execute("SELECT id, autor, texto, created_at FROM foro_comentarios "
                            "WHERE post_id=%s ORDER BY created_at ASC", (pid,))
                cs = [{'id': r[0], 'autor': r[1], 'texto': r[2],
                       'fecha': (r[3].isoformat() if r[3] else '')} for r in cur.fetchall()]
            finally:
                c.close()
            return jsonify({'comentarios': cs})
        data = request.get_json(force=True, silent=True) or {}
        try:
            pid = int(data.get('post_id'))
        except Exception:
            return jsonify({'error': 'Falta post'}), 400
        texto = str(data.get('texto') or '').strip()[:500]
        if not texto:
            return jsonify({'error': 'Texto vacío'}), 400
        c = _c()
        try:
            cur = c.cursor()
            cur.execute("SELECT 1 FROM foro_posts WHERE id=%s AND expires_at > now()", (pid,))
            if not cur.fetchone():
                return jsonify({'error': 'El post ya expiró'}), 404
            autor = str(ct.get('email') or '').split('@')[0] or 'usuario'
            cur.execute("INSERT INTO foro_comentarios(post_id,cuenta_id,autor,texto) VALUES(%s,%s,%s,%s)",
                        (pid, ct['id'], autor, texto))
            c.commit()
        finally:
            c.close()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'error': str(e)[:300]}), 500
