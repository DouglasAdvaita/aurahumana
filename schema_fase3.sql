-- FASE 3 RAVE: registro de visitas (opcion 2: IP completa para pais posterior).
-- Solo escritura desde la app; lectura privada desde cuenta.
CREATE TABLE IF NOT EXISTS visitas (
  id SERIAL PRIMARY KEY,
  created_at TIMESTAMPTZ DEFAULT now(),
  ip TEXT DEFAULT '',
  path TEXT DEFAULT '',
  user_agent TEXT DEFAULT '',
  referer TEXT DEFAULT '',
  pais TEXT DEFAULT '',
  duracion_seg INTEGER NULL,
  updated_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_visitas_fecha ON visitas(created_at DESC);
