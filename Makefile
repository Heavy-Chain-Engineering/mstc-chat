# One Make target per Cloud Run operation (ADR-07). Each target names the project and region
# itself, so it never depends on what `gcloud config` happens to hold. `make help` lists them.
#
# Secret values never appear on a command line, in a variable Make prints, or on the screen:
# they reach gcloud on standard input. Recipes start with @ so Make does not echo them.

SHELL := /bin/bash

PROJECT := mstc-chat
REGION := us-central1
SERVICE := mstc-chat
RUNTIME_ACCOUNT := mstc-chat-run@$(PROJECT).iam.gserviceaccount.com
BUILD_ACCOUNT := mstc-chat-build@$(PROJECT).iam.gserviceaccount.com
# The repository `gcloud run deploy --source` stores its images in.
SOURCE_REPOSITORY := cloud-run-source-deploy

PROJECT_FLAG := --project=$(PROJECT)
RUN_FLAGS := --project=$(PROJECT) --region=$(REGION)
# Prints the newest enabled version number of the secret named before it.
NEWEST_VERSION := $(PROJECT_FLAG) --filter=state:enabled --sort-by=~createTime --limit=1 \
	--format='value(name.basename())'
# Prints the service-level minimum and maximum (run.googleapis.com/minScale and maxScale) and
# the revision serving traffic, so a reader can see that warm-up changed no revision.
SHOW_SCALING := gcloud run services describe $(SERVICE) $(RUN_FLAGS) \
	--format='yaml(metadata.annotations,status.latestReadyRevisionName)'

# make rehearse: the address to test (default: the service's own) and the size of the class.
URL ?=
PARTICIPANTS ?= 50
DURATION ?= 60

.PHONY: help dev build-client setup class-password session-secret deploy warm-up cool-down \
	rollback rehearse

help:
	@echo "Local:"
	@echo "  make dev             build the client and run the server on http://localhost:8080"
	@echo "  make build-client    build the browser client into frontend/dist"
	@echo "Google Cloud (project $(PROJECT), region $(REGION)):"
	@echo "  make setup           create the missing accounts, secrets and grants (safe to rerun)"
	@echo "  make class-password  store a new class password, typed at a hidden prompt"
	@echo "  make session-secret  generate and store a new session secret, never shown"
	@echo "  make deploy          build from source and deploy with every Cloud Run setting"
	@echo "  make warm-up         keep 1 instance running (lecture day), without redeploying"
	@echo "  make cool-down       let the service scale to 0 again, without redeploying"
	@echo "  make rollback REVISION=<name>  send all traffic to an earlier revision"
	@echo "  make rehearse        sign in $(PARTICIPANTS) simulated students and time delivery"

dev: build-client
	@set -euo pipefail; \
	[ -f .env ] || { echo "Copy .env.example to .env and fill in both secrets first." >&2; exit 1; }; \
	uv run --env-file .env python -m backend

build-client:
	@npm --prefix frontend ci --ignore-scripts
	@npm --prefix frontend run build

# Creates only what is missing and never replaces a secret value. Granting a role a member
# already holds changes nothing, so the grants run every time.
setup:
	@set -euo pipefail; \
	gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
		artifactregistry.googleapis.com secretmanager.googleapis.com $(PROJECT_FLAG); \
	gcloud iam service-accounts describe $(RUNTIME_ACCOUNT) $(PROJECT_FLAG) >/dev/null 2>&1 \
		|| gcloud iam service-accounts create mstc-chat-run $(PROJECT_FLAG) \
			--display-name="MSTC Chat server (reads the two secrets only)"; \
	gcloud iam service-accounts describe $(BUILD_ACCOUNT) $(PROJECT_FLAG) >/dev/null 2>&1 \
		|| gcloud iam service-accounts create mstc-chat-build $(PROJECT_FLAG) \
			--display-name="MSTC Chat source builds"; \
	gcloud artifacts repositories describe $(SOURCE_REPOSITORY) $(PROJECT_FLAG) \
		--location=$(REGION) >/dev/null 2>&1 \
		|| gcloud artifacts repositories create $(SOURCE_REPOSITORY) $(PROJECT_FLAG) \
			--location=$(REGION) --repository-format=docker; \
	for secret in class-password session-secret; do \
		gcloud secrets describe $$secret $(PROJECT_FLAG) >/dev/null 2>&1 \
			|| gcloud secrets create $$secret $(PROJECT_FLAG) --replication-policy=automatic; \
		gcloud secrets add-iam-policy-binding $$secret $(PROJECT_FLAG) \
			--member=serviceAccount:$(RUNTIME_ACCOUNT) \
			--role=roles/secretmanager.secretAccessor >/dev/null; \
	done; \
	gcloud projects add-iam-policy-binding $(PROJECT) \
		--member=serviceAccount:$(BUILD_ACCOUNT) --role=roles/run.builder \
		--condition=None >/dev/null; \
	session_version=$$(gcloud secrets versions list session-secret $(NEWEST_VERSION)); \
	[[ "$$session_version" =~ ^[0-9]+$$ ]] || $(MAKE) --no-print-directory session-secret; \
	password_version=$$(gcloud secrets versions list class-password $(NEWEST_VERSION)); \
	[[ "$$password_version" =~ ^[0-9]+$$ ]] \
		|| echo "Next: run make class-password to store the class password."; \
	echo "Setup is complete."

