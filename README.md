# MSTC Chat

A live chat room for one lecture, where students send the lecturer feedback
and links. It is also the worked example in a lecture on spec-driven
development. See `DOMAIN.md` and `PROJECT.md`.

The app is one Python server that also serves the browser client. It keeps
every message and the list of who is online in memory, with no database, and
runs as one container on Google Cloud Run. `make help` lists every command.

## Setup

You need uv, Node 22, GNU Make, and, to deploy, the Google Cloud CLI
(`gcloud`) signed in to an account that may administer the `mstc-chat`
project.

```sh
uv sync                                        # Python tools
npm --prefix frontend ci --ignore-scripts      # TypeScript tools, no install scripts
pre-commit install                             # commit, commit-message and pre-push hooks
cp .env.example .env                           # local settings; git never tracks .env
```

## Run it locally

1. Fill in `.env`. Choose any local class password. Generate the session
   secret without printing it:
   `printf 'SESSION_SECRET=%s\n' "$(openssl rand -base64 48)" >> .env`
   (delete the empty `SESSION_SECRET=` line above it). The server refuses to
   start if either secret is missing or the session secret is under 32
   characters.
2. Run `make dev`. It builds the client into `frontend/dist/` and starts the
   server on http://localhost:8080.
3. Open http://localhost:8080 in Chrome or Firefox. Safari refuses the
   session cookie on `http://localhost`, because the cookie is marked
   `Secure`, so sign-in does not stick there.

To try the container itself: `docker build -t mstc-chat .` and
`docker run --rm -p 8080:8080 --env-file .env mstc-chat`.

## Secrets

The app has two secrets. Cloud Run reads both from Secret Manager; they never
live in the repository, the image, CI or the service's settings.

| Setting | Secret Manager secret | What it is |
|---|---|---|
| `CLASS_PASSWORD` | `class-password` | The one password every student types. |
| `SESSION_SECRET` | `session-secret` | The key that signs session cookies. |

Rules:

- **Never write the class password in this repository, in a commit, an issue
  or a pull request**, not even in an example. The repository is public, and
  no secret scanner can recognise a password made of plain words.
- Choose a class password of at least 12 characters, such as three random
  words. Wrong guesses each wait 1 second, but nothing locks anyone out.
- Enter secrets only through the commands below. They read the value at a
  hidden prompt, or generate it unseen, and pass it to `gcloud` on standard
  input, so it never appears on a command line, in shell history or on a
  projected screen.

```sh
make class-password    # type the class password at the hidden prompt
make session-secret    # generate a new session secret; nobody sees it
```

Each command adds a new version of the secret. The running service keeps the
version it was deployed with until the next `make deploy`. A new session
secret signs everyone out, which is also the only way to end every session
early.

## First-time Google Cloud setup

```sh
gcloud auth login
make setup
make class-password
```

`make setup` is safe to run again: it creates only what is missing and never
replaces a secret value. It:

- turns on the Cloud Run, Cloud Build, Artifact Registry and Secret Manager
  APIs;
- creates the runtime account `mstc-chat-run@mstc-chat.iam.gserviceaccount.com`
  and gives it Secret Accessor on the two secrets only, so the server can read
  nothing else;
- creates the build account `mstc-chat-build@mstc-chat.iam.gserviceaccount.com`
  and gives it only Cloud Run Builder (`roles/run.builder`), never Editor, so
  dependency code running during a build cannot change the project;
- creates the two secrets and the `cloud-run-source-deploy` image repository
  in `us-central1`, and generates a session secret if none exists.

### Budget alert

Set a US$5 budget alert once, in the Cloud Console under Billing, Budgets and
alerts, for the `mstc-chat` project. A lecture costs a few cents; an alert
means something is misconfigured or abused.

## Deploy

```sh
make deploy
```

`make deploy` uploads this folder (minus what `.gcloudignore` excludes), builds
the image in Cloud Build under the build account, and deploys the service
`mstc-chat` in `us-central1`. It sets every setting on the command line, so a
deploy never inherits a stale one:

| Cloud Run setting | Value | Why |
|---|---|---|
| Maximum instances (service level) | 1 | All messages live in one process's memory; a second instance would split the room. |
| Concurrency | 250 | About 100 open streams plus their posts must fit in one instance. |
| Request timeout | 60 s | The server ends each stream after 20 s anyway. |
| CPU, memory | 1 vCPU, 512 MiB | Enough for one class; the smallest that fits. |
| Start-up CPU boost | off | Keeps the cost near zero. |
| Access | public, invoker IAM check off (`--no-invoker-iam-check`) | Students reach the login page without a Google account. The heavychain.org organization policy (domain-restricted sharing) refuses the `allUsers` binding that `--allow-unauthenticated` would add; turning the check off needs no binding. |
| Runtime account | `mstc-chat-run` | Reads the two secrets and nothing else. |
| Build account | `mstc-chat-build` | Holds only Cloud Run Builder. |
| Secrets | `CLASS_PASSWORD=class-password:<n>`, `SESSION_SECRET=session-secret:<n>` | References pinned to the newest enabled version numbers, looked up at deploy time; the settings show names and numbers, never values. |
| Minimum instances | unchanged | Only `make warm-up` and `make cool-down` change it. |

