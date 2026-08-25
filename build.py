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
STYLES = """body{background:#eee;color:#111;font-family:"IBM Plex Sans",sans-serif;font-size:1.25rem;font-weight:300;line-height:1.6}main{max-width:70ch;margin:0 auto;padding:4rem 1.5rem}main>:last-child{margin-bottom:0}h1{font-size:4rem;margin:0 0 2rem;transform:translateX(var(--optical-left,0))}p{margin:0 0 2rem}a,a:visited{color:#985333}@media(prefers-color-scheme:dark){body{background:#222;color:#eee}a,a:visited{color:#d1977a}}"""
DOCUMENT_TEMPLATE = """<!doctype html><html lang="en"><head><meta charset="UTF-8" /><meta name="viewport" content="width=device-width, initial-scale=1.0" /><title>{title}</title><link rel="preconnect" href="https://fonts.googleapis.com" /><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin /><link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@300&display=swap" rel="stylesheet" /><style>{styles}</style></head><body><main>{body}</main></body></html>\n"""

# IBM Plex Sans Light v23 has 1,000 design units per em. These are the left outline
# bounds (xMin) of its capitals, in design units.
FONT_UNITS_PER_EM = 1000
BODY_TO_HEADING_SIZE = 1.25 / 4
CAPITAL_LEFT_BOUNDS = {
    "A": 27,
    "B": 99,
    "C": 63,
    "D": 99,
    "E": 99,
    "F": 99,
    "G": 63,
    "H": 99,
    "I": 63,
    "J": 26,
    "K": 99,
    "L": 99,
    "M": 99,
    "N": 99,
    "O": 63,
    "P": 99,
    "Q": 63,
    "R": 99,
    "S": 42,
    "T": 20,
    "U": 93,
    "V": 24,
    "W": 24,
    "X": 26,
    "Y": 16,
    "Z": 37,
}
AVERAGE_CAPITAL_LEFT_BOUND = sum(CAPITAL_LEFT_BOUNDS.values()) / len(
    CAPITAL_LEFT_BOUNDS
)


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


def heading_left_offset(title: str) -> str | None:
    heading_bound = CAPITAL_LEFT_BOUNDS.get(title[:1])
    if heading_bound is None:
        return None

    offset = (
        -heading_bound + AVERAGE_CAPITAL_LEFT_BOUND * BODY_TO_HEADING_SIZE
    ) / FONT_UNITS_PER_EM
    value = f"{float(offset):.9f}".rstrip("0").rstrip(".")
    return f"{value}em"


def render_body(page: Page) -> str:
    title = html.escape(page.title)
    optical_offset = heading_left_offset(page.title)
    heading_style = (
        f' style="--optical-left:{optical_offset}"' if optical_offset else ""
    )
    content = "".join(
        f"<p>{render_inline(paragraph)}</p>" for paragraph in page.paragraphs
    )
    return f"<h1{heading_style}>{title}</h1>{content}"


def render_document(page: Page) -> str:
    return DOCUMENT_TEMPLATE.format(
        title=html.escape(page.title),
        styles=STYLES,
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
