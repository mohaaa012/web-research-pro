# Benchmark (iteración 1 · 2026-11-07)

Comparación entre Claude **con** el skill y Claude **sin** él (solo la herramienta integrada WebFetch), en 4 tareas
reales. Los casos están en [`skills/web-research-pro/evals/`](../skills/web-research-pro/evals).

## Resultado

| Caso | Criterios | Sin el skill | Con el skill |
|---|---|---|---|
| `js-app-package-stats` — descargas, versión y licencia de serde en crates.io | 3 | 3/3 ⚠️ | 3/3 |
| `pdf-paper-details` — resumen, autores y aceleración de un paper en PDF | 4 | 0/4 | 4/4 |
| `blocked-site-no-invention` — descargas semanales en npmjs.com (protegido por Cloudflare) | 3 | 3/3 | 3/3 |
| `docs-plugin-install-commands` — comandos exactos en la documentación de Claude Code | 3 | 3/3 | 3/3 |
| **Media por caso** | | **75 %** | **100 %** |

⚠️ Sin el skill, la página de crates.io llega vacía (WebFetch solo vio el título). Aprueba porque el agente
recurrió a la API de crates.io por su cuenta. Con el skill se leyó la propia página (`http=js_shell → browser=ok`)
con cifras extra (descargas recientes, número de versiones), que además coinciden con la API.

## Qué muestra

- **PDF**: es la diferencia más clara. WebFetch no descomprime los PDF; `fetch.py` extrajo las 14 páginas en ~1,3 s.
- **Páginas con JavaScript**: el skill las lee directamente; sin él hay que conocer una API alternativa.
- **Webs con bloqueo fuerte**: ninguno de los dos se inventa el número. El skill además explica el bloqueo y da la
  vía alternativa (la API de descargas de npm). En este entorno esa API también estaba bloqueada por la red;
  en una conexión normal el skill devolvería la cifra.
- **Documentación** bien hecha: los dos aciertan. Aquí el benchmark detectó un fallo real del skill (el extractor de
  artículos perdía los bloques de código) que se corrigió en esta misma iteración, con su test de regresión.

## Método y limitaciones (para ser honestos)

- Una ejecución por configuración, hecha dentro de una sola sesión, no con agentes independientes.
- La línea base es **fuerte**: se le permitieron las llamadas de seguimiento que haría un agente con iniciativa (APIs oficiales, enlaces de la documentación).
- La red del entorno de pruebas bloqueaba muchos dominios (api.npmjs.org, r.jina.ai, archive.org), lo que limita los escalones de terceros.
- No hay cifras de tiempo ni tokens por ejecución porque esas ejecuciones no las generan; no se han estimado.

## Reproducirlo

Con Claude Code (ejecuciones reales de modelo, con coste):

```bash
cd skills/web-research-pro
claude plugin eval . --allow-tools Write,Edit,Bash,WebFetch,WebSearch
```
