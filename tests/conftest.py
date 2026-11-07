import os
import sys
from pathlib import Path

import pytest

# The scripts re-exec themselves inside ~/.web-research-pro/venv when it exists.
# Never let that happen to the pytest process while test modules are imported.
os.environ["WRP_NO_REEXEC"] = "1"

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "web-research-pro" / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import server  # noqa: E402


@pytest.fixture(scope="session")
def site():
    httpd, base = server.start()
    yield base
    httpd.shutdown()


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Every test gets its own ~/.web-research-pro so sessions/snapshots never leak."""
    monkeypatch.setenv("WRP_HOME", str(tmp_path / "wrp-home"))
    monkeypatch.setenv("WRP_NO_REEXEC", "1")
    server.STATE.update({"price": "19,99 €", "counter": 0})
    yield


def _browser_works() -> bool:
    try:
        from wrp.browser import Browser

        with Browser() as b:
            b.start()
        return True
    except Exception:
        return False


BROWSER_OK = None


def browser_available() -> bool:
    """Launch Chromium once per run to find out whether browser tests can run."""
    global BROWSER_OK
    if BROWSER_OK is None:
        BROWSER_OK = _browser_works()
    return BROWSER_OK
