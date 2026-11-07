"""Formatting results for Claude (and humans) to read."""

from __future__ import annotations

import json
import re
import urllib.parse
from pathlib import Path

from .fetcher import FetchResult


def _chain(result: FetchResult) -> str:
    parts = []
    for a in result.attempts:
        label = a["method"]
        if a["ok"]:
            parts.append(f"{label}=ok")
        else:
            reason = (a.get("reason") or "failed").split(":")[0]
            parts.append(f"{label}={reason}")
    return " -> ".join(parts)


def header(result: FetchResult, shown: tuple[int, int] | None = None) -> str:
    lines = ["=== web-research-pro fetch ==="]
    lines.append(f"title: {result.title or '(none)'}")
    lines.append(f"url: {result.final_url or result.url}")
    if result.final_url and result.final_url.rstrip("/") != result.url.rstrip("/"):
        lines.append(f"requested: {result.url}")
    lines.append(f"ok: {'yes' if result.ok else 'NO'}" + (f"  (reason: {result.reason})" if not result.ok else ""))
    lines.append(f"method: {result.method or '-'}   attempts: {_chain(result)}")
    if result.status is not None:
        lines.append(f"http_status: {result.status}")
    if result.extractor:
        lines.append(f"content: {result.content_type or '-'} via {result.extractor}")
    meta = result.metadata
    for key in ("published", "author", "site_name", "pages", "items", "archive_url"):
        if meta.get(key):
            lines.append(f"{key}: {meta[key]}")
    if result.archived_at:
        lines.append(f"archived_at: {result.archived_at}")
    if result.screenshot:
        lines.append(f"screenshot: {result.screenshot}")
    if meta.get("feeds"):
        lines.append(f"feeds_found: {', '.join(meta['feeds'][:3])}")
    lines.append(f"fetched_at: {result.fetched_at}")
    if shown is not None:
        start, end = shown
        lines.append(f"chars: {result.chars} (showing {start}-{end})")
    else:
        lines.append(f"chars: {result.chars}")
    for warning in result.warnings:
        lines.append(f"warning: {warning}")
    for tip in result.suggestions:
        lines.append(f"suggestion: {tip}")
    lines.append("---")
    return "\n".join(lines)


def render(result: FetchResult, fmt: str = "markdown", max_chars: int = 25000, offset: int = 0,
           show_links: bool = False, max_links: int = 150) -> str:
    if fmt == "json":
        data = result.to_dict(include_html=bool(result.html))
        if max_chars and len(data["content"]) > offset + max_chars:
            data["content"] = data["content"][offset:offset + max_chars]
            data["truncated"] = True
            data["next_offset"] = offset + max_chars
        elif offset:
            data["content"] = data["content"][offset:]
        if not show_links:
            data["links"] = len(result.links)
        else:
            data["links"] = [{"url": u, "text": t} for u, t in result.links[:max_links]]
        return json.dumps(data, ensure_ascii=False, indent=2)
    if fmt == "html":
        return result.html or "(no HTML kept; this content was not an HTML page)"
    content = result.content or ""
    if not result.ok and content:
        # Failed attempts may have produced a block page: show little of it.
        max_chars = min(max_chars or 1500, 1500)
    end = min(len(content), offset + max_chars) if max_chars else len(content)
    body = content[offset:end]
    out = [header(result, (offset, end))]
    if not result.ok and body:
        out.append("[partial content from a failed attempt; may be a block or login page]")
    out.append(body if body else "(no content)")
    if end < len(content):
        out.append(f"\n--- [truncated: {len(content) - end} more chars. Continue with --offset {end}, "
                   f"or save everything with --out FILE] ---")
    if show_links and result.links:
        out.append("\n=== links ===")
        for url, text in result.links[:max_links]:
            out.append(f"- [{text}]({url})")
        if len(result.links) > max_links:
            out.append(f"- ... {len(result.links) - max_links} more")
    return "\n".join(out)


def slugify_url(url: str, max_len: int = 80) -> str:
    parts = urllib.parse.urlsplit(url)
    raw = (parts.hostname or "page") + parts.path
    if parts.query:
        raw += "-" + parts.query
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", raw).strip("-._")
    return (slug[:max_len] or "page").rstrip("-.")


def save(result: FetchResult, path: Path, fmt: str = "markdown") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "json":
        text = render(result, "json", max_chars=0, show_links=True)
    elif fmt == "html":
        text = render(result, "html")
    else:
        text = header(result) + "\n" + (result.content or "(no content)") + "\n"
    path.write_text(text, encoding="utf-8")
    return path
