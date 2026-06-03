"""Rendering helpers for Markdown and HTML surveillance reports.

Kept dependency-free (no Jinja/markdown packages required) so the prototype
runs anywhere. ``render_html`` performs a minimal Markdown-to-HTML conversion
sufficient for headings, tables, lists and paragraphs produced by the report
writer.
"""

from __future__ import annotations

import html
import re
from typing import Any


def md_table(headers: list[str], rows: list[list[Any]]) -> str:
    """Render a GitHub-flavoured Markdown table."""

    if not rows:
        return "_No data._\n"
    head = "| " + " | ".join(str(h) for h in headers) + " |"
    sep = "| " + " | ".join("---" for _ in headers) + " |"
    body = "\n".join("| " + " | ".join(str(c) for c in row) + " |" for row in rows)
    return f"{head}\n{sep}\n{body}\n"


def md_section(title: str, level: int = 2) -> str:
    """Return a Markdown heading line."""

    return f"{'#' * level} {title}\n"


def _inline(text: str) -> str:
    """Convert inline Markdown emphasis/code to HTML on an escaped string."""

    text = html.escape(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"`(.+?)`", r"<code>\1</code>", text)
    return text


def render_html(markdown_text: str, title: str = "MetaMAVS Report") -> str:
    """Convert a subset of Markdown to a standalone HTML document.

    Supports ATX headings, pipe tables, unordered lists, horizontal rules and
    paragraphs -- enough for the reports MetaMAVS generates.
    """

    lines = markdown_text.splitlines()
    out: list[str] = []
    i = 0
    in_list = False

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            out.append("</ul>")
            in_list = False

    while i < len(lines):
        line = lines[i]

        # Tables: a header row followed by a separator row of dashes.
        if line.startswith("|") and i + 1 < len(lines) and re.match(r"^\|[\s:|-]+\|$", lines[i + 1]):
            close_list()
            header_cells = [c.strip() for c in line.strip("|").split("|")]
            out.append("<table><thead><tr>")
            out.extend(f"<th>{_inline(c)}</th>" for c in header_cells)
            out.append("</tr></thead><tbody>")
            i += 2
            while i < len(lines) and lines[i].startswith("|"):
                cells = [c.strip() for c in lines[i].strip("|").split("|")]
                out.append("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in cells) + "</tr>")
                i += 1
            out.append("</tbody></table>")
            continue

        heading = re.match(r"^(#{1,6})\s+(.*)$", line)
        if heading:
            close_list()
            level = len(heading.group(1))
            out.append(f"<h{level}>{_inline(heading.group(2))}</h{level}>")
        elif line.strip() in {"---", "***", "___"}:
            close_list()
            out.append("<hr/>")
        elif re.match(r"^\s*[-*]\s+", line):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{_inline(re.sub(r'^\s*[-*]\s+', '', line))}</li>")
        elif line.strip() == "":
            close_list()
        else:
            close_list()
            out.append(f"<p>{_inline(line)}</p>")
        i += 1

    close_list()
    body = "\n".join(out)
    return (
        "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\"/>\n"
        f"<title>{html.escape(title)}</title>\n"
        "<style>\n"
        "body{font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;"
        "max-width:960px;margin:2rem auto;padding:0 1rem;color:#1a1a1a;line-height:1.5}\n"
        "h1,h2,h3{color:#0b3d66}\n"
        "table{border-collapse:collapse;width:100%;margin:1rem 0}\n"
        "th,td{border:1px solid #ccc;padding:6px 10px;text-align:left}\n"
        "th{background:#f0f4f8}\ncode{background:#f3f3f3;padding:1px 4px;border-radius:3px}\n"
        "hr{border:none;border-top:1px solid #ddd;margin:1.5rem 0}\n"
        "</style>\n</head>\n<body>\n"
        f"{body}\n</body>\n</html>\n"
    )
