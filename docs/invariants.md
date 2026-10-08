# Invariants

Rules this project never breaks. Each Verify command prints nothing when the rule holds and
prints at least one line when it fails or cannot run. The tests and the ruff setting they name
arrive with the chat feature's build tasks; until they exist, INV-002 and INV-003 print their
failure line.

## INV-001: The room's rules import no web framework

- **Layers:** test, ci
- **Verify:** `uv run ruff check --select TID251 --output-format concise --quiet backend tests`
- **Fail action:** Block merge
- **Rationale:** ADR-02. A reader must find every room rule in plain Python, and each rule must be testable without HTTP. Ruff exits 1 when it reports a banned import and 2 when it cannot run.
- **Scope:** `backend/`

## INV-002: No name, message text, password, secret or cookie value reaches a log

- **Layers:** test, ci, agent-instructions
- **Verify:** `uv run pytest -q tests/test_privacy.py >/dev/null 2>&1 || echo "INV-002 failed: tests/test_privacy.py"`
- **Fail action:** Block merge
- **Rationale:** DOMAIN.md, design implication 5, and AC-15. Display names are personal data, and Cloud Run keeps everything the app writes to standard output or standard error.
- **Scope:** `backend/`

## INV-003: Message HTML holds only the allowlisted elements, and raw HTML shows as text

- **Layers:** test, ci
- **Verify:** `uv run pytest -q tests/test_safe_markdown.py >/dev/null 2>&1 || echo "INV-003 failed: tests/test_safe_markdown.py"`
- **Fail action:** Block merge
- **Rationale:** DOMAIN.md, risk 1, and ADR-05. A message that runs script in other browsers breaks the demo in front of the class.
- **Scope:** `backend/safe_markdown.py`
