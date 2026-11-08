# Panel secreto admin + tics de lectura reales

## Objetivo
Que el usuario (administrador) pueda ver en un panel web secreto la actividad de la APK Alma (usuarios, matches, mensajes, bloqueos, reportes) y que los tics de lectura del chat sean reales (doble check azul solo cuando el otro usuario leyó el mensaje).

## Problema
Hoy no hay panel admin (solo Neon crudo) y los tics azules del chat están hardcodeados en la app sin backend real: todos los mensajes propios muestran ✓✓ azul aunque el destinatario nunca los haya abierto.

## Pedido textual
> 1.
> y los tics azules no son reales

## Alcance
- Incluye: migración `leido_at` en `buscar_mensajes`, marcado de leído al abrir el chat, campo `leido` por mensaje en la API, tics reales en la APK (✓ gris = enviado, ✓✓ azul = leído), ruta web secreta larga `/admin/alma-.../panel` con dashboard HTML inline (totales, actividad reciente, últimas cuentas/mensajes/reportes/bloqueos), compilación e instalación de la APK en el celular, push de RAVE para despliegue en Render.
- No incluye: notificaciones push de mensajes, editar/borrar mensajes, fotos en el chat, protección con login en el panel (solo URL secreta, como eligió el usuario).

## Restricciones
- RAVE: `app.py` local en `C:\Mis Documentos\_superacion\Codex\DisenioHumano - para prueba OpenCode`; despliegue por push a `origin` (GitHub `DouglasAdvaita/aurahumana`) → Render.
- Alma: APK Kotlin en `C:\Users\jorge\AndroidStudioProjects\Alma`; `ChatScreen.kt` muestra hoy ✓✓ hardcodeado en `m.mio`.
- Panel sin login, solo URL larga secreta; cabecera `X-Robots-Tag: noindex`.

## Tareas
- [x] T1 — Backend: columna `leido_at` en `buscar_mensajes` (schema + `ALTER TABLE ... IF NOT EXISTS`) · criterio: existe en Neon tras el primer llamado.
- [x] T2 — Backend: `GET /api/buscar/mensajes` marca como leídos los mensajes dirigidos a mí y devuelve `leido` por mensaje · criterio: al abrir el chat, el otro usuario recibe `leido:true`.
- [x] T3 — Alma: `Mensaje.leido`, parseo y tics reales (✓ gris vs ✓✓ azul) · criterio: sin leer = 1 check, leído = 2 azules.
- [x] T4 — Ruta secreta `/admin/dh-9f3a7c1e5b2d4f6a8c0e/panel` con dashboard · criterio: abre en navegador con totales y tablas recientes.
- [ ] T5 — Compilar APK, instalar en el celular y push de RAVE · criterio: `assembleDebug` OK, `adb install Success`, push hecho.
- [ ] T6 — Verificación funcional: prueba de lectura con dos cuentas · criterio: evidencia observada.

## Evidencia
- `python -c "ast.parse(app.py)"` → app.py OK.
- Panel local con el cliente de pruebas: `GET /admin/.../panel` → status 200, 5438 bytes, cabecera noindex, totales [4 cuentas, 4 con perfiles, 492 perfiles públicos, 11 sesiones, 1 match, 13 mensajes, 1 mensaje 24 h, 13 sin leer, 35 votos, 1 bloqueo, 0 reportes].
- Neon: `SELECT count(*), count(leido_at) FROM buscar_mensajes` → (13, 0); `UPDATE ... SET leido_at=now() WHERE a_cuenta=0 AND de_cuenta=0` → 0 filas sin error (columna operativa).
- `gradlew assembleDebug` → BUILD SUCCESSFUL in 3m 8s.
- `adb install -r app-debug.apk` → Success.

## Progreso
- 08/11/2026: T1–T4 hechos y probados; APK compilada e instalada. Falta el push de RAVE (hay cambios propios sin commitear en app.py, así que se decidió no empujar a ciegas) y la prueba con dos cuentas.
- 08/11/2026: corregido el envío de comentarios (asunto y cuerpo ahora van dentro del `mailto`) y el resaltado del botón inferior (sincronizado con la hoja y visible en violeta).

## Próximo paso
Decidir si se hace push de RAVE para publicar el panel en Render, y probar la lectura con dos cuentas.
