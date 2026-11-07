# Cómo funciona por dentro

## Piezas

```
scripts/
  fetch.py  search.py  crawl.py  monitor.py  login.py  doctor.py     ← CLIs que ejecuta Claude
  wrp/
    config.py    rutas (~/.web-research-pro), User-Agent, idioma, re-ejecución en el venv privado
    net.py       cliente HTTP sin dependencias (gzip, 308, cookies, límites, errores legibles)
    extract.py   HTML→Markdown (2 salidas en una pasada), trafilatura opcional, PDF, RSS/Atom, JSON
    detect.py    ¿página vacía por JS? ¿muro anti-bots? ¿login? ¿muro de pago?
    browser.py   Chromium vía Playwright (reutilizado, contexto aislado por página)
    fetcher.py   la escalera de métodos y el registro de intentos
    engines.py   motores de búsqueda y fuentes especializadas (red + parsers puros)
    sessions.py  sesiones propias: guardar, importar cookies, cookiejar
    output.py    cabecera del resultado, paginación, guardado en archivos
```

## La escalera (fetcher.py)

1. **http** — petición con cabeceras de un navegador normal. Lo resuelve casi todo en menos de un segundo:
   artículos, documentación, PDFs, feeds, APIs JSON.
2. **browser** — solo si la respuesta es una "cáscara" vacía de JavaScript, un muro anti-bots o está vacía.
   Chromium carga la página, espera a que la red se calme y a que el texto deje de crecer (las SPA siguen
   pintando después del evento *load*). Bloquea imágenes y fuentes para ir más rápido (salvo si pides captura).
3. **reader** — `r.jina.ai` convierte la página en Markdown desde sus servidores. Útil si no tienes navegador
   instalado o si tu red bloquea algo que ellos sí alcanzan.
4. **archive** — la copia más reciente (o la más cercana a `--archive-date`) de Wayback Machine, pedida en
   formato original (`id_`) para que no traiga la barra de archive.org. Siempre se marca con su fecha.

Reglas inteligentes:
- Un **404** salta directamente al archivo (el navegador no va a encontrar lo que no existe).
- Un **muro de login** sin sesión corta la escalera después del navegador: los servicios públicos verían el mismo muro.
- **Sin terceros** con `--session`, en direcciones privadas o con `--no-third-party`.
- Si nada funciona, se devuelve el mejor intento **marcado como fallido**, con el motivo y sugerencias.

## Elegir el texto (extract.py)

Una sola pasada del parser produce dos versiones: la **página completa** y la página **sin `<nav>` ni `<footer>`**.
Si trafilatura está instalado, también se obtiene el **texto de artículo**. En modo `auto`:

- Se usa el texto de artículo solo si conserva casi todo lo demás (≥ 70 %, o ≥ 50 % en textos largos) **y no ha
  perdido bloques de código ni tablas** (en la documentación técnica esos bloques son justo lo importante).
- Si no, la página sin menús. Si quitar menús deja casi nada, la página completa.

Así una ficha de producto conserva el precio de la barra lateral, un listado conserva todos sus elementos y un
artículo de periódico llega limpio.

## Detección (detect.py)

| Señal | Cómo se detecta |
|---|---|
| Cáscara de JavaScript | hay `<script>` y casi nada de texto, o frases tipo "enable JavaScript", o un `<div id="root"></div>` vacío |
| Muro anti-bots | página corta con marcas de Cloudflare, reCAPTCHA/hCaptcha, DataDome, PerimeterX, Akamai, Incapsula, AWS WAF... o 403/429/503 con poco texto |
| Login | URL de login/SSO con poco contenido, campo de contraseña en página corta, o frases tipo "inicia sesión para continuar" |
| Muro de pago | frases tipo "suscríbete para seguir leyendo" o clases `paywall` (solo aviso) |

Las marcas se buscan solo en páginas cortas: un artículo largo que *habla* de CAPTCHAs no se confunde con un bloqueo.

## Sesiones (sessions.py + login.py)

El formato es el "storage state" de Playwright (cookies + localStorage). Con el cliente HTTP las cookies se cargan en
un `CookieJar`, que solo las envía al dominio correcto, también tras redirecciones. Con el navegador se cargan en un
contexto aislado y, al terminar, se guardan las cookies renovadas para que la sesión dure más.

## Entorno privado

`doctor.py --setup` crea `~/.web-research-pro/venv`. Cada script, al arrancar, comprueba si ese venv existe y, si
no se está ejecutando ya dentro, se relanza con él. Por eso Claude siempre puede llamar a `python3 script.py` sin
preocuparse de dónde están instaladas las dependencias, y nada choca con el Python de tu sistema.