class-password:
	@set -euo pipefail; \
	printf 'Class password (typing stays hidden): ' >&2; \
	IFS= read -rs password || true; \
	echo >&2; \
	[ -n "$$password" ] || { echo "No password entered, so nothing changed." >&2; exit 1; }; \
	printf '%s' "$$password" \
		| gcloud secrets versions add class-password $(PROJECT_FLAG) --data-file=-; \
	echo "Stored a new class password. Run make deploy to use it." >&2

session-secret:
	@set -euo pipefail; \
	openssl rand -base64 48 | tr -d '\n' \
		| gcloud secrets versions add session-secret $(PROJECT_FLAG) --data-file=-; \
	echo "Stored a new session secret. After make deploy, everyone must sign in again." >&2

# Looks up each secret's newest enabled version number now, so the service is pinned to it
# (never `latest`), and stops before deploying when a secret has none.
deploy:
	@set -euo pipefail; \
	password_version=$$(gcloud secrets versions list class-password $(NEWEST_VERSION)); \
	session_version=$$(gcloud secrets versions list session-secret $(NEWEST_VERSION)); \
	[[ "$$password_version" =~ ^[0-9]+$$ ]] || { \
		echo "The secret class-password has no enabled version. Run make class-password." >&2; \
		exit 1; }; \
	[[ "$$session_version" =~ ^[0-9]+$$ ]] || { \
		echo "The secret session-secret has no enabled version. Run make session-secret." >&2; \
		exit 1; }; \
	gcloud run deploy $(SERVICE) $(RUN_FLAGS) --source=. --quiet \
		--max=1 --concurrency=250 --timeout=60 --cpu=1 --memory=512Mi --no-cpu-boost \
		--no-invoker-iam-check \
		--service-account=$(RUNTIME_ACCOUNT) \
		--build-service-account=projects/$(PROJECT)/serviceAccounts/$(BUILD_ACCOUNT) \
		--set-secrets=CLASS_PASSWORD=class-password:$$password_version,SESSION_SECRET=session-secret:$$session_version; \
	changes=$$(git status --short); \
	echo; \
	echo "Address:  $$(gcloud run services describe $(SERVICE) $(RUN_FLAGS) --format='value(status.url)')"; \
	echo "Commit:   $$(git rev-parse --short HEAD)"; \
	echo "Uncommitted changes, which the deploy uploaded too:"; \
	echo "$${changes:-  none}"; \
	echo "Finished: $$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# Both change the service-level minimum, which creates no revision, so the room keeps its
# messages and every open page stays connected.
warm-up:
	@set -euo pipefail; \
	gcloud run services update $(SERVICE) $(RUN_FLAGS) --min=1; \
	$(SHOW_SCALING)

cool-down:
	@set -euo pipefail; \
	gcloud run services update $(SERVICE) $(RUN_FLAGS) --min=0; \
	$(SHOW_SCALING)

rollback:
	@set -euo pipefail; \
	[ -n "$(REVISION)" ] || { \
		echo "Name the revision to roll back to: make rollback REVISION=<name>" >&2; \
		gcloud run revisions list --service=$(SERVICE) $(RUN_FLAGS); \
		exit 1; }; \
	gcloud run services update-traffic $(SERVICE) $(RUN_FLAGS) --to-revisions=$(REVISION)=100

rehearse:
	@set -euo pipefail; \
	url="$(URL)"; \
	[ -n "$$url" ] \
		|| url=$$(gcloud run services describe $(SERVICE) $(RUN_FLAGS) --format='value(status.url)'); \
	uv run python tests/rehearsal/rehearse.py --url "$$url" \
		--participants $(PARTICIPANTS) --duration $(DURATION)
