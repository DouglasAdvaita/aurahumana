-- RLS para Neon (preparado, NO aplicado automaticamente).
-- Requiere crear rol rave_app y usarlo como DATABASE_URL en runtime.

-- 1) Rol de aplicacion (ejecutar como owner):
-- CREATE ROLE rave_app LOGIN PASSWORD 'CAMBIAR';
-- GRANT USAGE ON SCHEMA public TO rave_app;
-- GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO rave_app;
-- GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO rave_app;

-- 2) Activar RLS:
-- ALTER TABLE cuentas ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE sesiones ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE perfiles_cuenta ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE dispositivos ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE perfiles_nube ENABLE ROW LEVEL SECURITY;

-- 3) Politicas (ejemplo por cuenta_id via claim de sesion; requiere setear current_setting('app.cuenta_id') en cada conexion).
-- CREATE POLICY cuentas_self ON cuentas USING (id = current_setting('app.cuenta_id')::int);
-- CREATE POLICY sesiones_self ON sesiones USING (cuenta_id = current_setting('app.cuenta_id')::int);
-- CREATE POLICY perfiles_cuenta_self ON perfiles_cuenta USING (cuenta_id = current_setting('app.cuenta_id')::int);
-- CREATE POLICY dispositivos_self ON dispositivos USING (device_id = current_setting('app.device_id'));
-- CREATE POLICY perfiles_nube_self ON perfiles_nube USING (device_id = current_setting('app.device_id'));