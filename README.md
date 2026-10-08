# MSTC Chat

A live chat room for one lecture, where students send the lecturer feedback
and links. It is also the worked example in a lecture on spec-driven
development. See `DOMAIN.md` and `PROJECT.md`.

## Setup

```sh
uv sync                        # Python tools
npm --prefix frontend install  # TypeScript tools
pre-commit install             # commit, commit-message and pre-push hooks
cp .env.example .env           # then fill in CLASS_PASSWORD and SESSION_SECRET
```
