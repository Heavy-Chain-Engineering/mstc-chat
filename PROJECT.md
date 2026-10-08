# MSTC Chat

A small live chat room for one lecture, where master's students send the
lecturer feedback and links; it doubles as the lecture's spec-driven
development demo.

Read `DOMAIN.md` first. It explains the purpose, the risks and the design
rules that follow from them.

## Current phase

Greenfield. The repository holds only setup and context files. The first
feature, the chat app with its login page and its Cloud Run deployment, starts
through `/etc:start`. The plan is to build and deploy it before the lecture,
then show the spec and re-run a deploy live in class.

## Where things live

- `backend/`: the Python server (HTTP API, login, live message stream).
- `frontend/`: the TypeScript and daisyUI browser client.
- `tests/`: the Python tests.
- `DOMAIN.md`, `PROJECT.md`: the project's context.
- `.github/`: CI (`ci.yml`) and Dependabot.

Remote: https://github.com/Heavy-Chain-Engineering/mstc-chat (private).

The feature's spec and architecture fix the exact layout inside these folders.

## Tech stack

- Backend: Python, managed with uv.
- Frontend: TypeScript, Tailwind CSS and daisyUI.
- Live updates: Server-Sent Events.
- Hosting: one container on Google Cloud Run, with the free `run.app` HTTPS
  URL. No database.

## Languages

- python
- typescript

## How to build and test

The check commands that prove the project green live in
`.etc_sdlc/settings.toml`, in its `[checks]` table.

## Decision records to read first

None yet. The first ones will come from the chat feature's architecture node.

## Standing decisions

- Decision records: `docs/decisions/`
- Invariants: `docs/invariants.md`
- Antipatterns: `docs/antipatterns.md`
- Ratified architecture baseline: `docs/architecture-baseline.yaml`
- Project standards: `docs/standards/`

## Setup status

Declined: ETC agent rules in `AGENTS.md` (offered, not recommended)
Paused:
