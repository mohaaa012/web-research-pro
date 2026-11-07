# Seguridad y privacidad

## Qué datos guarda y dónde

| Qué | Dónde | Protección |
|---|---|---|
| Sesiones iniciadas (cookies + localStorage) | `~/.web-research-pro/sessions/<nombre>.json` | Carpeta `700` y archivos `600` (solo tu usuario). Nunca se imprimen los valores |
| Instantáneas de `monitor.py` | `~/.web-research-pro/monitor/` | Carpeta privada |
| Entorno Python privado | `~/.web-research-pro/venv/` | Solo paquetes de `requirements.txt` |

Para "cerrar sesión", borra el archivo de la sesión (`login.py delete nombre`). Para borrarlo todo: elimina `~/.web-research-pro`.

## A quién se conecta

- **Siempre**: solo a la web que pides (y a los motores de búsqueda que elijas).
- **Solo si los escalones anteriores fallan**: `r.jina.ai` (recibe la URL, nunca cookies) y `archive.org`.
  Nunca se usan con `--session`, con direcciones privadas (localhost, 192.168.x.x, `.local`...) ni con `--no-third-party`.

## Principios de diseño

- Las contraseñas las escribes **tú** en una ventana de navegador real; el skill nunca las pide ni las recibe por el chat.
- No hay resolución de CAPTCHAs, ni evasión de sistemas anti-bots, ni rotación de proxies, ni falsificación de huellas del navegador.
- El rastreador respeta `robots.txt` y limita la velocidad.

## Informar de una vulnerabilidad

No abras un issue público. Usa **Security → Report a vulnerability** en este repositorio (aviso privado de GitHub)
e incluye pasos para reproducirlo. Se responderá lo antes posible.
