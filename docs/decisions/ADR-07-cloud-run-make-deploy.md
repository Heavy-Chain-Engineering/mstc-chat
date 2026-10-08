+++
id = "ADR-07"
name = "CLOUD-RUN-MAKE-DEPLOY"
kind = "pattern"
status = "accepted"
decision = "The app ships as one multi-stage, non-root container built from source by Cloud Build under a dedicated build account, and every Cloud Run operation is one Make target that sets all of its settings on the command line."
use_when = "Changing how the app is run locally (make dev, make build-client), built into an image, deployed, warmed up, cooled down, rolled back or rehearsed, or which Cloud Run settings it runs with."
do_not_use_when = "Changing what CI checks, which lives in .github/workflows/ci.yml and never deploys."
use_instead = ["ADR-06"]
applies_to = ["Dockerfile", ".dockerignore", ".gcloudignore", "Makefile"]
rules = [
  "The Dockerfile has a Node stage that runs npm ci --ignore-scripts and builds the client, and a Python stage that installs from uv.lock with uv sync --locked --no-dev --no-build and copies only frontend/dist, backend/, pyproject.toml and uv.lock; it starts with # check=error=true.",
  "The runtime stage runs as a non-root user and starts python -m backend; base images are pinned to exact version tags.",
  "No secret is an ARG, an ENV or a build input; .dockerignore and .gcloudignore exclude .git, .env and .env.*.",
  "The runtime account is mstc-chat-run@mstc-chat.iam.gserviceaccount.com, which the VP created, with Secret Accessor on the two secrets only; make setup creates the build account mstc-chat-build with only the roles Google lists for a source-deploy build account and never Editor.",
  "make deploy sets the service maximum of 1 instance, concurrency 250, a 60-second timeout, 1 vCPU, 512 MiB, no start-up CPU boost, public access through --no-invoker-iam-check (never --allow-unauthenticated), the runtime account, the build account and both secrets as references pinned to version numbers it looks up at deploy time.",
  "make deploy prints the service address, the commit and git status --short.",
  "make dev builds the client and runs the server locally with the settings in .env; make build-client builds the client only.",
  "make warm-up and make cool-down change only the service-level minimum, which creates no revision.",
  "Secret values enter through standard input or a silent prompt, never a command-line argument.",
]
example = "Makefile"
enforced_by = ".github/workflows/ci.yml image job: docker build with check=error=true"
+++

# ADR-07: One container, one Make target per Cloud Run operation

## Context

The lecturer deploys by hand, from a laptop, sometimes on a projected screen (gray-areas-spec.md
GA-010). A deploy that forgets one setting can split the room (more than one instance), show a
secret's value, or run as a service account that can edit the whole project. A source deploy
runs the Docker build in Cloud Build, whose default identity may also hold Editor, and `npm ci`
runs every dependency's install script during that build. A redeploy mid-lecture is part of the
demo, so the same command must work the same way every time. Cloud Run runs a container as root
unless the image names another user (research R17), and build arguments persist in images (R15).

## Decision

The app ships as one multi-stage, non-root container built by Cloud Build under a dedicated
build account, and each Cloud Run operation is one Make target that sets all of its settings.

Ruled by the person on 2026-10-08: deployment is one manual command, and automated deploy is out
of scope (gray-areas-spec.md GA-010). The VP ruled on the same day that the deploy sets no
start-up CPU boost and that `make dev` and `make build-client` stay (gray-areas-architect.md
GA-043).

- Two stages keep Node, `node_modules` and the TypeScript sources out of the runtime image;
  `check=error=true` turns Docker's build checks, including the one for secrets in `ARG` and
  `ENV`, into failures.
- Install scripts off, wheels only, and a build account without Editor mean a compromised
  dependency cannot act on the project while the image builds.
- A non-root user limits what a bug in the server could do inside the container.
- Every setting on the command line means a deploy cannot inherit a stale one, and the README can
  record the values from one place. Looking up the secret versions at deploy time pins them
  without anyone copying a number. Students reach the login page without a Google sign-in through
  `--no-invoker-iam-check`; `--allow-unauthenticated` would add an `allUsers` binding, which the
  heavychain.org organization policy (domain-restricted sharing) refuses.
- Printing the commit and the working tree's changes tells the lecturer what is live, since a
  source deploy uploads uncommitted files too.
- The service-level minimum changes without a new revision, so warming up never empties the room.
- Standard input keeps secret values out of shell history and off the projected screen.

CI builds the image on every push without pushing it, so a Dockerfile error or a secret-shaped
`ARG` fails CI. The deploy flags and account roles can be checked only against a real project,
so they rest on code review and the rehearsal (AC-20).

## Consequences

Easier:

- One command per operation, readable in the Makefile and in the lecture, including the local
  run.
- The same image runs locally (`docker build` and `docker run`) and on Cloud Run.

Harder:

- The deploy itself still runs with the lecturer's own credentials.
- `make setup` creates two accounts and their role bindings once.
- Base image versions are pinned by hand until a Dependabot `docker` entry watches them.

## Rejected alternatives

| Option | Why it lost | What would change our mind |
|---|---|---|
| Deploy from CI with Workload Identity Federation | The person ruled for a manual deploy (gray-areas-spec.md GA-010); a merge would redeploy mid-lecture. | Regular deploys by several people. |
| Cloud Build's default build identity | May hold Editor on the project while third-party install code runs. | None. |
| A shell script instead of a Makefile | The spec names a Makefile target; Make gives each operation a name. | None. |
| Build and push the image locally | Needs Docker and a registry login on the laptop. | Cloud Build unavailable to the project. |
| One image stage with Node and Python | A larger image with build tools inside. | None. |
