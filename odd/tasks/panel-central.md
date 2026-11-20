# Panel central RAVE (Búsqueda / Chat / Posts)

## Objetivo
Nueva página /panel con pestañas Búsqueda, Chat y Posts (foro), reutilizando endpoints existentes y agregando foro mínimo. Base para futura integración en Alma.

## Alcance
- Ruta /panel + template panel.html con tabs.
- Foro: schema + endpoints posts/comentarios, 1 post/día por cuenta, ventana 7 días.
- Búsqueda y Chat: reutilizar /buscar y /api/buscar/* (sin duplicar lógica).
- No incluye aún eneagrama/neurodivergencias ni apodo/avatar (siguiente fase).

## Restricciones
- RAVE sin .bak; deploy lo hace el usuario.
- Mínimo código en app.py: solo ruta + endpoints foro + init.
- No tocar Alma en esta fase.

## Tareas
- [ ] T1 — Schema foro (schema_fase5.sql) + _foro_init
- [ ] T2 — Endpoints /api/foro/posts (GET/POST) y /api/foro/comentarios (GET/POST)
- [ ] T3 — Ruta /panel + template con tabs (Buscar, Chat, Posts)
- [ ] T4 — Prueba manual: post, comentario, expiración 7 días, rate limit 1/día

## Próximo paso
Implementar schema + endpoints + ruta + template.