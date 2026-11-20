-- FASE 5 RAVE: foro público (posts + comentarios), ventana 7 días.
CREATE TABLE IF NOT EXISTS foro_posts (
  id SERIAL PRIMARY KEY,
  cuenta_id INTEGER NOT NULL REFERENCES cuentas(id) ON DELETE CASCADE,
  autor TEXT NOT NULL DEFAULT '',
  texto TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now(),
  expires_at TIMESTAMPTZ DEFAULT (now() + interval '7 days')
);
CREATE TABLE IF NOT EXISTS foro_comentarios (
  id SERIAL PRIMARY KEY,
  post_id INTEGER NOT NULL REFERENCES foro_posts(id) ON DELETE CASCADE,
  cuenta_id INTEGER NOT NULL REFERENCES cuentas(id) ON DELETE CASCADE,
  autor TEXT NOT NULL DEFAULT '',
  texto TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_foro_posts_exp ON foro_posts(expires_at);
CREATE INDEX IF NOT EXISTS idx_foro_comentarios_post ON foro_comentarios(post_id);