When it finishes, it prints the address, the commit, any uncommitted changes
(a source deploy uploads those too) and the UTC time. Check that the commit is
the one you meant to ship.

**A redeploy wipes the room.** The new version starts with no messages. Every
open page reconnects to it within about 30 seconds, shows "The chat
restarted", and reloads. Rolling back empties the room the same way. Deploy
before the lecture, not during it, unless the redeploy is the demo.

### Roll back

```sh
make rollback                              # lists the revisions
make rollback REVISION=mstc-chat-00007-abc # sends all traffic to that revision
```

Rolling back builds nothing and empties the room. `make deploy` later sends
traffic to the new revision again.

## Lecture day

Before the lecture:

1. `make warm-up`. It sets the service's minimum to 1 instance, so no student
   waits for a cold start. It creates no revision, so nothing restarts.
2. Confirm in its output that `run.googleapis.com/minScale` reads `'1'`,
   `run.googleapis.com/maxScale` reads `'1'`, and `latestReadyRevisionName`
   is the revision you deployed.
3. Open the address in your browser, sign in, and post one message.
4. Optional rehearsal: `make rehearse` signs in 50 simulated students named
   "Rehearsal 01" and up, posts a probe every 2 seconds for 60 seconds, and
   prints the slowest delivery. It passes when every student got every probe
   within 2 seconds and nothing was refused. Set `PARTICIPANTS`, `DURATION` or
   `URL` to change it, as in `make rehearse PARTICIPANTS=10`. Run it well
   before class: its messages stay in the room until the next restart.

After the lecture:

1. `make cool-down`. It sets the minimum back to 0, so the idle service costs
   nothing. Open tabs keep the instance running, and billed, until they close.
2. Confirm that `run.googleapis.com/minScale` reads `'0'` or is gone.

## What Cloud Run's request logs keep

The app never logs names, message text, passwords or cookies. Cloud Run itself
logs every request for 30 days: the URL (with its query, which holds only a
random tab id), the method, status, latency, the client's IP address and
browser name. It logs no body and no cookie. To stop keeping this service's
request logs:

```sh
gcloud logging sinks update _Default --project=mstc-chat \
  --add-exclusion='name=mstc-chat-requests,filter=resource.type="cloud_run_revision" AND resource.labels.service_name="mstc-chat" AND log_id("run.googleapis.com/requests")'
```

## CI

`.github/workflows/ci.yml` runs on every push to `main` and every pull request,
with read-only access and no secrets. It runs Ruff, mypy, pytest with at least
80% coverage, tsc, ESLint, Prettier, the frontend tests, pip-audit and npm
audit; scans the whole git history for secrets with Gitleaks, after proving on
a throwaway repository that the scan fails on a deleted token; and builds the
image without pushing it. CI never deploys.

### GitHub settings to switch on

These are repository settings, which only an admin can change:

1. Settings, Code security: turn on **Secret scanning** and **Push
   protection**. Both are free for public repositories.
2. Settings, Branches (or Rules, Rulesets): protect `main`. Require a pull
   request, require the status checks `checks`, `secret-scan` and `image` to
   pass, and block force pushes.
3. Settings, Actions, General: allow only actions pinned to a full commit SHA,
   and keep "Require approval for first-time contributors".

## After the course

Delete the service, its images, the secrets and the accounts:

```sh
gcloud run services delete mstc-chat --region=us-central1 --project=mstc-chat
gcloud artifacts repositories delete cloud-run-source-deploy --location=us-central1 --project=mstc-chat
gcloud secrets delete class-password --project=mstc-chat
gcloud secrets delete session-secret --project=mstc-chat
gcloud iam service-accounts delete mstc-chat-run@mstc-chat.iam.gserviceaccount.com --project=mstc-chat
gcloud iam service-accounts delete mstc-chat-build@mstc-chat.iam.gserviceaccount.com --project=mstc-chat
```

Or shut down the whole project: `gcloud projects delete mstc-chat`.

## Logo and fonts

- **Logo.** The McCombs logo comes unchanged from McCombs' official logo
  downloads on UT's Box service (formal logo:
  https://utexas.box.com/s/b88qfe69z1mhr4d441yj28k1gwo7c402). The person who
  runs this course holds permission to use the McCombs mark for this class
  tool through their service on the MSTC Advisory Council. When no official
  file is in `frontend/public/brand/`, the login page shows the text wordmark
  "MSTC Chat" instead. UT owns all rights in its marks.
- **Fonts.** Libre Franklin and Charis SIL come from the Fontsource npm
  packages and are served by the app, so students' browsers contact no third
  party. Both are under the SIL Open Font License 1.1; the licence texts are
  served with the app from `frontend/public/fonts/`.
