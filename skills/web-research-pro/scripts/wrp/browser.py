"""Real Chromium browser (via Playwright) for pages that need JavaScript.

One browser process is started lazily and reused for every URL in the same
command, with a fresh, isolated context per page. This is a normal browser:
no CAPTCHA solving and no fingerprint spoofing. It simply runs the page's
JavaScript the way the user's own browser would.
"""

from __future__ import annotations

import os
import platform
import time
import urllib.parse

from .config import accept_language, browser_user_agent


class BrowserUnavailable(Exception):
    pass


def playwright_installed() -> bool:
    try:
        import playwright.sync_api  # noqa: F401

        return True
    except ImportError:
        return False


def proxy_from_env() -> dict | None:
    raw = (os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
           or os.environ.get("ALL_PROXY") or os.environ.get("all_proxy"))
    if not raw:
        return None
    parts = urllib.parse.urlsplit(raw if "://" in raw else "http://" + raw)
    if not parts.hostname:
        return None
    server = f"{parts.scheme or 'http'}://{parts.hostname}"
    if parts.port:
        server += f":{parts.port}"
    proxy: dict = {"server": server}
    if parts.username:
        proxy["username"] = urllib.parse.unquote(parts.username)
        proxy["password"] = urllib.parse.unquote(parts.password or "")
    bypass = os.environ.get("NO_PROXY") or os.environ.get("no_proxy")
    if bypass:
        proxy["bypass"] = bypass
    return proxy


_LOCALE = None


def _locale() -> str:
    global _LOCALE
    if _LOCALE is None:
        _LOCALE = accept_language().split(",")[0] or "en-US"
    return _LOCALE


class Browser:
    def __init__(self, headed: bool = False):
        self.headed = headed
        self._pw = None
        self._browser = None
        self.engine = ""

    # -- lifecycle -----------------------------------------------------------
    def start(self):
        if self._browser is not None:
            return self._browser
        if not playwright_installed():
            raise BrowserUnavailable(
                "playwright_not_installed: run `python3 doctor.py --setup` (or install.sh) to add the browser"
            )
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        launch: dict = {"headless": not self.headed}
        proxy = proxy_from_env()
        if proxy:
            launch["proxy"] = proxy
        exe = os.environ.get("WRP_CHROMIUM_PATH")
        attempts = []
        if exe:
            attempts.append(("custom", dict(launch, executable_path=exe)))
        attempts.append(("chromium", launch))
        attempts.append(("chrome", dict(launch, channel="chrome")))
        if platform.system() == "Windows":
            attempts.append(("msedge", dict(launch, channel="msedge")))
        errors = []
        for label, options in attempts:
            try:
                self._browser = self._pw.chromium.launch(**options)
                self.engine = label
                return self._browser
            except Exception as exc:  # try the next option
                errors.append(f"{label}: {str(exc).splitlines()[0][:200]}")
        self.close()
        hint = "run `python3 doctor.py --setup` to download Chromium"
        if platform.system() == "Linux":
            hint += " (on Linux you may also need: python3 -m playwright install-deps chromium)"
        raise BrowserUnavailable("browser_launch_failed: " + " | ".join(errors) + f". Fix: {hint}")

    def close(self) -> None:
        try:
            if self._browser is not None:
                self._browser.close()
        except Exception:
            pass
        try:
            if self._pw is not None:
                self._pw.stop()
        except Exception:
            pass
        self._browser = None
        self._pw = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # -- rendering -------------------------------------------------------------
    def render(
        self,
        url: str,
        *,
        storage_state: dict | None = None,
        wait_for: str | None = None,
        clicks: tuple = (),
        scroll: int = 0,
        wait_ms: int = 0,
        screenshot: str | None = None,
        timeout: float = 30,
        block_media: bool = True,
        extra_headers: dict | None = None,
    ) -> dict:
        """Load a page like a person would and return its final HTML."""
        browser = self.start()
        started = time.monotonic()
        version = getattr(browser, "version", "") or ""
        major = version.split(".")[0] if version[:1].isdigit() else None
        context_args: dict = {
            "user_agent": browser_user_agent(major),
            "locale": _locale(),
            "viewport": {"width": 1366, "height": 900},
            "java_script_enabled": True,
        }
        if storage_state is not None:
            context_args["storage_state"] = storage_state
        if extra_headers:
            context_args["extra_http_headers"] = extra_headers
        context = browser.new_context(**context_args)
        result: dict = {"status": None, "final_url": url, "html": "", "title": "", "error": None,
                        "storage_state": None, "screenshot": None, "notes": []}
        try:
            if block_media and not screenshot:
                def _route(route):
                    if route.request.resource_type in ("image", "media", "font"):
                        return route.abort()
                    return route.continue_()

                context.route("**/*", _route)
            page = context.new_page()
            page.set_default_timeout(timeout * 1000)
            response = page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
            result["status"] = response.status if response else None
            try:
                page.wait_for_load_state("networkidle", timeout=min(10000, timeout * 1000))
            except Exception:
                result["notes"].append("network never went fully idle (normal for live sites)")
            if wait_for:
                try:
                    page.wait_for_selector(wait_for, timeout=timeout * 1000)
                except Exception:
                    result["notes"].append(f"selector not found: {wait_for}")
            for selector in clicks:
                try:
                    page.click(selector, timeout=5000)
                    page.wait_for_timeout(1200)
                except Exception:
                    result["notes"].append(f"could not click: {selector}")
            for _ in range(max(0, scroll)):
                page.evaluate("window.scrollBy(0, Math.max(window.innerHeight, 900) * 2)")
                page.wait_for_timeout(900)
                try:
                    page.wait_for_load_state("networkidle", timeout=3000)
                except Exception:
                    pass
            self._wait_for_stable_text(page, max_ms=6000)
            if wait_ms:
                page.wait_for_timeout(wait_ms)
            result["html"] = page.content()
            result["final_url"] = page.url
            try:
                result["title"] = page.title()
            except Exception:
                pass
            if screenshot:
                page.screenshot(path=screenshot, full_page=True)
                result["screenshot"] = screenshot
            if storage_state is not None:
                result["storage_state"] = context.storage_state()
        except Exception as exc:
            message = str(exc).splitlines()[0][:300]
            if "ERR_NAME_NOT_RESOLVED" in message:
                message = "dns_error: the host name could not be resolved"
            elif "ERR_TUNNEL_CONNECTION_FAILED" in message or "ERR_PROXY" in message:
                message = "proxy_blocked: the network proxy refused the connection"
            elif "Timeout" in message:
                message = f"timeout: page did not finish loading in {timeout:.0f}s"
            result["error"] = message
            try:
                result["html"] = page.content()  # keep whatever rendered
                result["final_url"] = page.url
            except Exception:
                pass
        finally:
            result["elapsed_ms"] = int((time.monotonic() - started) * 1000)
            try:
                context.close()
            except Exception:
                pass
        return result

    @staticmethod
    def _wait_for_stable_text(page, max_ms: int = 6000) -> None:
        """Single-page apps keep painting after 'load'. Wait until the amount of
        visible text stops changing (or give up after max_ms)."""
        deadline = time.monotonic() + max_ms / 1000
        last = -1
        stable = 0
        while time.monotonic() < deadline:
            try:
                length = page.evaluate("document.body ? document.body.innerText.length : 0")
            except Exception:
                return
            if length == last and length > 0:
                stable += 1
                if stable >= 2:
                    return
            else:
                stable = 0
            last = length
            page.wait_for_timeout(400)
