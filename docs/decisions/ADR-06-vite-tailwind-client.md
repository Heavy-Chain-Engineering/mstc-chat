+++
id = "ADR-06"
name = "VITE-TAILWIND-CLIENT"
kind = "technology"
status = "accepted"
decision = "The browser client is plain TypeScript with no UI framework, styled with Tailwind CSS 4 and daisyUI 5 in the mstc theme, built by Vite into frontend/dist, tested with Vitest, and served by the Python server from the same container."
use_when = "Changing anything the browser runs or shows: markup, styles, fonts, client logic, client tests."
do_not_use_when = "Rendering message Markdown, which the server does."
use_instead = ["ADR-05"]
applies_to = ["frontend/"]
rules = [
  "frontend/index.html holds the markup of both screens; each screen's behaviour lives in its own module under frontend/src/.",
  "Client state lives in frontend/src/room.ts as pure functions with no DOM access.",
  "Tests sit beside their module as <name>.test.ts and run with vitest run; DOM tests opt in with // @vitest-environment jsdom.",
  "Styles use the mstc theme roles and tokens from DESIGN.md, never raw hex values in markup or code.",
  "Fonts come from the @fontsource packages and are served by the app; their licence texts sit in frontend/public/fonts/.",
  "The build writes only to frontend/dist/, which git ignores; the server serves index.html with Cache-Control: no-cache.",
  "No script loads from another origin.",
  "The client writes to browser storage only the reload record of ADR-04 (draft, restarted flag, instance id) in sessionStorage, and deletes it once restored.",
]
example = "frontend/src/room.ts"
enforced_by = "npm --prefix frontend run test, in CI and in the project's check commands"
+++

# ADR-06: A Vite-built TypeScript client with Tailwind and daisyUI

## Context

PROJECT.md names TypeScript, Tailwind CSS and daisyUI for the client, but the repository has no
build tool, no test runner and no way to serve the client. Tailwind 4 and daisyUI 5 are compiled
from CSS at build time, so the client needs a build step. The spec asks for frontend tests in CI
(AC-24). The app must stay small enough to explain in a lecture (DOMAIN.md, design implication
6), and students' browsers should contact no third party.

## Decision

The client is plain TypeScript, styled with Tailwind 4 and daisyUI 5, built by Vite into
`frontend/dist/`, tested with Vitest and served by the Python server.

Ruled by the person on 2026-10-08: the person ratified this choice of technology.

- Two screens do not need a component framework; markup in `index.html` and one module per
  screen read top to bottom.
- Keeping state in pure functions lets the most important client behaviour (order, replay,
  restart) be tested without a DOM.
- Vitest reads Vite's own configuration, so one tool chain builds and tests; jsdom serves the few
  tests that need elements and events.
- Theme roles keep the brand rules in one theme block, as DESIGN.md sets.
- Fontsource packages put the font files under npm's version control and Dependabot's watch.
  Serving them from the app keeps students' addresses away from Google; the licence texts
  travel with them.
- Building into the ignored `dist/` keeps generated files out of git; `no-cache` on
  `index.html` makes a reload after a redeploy fetch the new build.

## Consequences

Easier:

- One container serves the whole app; the Docker build compiles the client in its own stage.
- The client has six small modules and no framework to learn.

Harder:

- DOM updates are written by hand.
- Vite, Vitest and jsdom are new dev dependencies to keep current.

## Rejected alternatives

| Option | Why it lost | What would change our mind |
|---|---|---|
| React, Vue or Svelte | A framework and its build for two screens. | Many screens or shared components. |
| `tsc` plus the Tailwind CLI | Two build tools and no test runner. | A rule against a bundler. |
| Jest | Needs its own TypeScript transform; Vitest reuses Vite's. | None. |
| Google Fonts from their servers | Sends every student's address to Google and needs a wider CSP. | None. |
| Committing the font files by hand | Works, but nothing tracks their version. | Fontsource dropping one of the fonts. |
