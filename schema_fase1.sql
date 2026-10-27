-- FASE 1 RAVE: persistencia en Neon sin romper CSV local.
-- Privado por defecto. Publico latente (columna lista, sin listado publico aun).

CREATE TABLE IF NOT EXISTS dispositivos (
  device_id TEXT PRIMARY KEY,
  email TEXT NULL,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS perfiles_nube (
  id SERIAL PRIMARY KEY,
  device_id TEXT NOT NULL REFERENCES dispositivos(device_id) ON DELETE CASCADE,
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
  UNIQUE(device_id, nombre)
);

CREATE INDEX IF NOT EXISTS idx_perfiles_nube_device ON perfiles_nube(device_id);
-- Indice para futura red social (solo cuando se active listado publico):
-- CREATE INDEX IF NOT EXISTS idx_perfiles_publico ON perfiles_nube(visibilidad) WHERE visibilidad='publico';
