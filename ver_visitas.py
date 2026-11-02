"""Ver ultimas visitas (solo operador con DATABASE_URL). Uso: python ver_visitas.py [limite]"""
import sys
sys.path.insert(0, ".")
import cuentas_neon
import os
os.environ["DATABASE_URL"] = cuentas_neon.conectar_rapido(cuentas_neon.cargar_dsn())
import visitas_db
visitas_db.init_db()
lim = int(sys.argv[1]) if len(sys.argv) > 1 else 50
for v in visitas_db.ultimas(lim):
    print(v.get("created_at"), "|", (v.get("ip") or ""), "|", (v.get("path") or "")[:40],
          "| pais:", (v.get("pais") or "-"), "|", (v.get("duracion_seg") if v.get("duracion_seg") is not None else "-"), "s")
