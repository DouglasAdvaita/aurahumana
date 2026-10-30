# Publicar RAVE en GitHub (repo privado `aura-humana`)

## Que entra al repo
- Codigo: `app.py`, `generar_publicos.py`, `generar_xlsx.py`, `bajar_fotos_publicas.py`, `preparar_datos.py`.
- Plantillas web: `templates/*.html` (incluye `autoconocimiento.html` restaurado).
- Contenido y datos publicos: `puertas.csv`, `lineas_popup.csv`, `canales.csv`, `centros.csv`, `cruces.csv`, `autoridades.csv`, `perfiles.csv`, `definiciones.csv`, `tipos.csv`, `eneatipos.csv`, `doshas.csv`, `numerologia.csv`, `natal.csv`, `natal_planetas.csv`, `sernoser_puertas.csv`, `sernoser_emojis.csv`, `personas_publicas.csv`, `parejas_publicas.csv`, `fotos_publicas.csv`, `clan_fotos.csv`.
- Datos consolidados de públicos: `personas_publicas.csv` y `parejas_publicas.csv` (las listas fuente .xlsx quedan locales y no se publican).
- Textos: `canales_accesibles/`, `base_informe_ia.txt`, `canales simplificados.txt`.
- Config: `.gitignore`, `render.yaml`, `Procfile`, `requirements.txt`, `opencode`, `INICIAR.cmd`, `PUBLICAR.cmd`, `PUBLICACION.md`, imagenes SVG.
- Nube (Neon): `nube_db.py`, `auth_db.py`, `schema_fase1.sql`, `schema_fase2.sql`, `templates/cuenta.html`, `templates/nube_test.html`.
- Plantillas vacias: `plantillas/*.csv` (solo cabecera).

## Que NO entra (queda local)
- Datos personales llenos: `datos.csv`, `datos_sin_analia.csv`, `vinculos.csv`, `clan.csv`, `conocidos.csv`, `test.csv`, `ia.csv`, `informe.csv`, `dinamica_compuesta.csv`, `cambios_aplicados_horas.csv`, `comparacion_datos_horas.csv`.
- Memorias personales: `memoriaOC.md` (contiene chats y nombres; queda local).
- Pagina de laboratorio: `templates/lab.html` (tenia nombres de prueba; queda local; `/lab` da 404 en el clon).
- Excel de trabajo: `*.xlsx` (salvo `centros_detallado Matriz 9 Centros.xlsx` y `razgos.xlsx` si aparece).
- Medios pesados: `static/canales_audio/` (91 MB), `videos_canales/` (48 MB), `Publicos/` (18 MB), `avatares_arquetipos/`.
- Respaldos y copias: `*.bak`, `_viejos/`, `app - copia.py`, `* - copia.*`.
- Secretos: `.env`.
- Accesos directos y basura de Windows: `*.lnk`, `Thumbs.db`, `desktop.ini`.

## Como funciona en un clon nuevo
1. Clonar el repo.
2. `python preparar_datos.py` crea los CSV personales vacios desde `plantillas/` (solo si no existen).
3. `INICIAR.cmd` ya llama a `preparar_datos.py` antes de arrancar.
4. Las fotos de `Publicos/` se regeneran con `python bajar_fotos_publicas.py` si hacen falta.

## Nube (Neon) — opcional
- Variable `DATABASE_URL` en Render (Environment). Sin ella todo sigue local en CSV.
- `render.yaml` la declara con `sync: false`: se carga a mano en el panel y no se borra al sincronizar el Blueprint.
- Tablas: `dispositivos` + `perfiles_nube` (fase 1, por navegador) y `cuentas` + `sesiones` + `perfiles_cuenta` (fase 2, por correo).
- `/cuenta`: crear cuenta, entrar, importar/exportar CSV y fijar visibilidad.
- Las tablas se crean solas al primer uso (`schema_fase1.sql`, `schema_fase2.sql`).

## Fuente de datos según entorno
1. Con sesión iniciada: solo las personas de esa cuenta (Neon). Nunca los CSV del servidor.
2. Local con `datos.csv` propio con contenido: `datos.csv`.
3. Sin datos propios o en Render: `datos_publicos.xlsx` (492 personas públicas).
- En Render no se puede guardar sin cuenta: `Agregar` responde 401 y pide entrar.
- `datos.csv` no se publica: en Render no existe, por eso nunca se exponen datos personales.
- Importar/exportar: CSV con formato `Nombre;Puerta;Linea;C/I` (+ `Fecha;Hora;Lugar` opcional).

## Aislamiento (fase 3)
- `datos.csv`, `vinculos.csv`, `test.csv`, `ia.csv` e `informe.csv` locales NO se exponen a cuentas.
- Por cuenta se guardan: puertas, líneas, fecha/hora/lugar, perfil y test de autoconocimiento.
- Todavía locales (sin cuenta): clan, conocidos, dinámica compuesta, informes manuales y textos IA.

## Primera vez (crear el remoto)
1. En GitHub: New repository -> nombre `aura-humana` -> Private -> NO marcar README, .gitignore ni licencia.
2. Copiar la URL del repo.
3. En esta carpeta: `git remote add origin <URL>`.
4. `PUBLICAR.cmd` (o `git push -u origin main`).

## Como publicar
- Doble clic en `PUBLICAR.cmd`.
- Escribe una descripcion (o Enter para usar la fecha).
- Guarda el commit local; si hay remoto `origin`, sube a GitHub.
- Si no hay remoto, avisa y no falla.

## Notas
- `parejas_publicas.csv` fila 87 corregida (tenia 11 campos; ahora 10).
- `templates/autoconocimiento.html` restaurado desde el commit inicial (la ruta `/autoconocimiento` lo necesita).
- `razgos.xlsx` no esta en el proyecto: la funcion de "circuitos excluyentes" falla hasta recuperarlo. No se invento.
- `centros_detallado Matriz 9 Centros.xlsx` queda incluido como excepcion porque la app lo usa en tiempo de ejecucion.
- `sernoser_puertas.csv` usa TAB (no `;`) y se lee con `delimiter='\t'`.
- Git: el commit es local; PUBLICAR sube. Nada se borra: se puede volver atras.
