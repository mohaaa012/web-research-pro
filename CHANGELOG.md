# Changelog

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/); versiones con [SemVer](https://semver.org/lang/es/).

## [Sin publicar]

### Añadido
- Web del proyecto en `site/` (español e inglés) publicada con GitHub Pages: metadatos para buscadores y redes sociales, datos estructurados, sitemap e imagen de vista previa.
- Sección de preguntas frecuentes en los README y más palabras clave en `plugin.json` y `pyproject.toml`.

## [1.0.0] - 2026-11-07

Primera versión.

### Añadido
- `fetch.py`: lectura con escalera automática (HTTP con cabeceras de navegador → Chromium real → lector r.jina.ai → Wayback Machine), detección de páginas vacías por JavaScript, muros anti-bots, muros de login y avisos de muro de pago. PDF (pypdf o pdftotext), RSS/Atom, JSON y texto. Capturas de pantalla, scroll infinito, clics, espera por selector, paginación de la salida y guardado en archivos.
- Extracción que nunca pierde bloques de código ni tablas: usa trafilatura solo cuando el texto limpio conserva lo importante; si no, la página completa sin menús ni pie.
- `search.py`: DuckDuckGo (HTML y Lite, con región y filtro de fecha), Brave, Tavily y SearXNG con clave, y Wikipedia, Hacker News, Reddit, GitHub, arXiv y Stack Exchange. `--fetch K` lee los mejores resultados.
- `login.py`: sesiones propias guardadas en local con permisos de solo-propietario; inicio de sesión manual en ventana real o importación de cookies (cookies.txt, JSON de Cookie-Editor, estado de Playwright).
- `crawl.py`: rastreo educado (robots.txt y Crawl-delay, límite de páginas, ámbito por carpeta, sitemap.xml, sin parámetros de seguimiento, sin duplicados) con índice `INDEX.md` y `pages.jsonl`.
- `monitor.py`: detección de cambios con diff, vigilancia de un valor con `--regex` o de un elemento con `--selector`.
- `doctor.py`: diagnóstico completo y `--setup` (venv privado + paquetes + Chromium; si la descarga falla usa Chrome o Edge del sistema).
- Instaladores de una línea (`install.sh`, `install.ps1`), plugin y marketplace de Claude Code, paquete `.skill` para claude.ai.
- 79 tests con un servidor web local que simula cada caso difícil; CI en Linux, macOS y Windows; evaluaciones en formato `claude plugin eval`.
