+++
id = "ADR-05"
name = "SERVER-SIDE-SAFE-MARKDOWN"
kind = "technology"
status = "proposed"
decision = "The server turns each message into HTML once, with markdown-it-py (raw HTML off, http and https links only, images as links, nesting at most 20) and then nh3 with an allowlist that matches the MessageBubble element list; the browser inserts that HTML only into a bubble and every other user string as text."
use_when = "Showing message text, or changing what Markdown a message may use."
do_not_use_when = "Showing a display name, an error or any other user string, which the client inserts with textContent."
use_instead = ["ADR-06"]
applies_to = ["backend/safe_markdown.py", "frontend/src/chat.ts"]
rules = [
  "Only backend/safe_markdown.py imports markdown_it, linkify_it or nh3, and app.py renders every message through to_safe_html before it enters the room.",
  "The renderer runs the commonmark preset with html off, maxNesting 20, linkify on with fuzzy links and emails off, strikethrough on, and a link check that allows only absolute http and https addresses.",
  "A render rule turns an image into a link to its address, with the alt text or the address as its text.",
  "nh3 allows only p, br, strong, em, s, code, pre, a, ul, ol, li, blockquote, h1 to h6 and hr; only href on a; schemes http and https; no relative URLs; target=_blank and rel=noopener noreferrer on every link.",
  "A test renders hostile 4,000-character inputs (deep nesting, runs of *, [, > and backticks) and fails if one takes 500 ms or more.",
  "The client sets innerHTML only from a message's html field, and only on the bubble body; it inserts names and every other user string with textContent inside <bdi>.",
  "Adding an element to the allowlist needs a matching style in component-specs and a test for it.",
]
example = "backend/safe_markdown.py"
enforced_by = "tests/test_safe_markdown.py"
+++

# ADR-05: Markdown becomes safe HTML on the server

## Context

Students will post HTML and script to see whether it runs in everyone's browser, and if it does,
the demo fails in front of the class (DOMAIN.md, risk 1). Messages also support Markdown with
code blocks and links (AC-8, AC-14), so the page cannot simply show plain text. Markdown
renderers pass raw HTML through by default, allow relative and unusual links, and turn images
into `<img>` tags that load third-party addresses.

## Decision

The server turns each message into HTML once, with markdown-it-py and then nh3 under an
allowlist; the browser inserts that HTML only into a bubble.

- One module owning the libraries gives one place to read and test everything a message can
  become.
- `html` off makes the renderer escape raw HTML, so it shows as text (AC-13). The link check
  closes `javascript:`, `data:`, `mailto:` and relative links, which the default check partly
  allows (`research/architect-codebase.md`). Fuzzy links are off so that only addresses written
  with `http://` or `https://` become links (AC-14).
- The image rule keeps a posted image from loading anything (AC-14). Disabling images instead
  leaves a stray "!" and, for `![](url)`, an empty link. markdown-it-py writes strikethrough as
  `<s>`, so the allowlist takes `s` and the stylesheet gives it the look component-specs sets for
  `<del>`.
- Rendering runs on the server's one event loop, so the nesting cap and the timed test keep one
  hostile message from stalling the room; the slowest probe input took 74 ms.
- nh3 is the second layer: even if a renderer rule had a bug, no tag, attribute or scheme
  outside the list reaches a browser. Its list is the MessageBubble table, so the sanitizer and
  the design cannot drift.
- Rendering once on the server means every open page and every replay get the same safe HTML,
  and pytest proves it. The page's Content Security Policy is the third layer.

INV-003 names the same test file.

## Consequences

Easier:

- One trust boundary, tested in Python with plain strings.
- The client stays free of a Markdown library and a sanitizer.

Harder:

- Three Python packages (markdown-it-py, linkify-it-py, nh3); nh3 is a compiled wheel.
- The client adds accessibility attributes after inserting the HTML, because the allowlist does
  not carry them.

## Rejected alternatives

| Option | Why it lost | What would change our mind |
|---|---|---|
| markdown-it or marked plus DOMPurify in the browser | Sanitizes with the browser's own parser, but each client must get it right, and tests need a DOM; two trust boundaries instead of one. | Clients that need the raw text, such as an editor preview. |
| Renderer with `html` off and no sanitizer | Safe today, but one renderer rule bug would reach every browser; the spec asks for sanitized output. | None. |
| bleach | Deprecated by its maintainers in favour of nh3. | None. |
| Python-Markdown | Passes raw HTML through by default and needs extensions for safe links. | None. |
