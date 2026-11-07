"""web-research-pro: shared library behind the skill's command-line scripts.

The scripts in the parent folder (fetch.py, search.py, login.py, crawl.py,
monitor.py, doctor.py) are thin command-line wrappers around these modules.
Everything degrades gracefully: with only the Python standard library the
HTTP path, the built-in HTML extractor, feeds, JSON and search all work;
Playwright, trafilatura and pypdf add the browser, better article extraction
and PDF text when they are installed.
"""

from .config import VERSION

__all__ = ["VERSION"]
