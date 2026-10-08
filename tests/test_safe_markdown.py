import time
from html.parser import HTMLParser
from urllib.parse import unquote

import pytest

from backend.safe_markdown import to_safe_html

ALLOWED_TAGS = {
    "p",
    "br",
    "strong",
    "em",
    "s",
    "code",
    "pre",
    "a",
    "ul",
    "ol",
    "li",
    "blockquote",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "hr",
}
LINK_ATTRIBUTES = {"href", "target", "rel"}


class _Elements(HTMLParser):
    """Collects every start tag with its attributes, and each link's href and text."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tags: list[tuple[str, dict[str, str | None]]] = []
        self.links: list[tuple[str | None, str]] = []
        self._open_link: tuple[str | None, list[str]] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append((tag, dict(attrs)))
        if tag == "a":
            self._open_link = (dict(attrs).get("href"), [])

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._open_link is not None:
            self.links.append((self._open_link[0], "".join(self._open_link[1])))
            self._open_link = None

    def handle_data(self, data: str) -> None:
        if self._open_link is not None:
            self._open_link[1].append(data)


def _parse(html: str) -> _Elements:
    elements = _Elements()
    elements.feed(html)
    elements.close()
    return elements


def _text(html: str) -> str:
    class _Text(HTMLParser):
        def __init__(self) -> None:
            super().__init__(convert_charrefs=True)
            self.parts: list[str] = []

        def handle_data(self, data: str) -> None:
            self.parts.append(data)

    parser = _Text()
    parser.feed(html)
    return "".join(parser.parts)


RICH_MARKDOWN = """# Heading
###### Small heading

Some **bold**, *italic*, ~~gone~~ and `code` text.
A second line\\
after a hard break.

- one
- two

3. three
4. four

> quoted

---

```python
print("hi")
```

