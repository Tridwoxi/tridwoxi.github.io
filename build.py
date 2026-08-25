"""Regenerate the website.

Parse README.md (source of truth) and create HTML files to avoid manually writing HTML.
The level 1 markdown heading becomes `/index.html`. Level 2 markdown headings become `/
<heading-slug>/index.html`. Paragraphs and inline links are supported.
"""

from __future__ import annotations

import html
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "README.md"
HEADING = re.compile(r"^(#{1,2})[ \t]+(.+?)[ \t]*#*[ \t]*$")
LINK = re.compile(r"\[([^]\n]+)]\(([^\s()]+)\)")
DOCUMENT_TEMPLATE = """<!doctype html><html lang="en"><head><meta charset="UTF-8" /><meta name="viewport" content="width=device-width, initial-scale=1.0" /><title>{title}</title><link rel="preconnect" href="https://fonts.googleapis.com" /><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin /><link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@300&display=swap" rel="stylesheet" /><link rel="stylesheet" href="{stylesheet}" /></head><body><main>{body}</main></body></html>\n"""


@dataclass(frozen=True)
class Section:
    heading_level: int
    title: str
    paragraphs: tuple[str, ...]


@dataclass(frozen=True)
class Page:
    title: str
    paragraphs: tuple[str, ...]
    route: str


def slugify(title: str) -> str:
    ascii_title = (
        unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    )
    return re.sub(r"[^a-z0-9]+", "-", ascii_title.lower()).strip("-")


def parse_paragraphs(lines: list[str]) -> tuple[str, ...]:
    paragraphs: list[str] = []
    paragraph_lines: list[str] = []

    def flush_paragraph() -> None:
        if paragraph_lines:
            paragraphs.append(" ".join(line.strip() for line in paragraph_lines))
            paragraph_lines.clear()

    for line in lines:
        if line.strip():
            paragraph_lines.append(line)
        else:
            flush_paragraph()
    flush_paragraph()
    return tuple(paragraphs)


def parse_sections(markdown: str) -> list[Section]:
    lines = markdown.splitlines()
    headings: list[tuple[int, int, str]] = []

    for line_index, line in enumerate(lines):
        heading = HEADING.match(line)
        if heading:
            level = len(heading.group(1))
            title = heading.group(2).strip()
            headings.append((line_index, level, title))

    sections: list[Section] = []
    for position, (line_index, level, title) in enumerate(headings):
        next_heading_index = (
            headings[position + 1][0] if position + 1 < len(headings) else len(lines)
        )
        sections.append(
            Section(
                heading_level=level,
                title=title,
                paragraphs=parse_paragraphs(lines[line_index + 1 : next_heading_index]),
            )
        )
    return sections


def build_pages(sections: list[Section]) -> list[Page]:
    pages: list[Page] = []
    routes: set[str] = set()
    for section in sections:
        route = "" if section.heading_level == 1 else slugify(section.title)
        if route in routes:
            raise ValueError("duplicate route")
        routes.add(route)
        pages.append(
            Page(
                title=section.title,
                paragraphs=section.paragraphs,
                route=route,
            )
        )
    return pages


def render_inline(text: str) -> str:
    output: list[str] = []
    position = 0
    for match in LINK.finditer(text):
        output.append(text[position : match.start()])
        label, url = match.groups()
        attributes = ""
        if url.startswith(("http://", "https://")):
            attributes = ' target="_blank" rel="noopener"'
        output.append(f'<a href="{url}"{attributes}>{label}</a>')
        position = match.end()
    output.append(text[position:])
    return "".join(output)


def render_body(page: Page) -> str:
    title = html.escape(page.title)
    content = "".join(
        f"<p>{render_inline(paragraph)}</p>" for paragraph in page.paragraphs
    )
    return f"<h1>{title}</h1>{content}"


def render_document(page: Page) -> str:
    stylesheet = "styles.css" if page.route == "" else "../styles.css"
    return DOCUMENT_TEMPLATE.format(
        title=html.escape(page.title),
        stylesheet=stylesheet,
        body=render_body(page),
    )


def output_path(page: Page) -> Path:
    return ROOT / page.route / "index.html"


def remove_stale_pages(expected: set[Path]) -> None:
    for candidate in ROOT.rglob("*.html"):
        if candidate not in expected:
            candidate.unlink()
            try:
                candidate.parent.rmdir()
            except OSError:
                pass


def main() -> None:
    sections = parse_sections(SOURCE.read_text(encoding="utf-8"))
    pages = build_pages(sections)
    rendered_pages = [(output_path(page), render_document(page)) for page in pages]
    expected = {destination for destination, _ in rendered_pages}
    remove_stale_pages(expected)

    for destination, document in rendered_pages:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(document, encoding="utf-8")
        print(destination.relative_to(ROOT))


if __name__ == "__main__":
    try:
        main()
    except ValueError as error:
        raise SystemExit(f"build error: {error}") from error
