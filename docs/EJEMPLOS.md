# Ejemplos de uso

Escribe a Claude con normalidad. Estos ejemplos muestran qué hace el skill por debajo para que sepas qué esperar.

## 🎮 Videojuegos y Roblox

**"Investiga los 10 juegos de Roblox con más jugadores ahora mismo y qué mecánicas comparten"**
- La página de *charts* de Roblox es JavaScript puro → `fetch.py https://www.roblox.com/charts --method browser --scroll 3`.
- Las cifras exactas (jugando ahora, visitas, favoritos, fecha de actualización) salen de la API pública de juegos, consultando varios a la vez (ver `site-recipes.md`).
- Contrasta con Reddit, wikis y vídeos para las mecánicas, y te da una tabla comparativa con fuentes.

**"Vigila el número de jugadores de mi juego cada hora"**
- `monitor.py check "<url de la API del juego>" --regex '"playing":\s*(\d+)'` y programarlo con `/loop 1h` o cron.

**"Guárdame la documentación de Luau y de la API de Roblox para consultarla"**
- `crawl.py https://create.roblox.com/docs/... --max-pages 80 --method auto` → carpeta con `INDEX.md`; después Claude busca dentro con grep en vez de volver a descargar.

## 💼 Negocio y dinero

**"Analiza a mis 5 competidores: precios, planes y qué prometen en su web"**
- `fetch.py URL1 URL2 URL3 URL4 URL5 --out-dir competencia/` (en una sola llamada), y si hay tablas de precios con pestañas, `--click` sobre "Anual"/"Mensual".
- Informe con tabla comparativa, fuente y fecha de cada precio.

**"Avísame si este producto baja de 150 €"**
- `monitor.py check https://tienda.com/producto --regex "([0-9]+[,.][0-9]{2}) ?€"`; Claude te propone programarlo.

**"Busca trabajos remotos de desarrollador junior publicados esta semana en España"**
- `search.py "remote junior developer jobs Spain" --region es-es --time w --fetch 5`, luego filtra y te da una lista con enlaces.

**"Resúmeme el último informe anual de esta empresa (PDF de 120 páginas)"**
- `fetch.py https://.../informe.pdf --out informe.md` y lectura por secciones; las marcas `--- Page N ---` permiten citar la página exacta.

> Para inversiones el skill te ayuda a reunir y contrastar información, pero no es asesoramiento financiero: comprueba siempre las cifras en la fuente oficial.

## 📚 Estudios

**"Busca papers recientes sobre agentes autónomos y explícame los 3 más citados"**
- `search.py "autonomous agents LLM" --engine arxiv,web --time y`, lee los PDF con `fetch.py` y te explica cada uno con ejemplos.

**"Lee este artículo de Wikipedia en inglés y hazme un esquema en español"**
- `fetch.py https://en.wikipedia.org/wiki/...` (texto completo, no un resumen) → esquema traducido.

## 🛠️ Programación

**"¿Por qué me da este error? `TypeError: ...`"**
- `search.py "TypeError ..." --engine stackoverflow,github,web`, lee las respuestas aceptadas y te da la solución adaptada a tu código.

**"¿Cuántas descargas semanales tiene este paquete y cuándo fue la última versión?"**
- npmjs.com bloquea bots, así que va directo a `registry.npmjs.org` y `api.npmjs.org` (rápido y fiable).

## 🔐 Con tu cuenta

**"Entra en mi panel de analíticas y dime cómo fue la semana"**
1. Claude te pide permiso y ejecuta `login.py save analytics --url https://.../login`.
2. Inicias sesión **tú** en la ventana que se abre y la cierras.
3. `fetch.py https://.../dashboard --session analytics --method browser --wait-for ".chart" --screenshot panel.png`
4. Resumen con cifras; la captura le sirve a Claude para leer los gráficos.

## 🗞️ Noticias y cambios

**"¿Qué ha cambiado en la última actualización de X?"**
- Si la web tiene RSS (`feeds_found:`), lee el feed: es más rápido y casi nunca está bloqueado.
- Si es una página de changelog, `monitor.py` te enseña exactamente qué líneas han cambiado desde la última vez.

**"Esta noticia ya no existe, ¿qué decía?"**
- `fetch.py URL --method archive` (o `--archive-date 20240101`) recupera la copia de Wayback Machine y te dice de qué fecha es.
