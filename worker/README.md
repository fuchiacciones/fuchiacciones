# FUCHIACCIONES — Refresh Worker

Este Worker permite que el botón **ACTUALIZAR AHORA** de GitHub Pages solicite una nueva ejecución real del workflow de FUCHIACCIONES.

## Arquitectura

`GitHub Pages → Cloudflare Worker → GitHub Actions → build_site.py → GitHub Pages`

El token de GitHub queda exclusivamente como **secret de Cloudflare**. Nunca se publica en `public/` ni en JavaScript del navegador.

## 1. Crear el Worker

En Cloudflare Workers, crear un Worker nuevo y copiar `worker/src/index.js` como código.

También puede desplegarse con Wrangler usando `worker/wrangler.toml.example` como referencia.

## 2. Crear el secreto

El Worker necesita un secreto llamado `GITHUB_TOKEN`.

Usar un token de GitHub con permisos mínimos para disparar workflows del repositorio `fuchiacciones/fuchiacciones`. No colocar el token en ningún archivo del repositorio.

Con Wrangler:

```bash
wrangler secret put GITHUB_TOKEN
```

## 3. URL del Worker

Después del deploy, Cloudflare entrega una URL similar a:

`https://fuchiacciones-refresh.<tu-subdominio>.workers.dev`

La URL debe configurarse en el botón de `public/index.html` como endpoint de refresh.

## 4. Seguridad

- El Worker acepta `POST` y `OPTIONS`.
- Solo acepta solicitudes CORS desde `https://fuchiacciones.github.io`.
- El token nunca llega al navegador.
- El endpoint no permite seleccionar workflows arbitrarios: solo dispara `daily.yml` sobre `main`.
- La respuesta es `202` cuando GitHub acepta la solicitud.

## 5. Qué hace el botón

El botón solicita una nueva ejecución de **FUCHIACCIONES Daily** mediante `workflow_dispatch`. El workflow vuelve a consultar precios, noticias, indicadores y calendario, genera `public/data.json` y `public/index.html`, y publica la nueva versión.

## Nota

El Worker debe estar desplegado en una cuenta de Cloudflare para que el botón pueda disparar el análisis. El código ya queda preparado dentro del repositorio, pero la cuenta/credenciales de Cloudflare no forman parte del repositorio.
