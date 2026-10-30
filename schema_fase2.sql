-- FASE 2 RAVE: cuenta con email + contrasena, sesion por cookie y perfiles por cuenta.
-- No toca perfiles_nube de fase 1 (queda por compatibilidad).

CREATE TABLE IF NOT EXISTS cuentas (
  id SERIAL PRIMARY KEY,
  email TEXT NOT NULL UNIQUE,
  pass_hash TEXT NOT NULL,
  cod_rec_hash TEXT NULL,
  verificado BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sesiones (
  token TEXT PRIMARY KEY,
  cuenta_id INTEGER NOT NULL REFERENCES cuentas(id) ON DELETE CASCADE,
  creada TIMESTAMPTZ DEFAULT now(),
  expira TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sesiones_cuenta ON sesiones(cuenta_id);

CREATE TABLE IF NOT EXISTS perfiles_cuenta (
  id SERIAL PRIMARY KEY,
  cuenta_id INTEGER NOT NULL REFERENCES cuentas(id) ON DELETE CASCADE,
  nombre TEXT NOT NULL,
  fecha TEXT DEFAULT '',
  hora TEXT DEFAULT '',
  lugar TEXT DEFAULT '',
  lat DOUBLE PRECISION NULL,
  lon DOUBLE PRECISION NULL,
  tz DOUBLE PRECISION NULL,
  tz_name TEXT DEFAULT '',
  datos_json JSONB DEFAULT '{}'::jsonb,
  visibilidad TEXT DEFAULT 'privado' CHECK (visibilidad IN ('privado','publico')),
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(cuenta_id, nombre)
);

CREATE INDEX IF NOT EXISTS idx_perfiles_cuenta ON perfiles_cuenta(cuenta_id);
