"""Message Markdown becomes sanitized HTML here, once, on the server (ADR-05).

markdown-it-py renders with raw HTML off, so any HTML a student types shows as text. nh3 then
keeps only the MessageBubble elements (component-specs.md) and only absolute http and https
links, each opening in a new tab without access to the chat page.
"""

from collections.abc import Sequence
from typing import Final

import nh3
from markdown_it import MarkdownIt
from markdown_it.common.utils import escapeHtml
from markdown_it.renderer import RendererHTML
from markdown_it.rules_core import StateCore
from markdown_it.token import Token
from markdown_it.utils import EnvType, OptionsDict

MAX_NESTING: Final = 20

ALLOWED_TAGS: Final = frozenset(
    {"p", "br", "strong", "em", "s", "code", "pre", "a", "ul", "ol", "li", "blockquote"}
    | {"h1", "h2", "h3", "h4", "h5", "h6", "hr"}
)


def _image_as_link(
    renderer: RendererHTML,
    tokens: Sequence[Token],
    index: int,
    options: OptionsDict,
    env: EnvType,
) -> str:
    """Render an image as a link to its address, so a posted image never loads (AC-14)."""
    image = tokens[index]
    address = str(image.attrGet("src") or "")
    alt = renderer.renderInlineAsText(image.children or [], options, env)
    return f'<a href="{escapeHtml(address)}">{escapeHtml(alt or address)}</a>'


def _trailing_colon_outside_links(state: StateCore) -> None:
    """Move a colon that ends a bare address out of its link, as for "." or ")" (AC-14)."""
    for block in state.tokens:
        children = block.children or []
        for index in reversed(range(len(children) - 2)):
            opening, text = children[index], children[index + 1]
            href = str(opening.attrGet("href") or "")
            if opening.markup != "linkify" or not href.endswith(":"):
                continue
            colons = href[len(href.rstrip(":")) :]
            opening.attrSet("href", href.removesuffix(colons))
            text.content = text.content.removesuffix(colons)
            children.insert(index + 3, Token("text", "", 0, content=colons))


def _make_renderer() -> MarkdownIt:
    renderer = MarkdownIt(
        "commonmark", {"html": False, "linkify": True, "maxNesting": MAX_NESTING}
    ).enable(["linkify", "strikethrough"])
    if renderer.linkify is None:
        raise RuntimeError("linkify-it-py is missing; install the project's dependencies.")
    # Only addresses written with http:// or https:// become links.
    renderer.linkify.set({"fuzzy_link": False, "fuzzy_email": False, "fuzzy_ip": False})
    renderer.core.ruler.after("linkify", "trailing_colon", _trailing_colon_outside_links)
    renderer.add_render_rule("image", _image_as_link)
    return renderer


_RENDERER: Final = _make_renderer()

_SANITIZER: Final = nh3.Cleaner(
    tags=set(ALLOWED_TAGS),
    clean_content_tags=set(),
    attributes={"a": {"href"}},
    url_schemes={"http", "https"},
    url_relative="deny",
    link_rel="noopener noreferrer",
    set_tag_attribute_values={"a": {"target": "_blank"}},
)


def to_safe_html(text: str) -> str:
    """Render message Markdown to sanitized HTML; never raises on text that encodes as UTF-8."""
    return _SANITIZER.clean(_RENDERER.render(text))
