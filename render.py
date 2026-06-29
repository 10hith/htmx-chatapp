from __future__ import annotations

import re

import nh3

ALLOWED_TAGS = {
    "div",
    "span",
    "p",
    "section",
    "article",
    "header",
    "footer",
    "main",
    "aside",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "ul",
    "ol",
    "li",
    "dl",
    "dt",
    "dd",
    "table",
    "thead",
    "tbody",
    "tfoot",
    "tr",
    "th",
    "td",
    "caption",
    "colgroup",
    "col",
    "details",
    "summary",
    "blockquote",
    "pre",
    "code",
    "strong",
    "b",
    "em",
    "i",
    "u",
    "s",
    "small",
    "mark",
    "sub",
    "sup",
    "abbr",
    "time",
    "figure",
    "figcaption",
    "hr",
    "br",
}
ALLOWED_ATTRS = {"*": {"class"}}
CLEAN_CONTENT_TAGS = {"script", "style", "svg"}
SPINNER_HTML = '<span class="loading loading-dots loading-sm opacity-60"></span>'

_FENCE_RE = re.compile(r"```[ \t]*[A-Za-z0-9]*[ \t]*\r?\n?(.*?)(?:```|\Z)", re.DOTALL)


def sanitize_html(raw: str | None) -> str:
    return nh3.clean(
        raw or "",
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRS,
        clean_content_tags=CLEAN_CONTENT_TAGS,
        strip_comments=True,
    )


def split_message(text: str | None) -> tuple[str, str | None]:
    if not text:
        return "", None
    match = _FENCE_RE.search(text)
    if not match:
        return text.strip(), None
    raw_html = (match.group(1) or "").strip()
    return text[: match.start()].strip(), raw_html or None
