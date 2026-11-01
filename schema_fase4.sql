-- FASE 4 RAVE: Buscar personas (opt-in público, = / X, match + chat + bloqueo + reporte).
CREATE TABLE IF NOT EXISTS buscar_votos (
  de_cuenta INTEGER NOT NULL REFERENCES cuentas(id) ON DELETE CASCADE,
  de_nombre TEXT NOT NULL,
  a_cuenta INTEGER NOT NULL REFERENCES cuentas(id) ON DELETE CASCADE,
  a_nombre TEXT NOT NULL,
  valor TEXT NOT NULL CHECK (valor IN ('=','X')),
  updated_at TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (de_cuenta, de_nombre, a_cuenta, a_nombre)
);
CREATE TABLE IF NOT EXISTS buscar_bloqueos (
  de_cuenta INTEGER NOT NULL REFERENCES cuentas(id) ON DELETE CASCADE,
  a_cuenta INTEGER NOT NULL REFERENCES cuentas(id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (de_cuenta, a_cuenta)
);
CREATE TABLE IF NOT EXISTS buscar_reportes (
  id SERIAL PRIMARY KEY,
  de_cuenta INTEGER NOT NULL REFERENCES cuentas(id) ON DELETE CASCADE,
  a_cuenta INTEGER NOT NULL REFERENCES cuentas(id) ON DELETE CASCADE,
  motivo TEXT DEFAULT '',
  created_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE IF NOT EXISTS buscar_mensajes (
  id SERIAL PRIMARY KEY,
  de_cuenta INTEGER NOT NULL REFERENCES cuentas(id) ON DELETE CASCADE,
  a_cuenta INTEGER NOT NULL REFERENCES cuentas(id) ON DELETE CASCADE,
  texto TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_buscar_votos_a ON buscar_votos(a_cuenta);
CREATE INDEX IF NOT EXISTS idx_buscar_msg_par ON buscar_mensajes(de_cuenta, a_cuenta);
CREATE INDEX IF NOT EXISTS idx_perfiles_cuenta_vis ON perfiles_cuenta(visibilidad) WHERE visibilidad='publico';