[site](https://example.com) and https://example.org/path.
![diagram](https://example.com/d.png)
<div onclick="alert(1)">raw</div>
"""


def test_should_show_script_tag_as_literal_text_when_message_holds_html_ac13() -> None:
    html = to_safe_html("<script>alert(1)</script>")

    assert "<script" not in html
    assert _text(html).strip() == "<script>alert(1)</script>"


def test_should_show_image_tag_as_literal_text_when_message_holds_onerror_ac13() -> None:
    html = to_safe_html('<img src=x onerror="alert(1)">')

    assert "<img" not in html
    assert _text(html).strip() == '<img src=x onerror="alert(1)">'


@pytest.mark.parametrize(
    ("markdown", "literal"),
    [
        ("**<b onmouseover=alert(1)>hi</b>**", "<b onmouseover=alert(1)>hi</b>"),
        ("- <iframe src=https://evil.example></iframe>", "<iframe src=https://evil.example>"),
        ("[<svg onload=alert(1)>](https://example.com)", "<svg onload=alert(1)>"),
        ("> <style>body{display:none}</style>", "<style>body{display:none}</style>"),
    ],
)
def test_should_escape_html_when_it_sits_inside_markdown_ac13(markdown: str, literal: str) -> None:
    html = to_safe_html(markdown)

    assert {tag for tag, _ in _parse(html).tags} <= ALLOWED_TAGS
    assert literal in _text(html)


def test_should_emit_only_allowlisted_elements_and_attributes_when_markdown_is_rich_ac13() -> None:
    elements = _parse(to_safe_html(RICH_MARKDOWN))

    used_tags = {tag for tag, _ in elements.tags}
    assert used_tags <= ALLOWED_TAGS
    assert {"h1", "h6", "strong", "em", "s", "code", "pre", "ul", "ol", "li"} <= used_tags
    assert {"blockquote", "hr", "br", "a", "p"} <= used_tags
    assert all(set(attrs) <= LINK_ATTRIBUTES for tag, attrs in elements.tags if tag == "a")
    assert all(not attrs for tag, attrs in elements.tags if tag != "a")


def test_should_keep_strikethrough_as_s_element_when_text_uses_tildes() -> None:
    assert to_safe_html("~~gone~~") == "<p><s>gone</s></p>\n"


def test_should_render_one_pre_code_block_with_line_breaks_when_fenced_ac8() -> None:
    html = to_safe_html("```\nline one\n  <b>line two</b>\n```")

    assert html == "<pre><code>line one\n  &lt;b&gt;line two&lt;/b&gt;\n</code></pre>\n"


@pytest.mark.parametrize(
    "markdown",
    [
        "[click](javascript:alert(1))",
        "[click](JaVaScRiPt:alert(1))",
        "[click](/api/leave)",
        "[click](../secret)",
        "[click](mailto:someone@example.com)",
        "[click](data:text/html;base64,PHNjcmlwdD4=)",
        "[click](vbscript:msgbox(1))",
        "<javascript:alert(1)>",
        "www.example.com",
        "someone@example.com",
    ],
)
def test_should_not_link_when_address_is_not_absolute_http_or_https_ac14(markdown: str) -> None:
    elements = _parse(to_safe_html(markdown))

    assert all(href is None for href, _ in elements.links)


@pytest.mark.parametrize(
    ("markdown", "href", "text"),
    [
        ("[the site](https://example.com/a?b=1)", "https://example.com/a?b=1", "the site"),
        ("see http://example.com/page", "http://example.com/page", "http://example.com/page"),
        ("<https://example.com/x>", "https://example.com/x", "https://example.com/x"),
    ],
)
def test_should_link_in_new_tab_without_opener_when_address_is_http_or_https_ac14(
    markdown: str, href: str, text: str
) -> None:
    elements = _parse(to_safe_html(markdown))

    assert elements.links == [(href, text)]
    link_attrs = next(attrs for tag, attrs in elements.tags if tag == "a")
    assert link_attrs == {"href": href, "target": "_blank", "rel": "noopener noreferrer"}


@pytest.mark.parametrize(
    "markdown",
    [
        'https://example.com/a"onmouseover="alert(1)',
        "https://example.com/a<script>alert(1)</script>",
        "https://example.com/a'b",
        "https://example.com/x>y",
    ],
)
def test_should_link_exactly_the_address_text_when_address_holds_quote_or_angle_ac14(
    markdown: str,
) -> None:
    html = to_safe_html(markdown)
    elements = _parse(html)

    assert len(elements.links) == 1
    href, text = elements.links[0]
    assert unquote(href or "") == text
    assert markdown.startswith(text)
    assert '"' not in (href or "")
    assert {tag for tag, _ in elements.tags} <= {"p", "a"}
    assert _text(html).strip() == markdown


@pytest.mark.parametrize("punctuation", [".", ",", ")", "!", "?", ";", ":"])
def test_should_leave_trailing_punctuation_outside_link_when_bare_address_ends_sentence(
    punctuation: str,
) -> None:
    elements = _parse(to_safe_html(f"(see https://example.com/page{punctuation}"))

    assert elements.links == [("https://example.com/page", "https://example.com/page")]


@pytest.mark.parametrize(
    ("markdown", "text"),
    [
        ("![a diagram](https://example.com/d.png)", "a diagram"),
        ("![](https://example.com/d.png)", "https://example.com/d.png"),
    ],
)
def test_should_render_image_as_link_never_image_when_markdown_has_image_ac14(
    markdown: str, text: str
) -> None:
    html = to_safe_html(markdown)
    elements = _parse(html)

    assert "<img" not in html
    assert elements.links == [("https://example.com/d.png", text)]
    assert _text(html).strip() == text


def test_should_not_link_image_when_its_address_is_not_http_or_https_ac14() -> None:
    html = to_safe_html("![x](javascript:alert(1)) ![y](data:image/png;base64,AAAA)")

    assert "<img" not in html
    assert all(href is None for href, _ in _parse(html).links)


def test_should_render_empty_html_when_message_is_only_a_link_definition() -> None:
    assert to_safe_html("[ref]: https://example.com").strip() == ""


HOSTILE_INPUTS = {
    "nested quotes": ">" * 4000,
    "nested lists": "- " * 2000,
    "emphasis run": "*" * 4000,
    "alternating emphasis": "*a_" * 1333,
    "bracket run": "[" * 4000,
    "link openers": "[a](" * 1000,
    "backtick run": "`" * 4000,
    "mixed backticks": "`a``" * 1000,
    "image openers": "![" * 2000,
    "angle autolinks": "<https://a" * 400,
    "nested brackets": "[" * 2000 + "]" * 2000,
}


@pytest.mark.parametrize("name", sorted(HOSTILE_INPUTS))
def test_should_render_within_500_ms_when_input_is_hostile_4000_characters(name: str) -> None:
    hostile = HOSTILE_INPUTS[name]
    started = time.perf_counter()

    html = to_safe_html(hostile)

    assert time.perf_counter() - started < 0.5
    assert {tag for tag, _ in _parse(html).tags} <= ALLOWED_TAGS
