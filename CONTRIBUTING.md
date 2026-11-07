# Cómo contribuir

¡Gracias por querer mejorar Web Research Pro! (English speakers: issues and PRs in English are welcome too.)

## Preparar el entorno

```bash
git clone https://github.com/mohaaa012/web-research-pro.git
cd web-research-pro
python3 -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
make dev                                                # dependencias + Chromium
make test
```

## Estructura

```
.claude-plugin/            plugin.json + marketplace.json (instalación como plugin) + icono
skills/web-research-pro/
  SKILL.md                 instrucciones que lee Claude (manténlas por debajo de ~250 líneas)
  references/              guías que Claude abre solo cuando las necesita
  scripts/                 CLIs (fetch, search, crawl, monitor, login, doctor)
  scripts/wrp/             librería compartida (red, extracción, detección, navegador, sesiones...)
  evals/                   casos de evaluación (formato `claude plugin eval`)
tests/                     pytest + servidor web local que simula cada caso difícil
tools/package_skill.py     genera dist/web-research-pro.skill
install.sh / install.ps1   instaladores de una línea
```

## Reglas del proyecto

1. **Solo librería estándar en el camino básico.** Playwright, trafilatura y pypdf son opcionales: el skill debe seguir funcionando (con menos funciones) sin ellos.
2. **Honestidad por encima de todo.** Si algo no se pudo leer, el resultado lo dice (`ok: NO`, `reason`, `suggestion`). Nunca se devuelve una página de bloqueo como si fuera contenido.
3. **Nada de evasión.** No se aceptan PRs que resuelvan CAPTCHAs, falsifiquen huellas del navegador, roten proxies o salten muros de pago.
4. **Cada arreglo, con su test.** Si cambias cómo se extrae o detecta algo, añade el caso al servidor de `tests/server.py`.
5. **Python 3.9+** y compatible con Windows (rutas con `pathlib`, sin `os.chmod` obligatorio).

## Ideas fáciles para empezar

- Añadir "recetas" de APIs públicas en `skills/web-research-pro/references/site-recipes.md` (comprueba que el endpoint existe).
- Mejorar la detección de páginas de bloqueo o de login con ejemplos reales (anonimizados) en `tests/`.
- Traducir mensajes o documentación.

## Pull requests

- Una idea por PR, con descripción de qué cambia y por qué.
- `make test` y `make validate` (si tienes Claude Code) en verde.
- Actualiza `CHANGELOG.md` en la sección de la próxima versión.
