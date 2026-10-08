This project owns this copy of ETC's engineering judgment and may edit it. ETC's agents read it in place of ETC's standard.

# Engineering judgment: build the boring thing, and prove it works

Paths that begin with `standards/` are relative to the ETC plugin folder.

## Status: MANDATORY
## Applies to: every agent that designs, writes, tests or reviews code in a project that uses ETC

This is ETC's default engineering culture. It governs how an agent designs, writes code, tests it
and reviews it.

The goal is simple, maintainable code that a mid-level engineer can understand and fix at 3 AM,
built quickly and proven by automated tests. An agent can write code almost for free, and
unverified or over-built code costs far more to find and remove later than it cost to write.

When the project keeps its own engineering-judgment document, and its `PROJECT.md`, `AGENTS.md` or
`CLAUDE.md` names it, the project's document governs. Apply this standard where the project's
document is silent.

ETC is language agnostic. The tools named below are examples from common ecosystems, not
requirements. Use the tools the project already uses, as its `PROJECT.md` and its check commands in
`.etc_sdlc/settings.toml` name them.

The numbers below are ETC's defaults. A project may set its own in its own configuration, such as
its coverage settings, its test runner's settings or its `PROJECT.md`. When it does, the project's
number applies.

## The field card

1. **Use proven tools, not custom ones.** Use the standard library and battle-tested tools, such
   as Celery and Redis in Python or a hosted queue. Never hand-roll a task queue, a background
   worker pool, a leasing loop or a lock manager, for example a `SELECT ... FOR UPDATE SKIP LOCKED`
   loop in Postgres that runs business logic.
2. **Verify hard, automatically.** Tests cover at least 98% of the lines a change adds or edits.
   Total coverage never goes down. Each test runs in under 1.5 seconds, or under 5 seconds when it
   uses a real database. Test real behaviour against real dependencies, not mocks of the project's
   own code.
3. **Run the checks locally before every push.** Run the tests, including integration tests
   against local containers or services, before pushing. Fix failures locally; do not push
   unverified code and wait for the continuous-integration server to find them.
4. **Let git keep versions and history.** Never track file versions, or keep checksums or hashes
   in code, such as a `RELEASE_FINGERPRINTS` table. Record a git commit hash when you need to know
   which version produced something. Use git branches for experiments.
5. **Compute derived values when they are needed.** Never make a person copy a hash or other
   value from one file into another. If a cache key or fingerprint is needed, compute it at run
   time.
6. **Use standard linters, not custom checks.** Never write a custom script or check in
   continuous integration that polices vocabulary, subjective style or a hand-kept registration
   list.
   Use the ecosystem's standard linter, type checker and test runner, such as ruff, mypy and pytest
   in Python or ESLint, tsc and Vitest in TypeScript.
7. **Write plain English.** Write no aphorisms in documents or decision records. State what the
   thing does, why, and how it fails. `standards/process/communication.md` sets how to write.
8. **Pass the 3 AM test.** If a tired engineer cannot fix a typo in a file at 3 AM without
   tripping an obscure custom tool, reject the design.

## 1. How to decide

### Use the runtime and the ecosystem first

Prefer the standard library, then a battle-tested industry tool, then custom code. Never hand-roll
your own version of something that a mature open-source project with many years of production use
already provides.

### Verify hard, because generated code costs almost nothing to write

In a codebase that agents help write, writing code costs almost nothing, and untested or invented
logic costs a great deal.

- **Changed-line coverage and a ratchet.** Meaningful tests cover at least 98% of the lines a
  change adds or edits, by default. Total coverage only rises.
- **Test time budgets.** A test runs in under 1.5 seconds, or under 5 seconds with a real
  database, by default. Never write a test that waits on `sleep()` or a slow polling loop.
- **Local verification before a push.** Check a change locally against real dependencies, for
  example with Docker Compose or testcontainers, before pushing.
- **Real boundaries, not mocks.** Test real behaviour. Do not mock every internal collaborator
  until the test no longer says anything about what the code does.

### Let git keep versions

Never repeat git's job in application code. Versions, file history, change tracking and rollbacks
belong to git commits, tags and branches. When a record must say which version of a prompt, schema
or configuration produced it, log the git commit hash or compute a hash at run time. Never keep a
static checksum table in code.

### Derive values at run time; never copy them by hand

Never design something where changing file A requires copying a value or checksum into file B by
hand. If a fingerprint, cache key or hash is needed, compute it in memory at run time.

### Match the rigour to the harm a failure would do

Scale the checks to the harm a failure would do. Do not add cryptographic verification,
two-phase commits or append-only ledgers unless there is a real compliance or financial
requirement.

Before you add a safeguard, name the harm it prevents and say how likely that harm is in this
system. When you cannot name a real harm that is likely, leave the safeguard out: a defence against
an imaginary threat costs time to build, review and maintain, and protects nothing, however
rigorous it looks. For example, an internal report that five staff open on a private network does
not need protection against automated attacks from the internet.

### Keep long-running work out of the handoff

An outbox, a database queue or a message broker exists only to hand work over reliably, and the
handoff should take milliseconds, under about 10 ms.
Long-running work, such as model calls, document parsing or heavy computation, runs in dedicated
background workers. It never runs inside a database leasing loop or a synchronous request.

## 2. What not to do

### Rebuilding infrastructure in SQL or in application code

- Do not hand-roll job queues, worker pools, leasing loops or lock managers in the database when a
  proven queue or broker is available or appropriate.
- Do not invent local daemons or custom inter-process pipes for work that a standard library
  already does, such as reading spreadsheets, writing slide decks or resizing images.

### Custom lint scripts and custom continuous-integration traps

- Do not write custom syntax-tree parsers, regular-expression scanners or home-grown checks that
  police architectural rules, code style, vocabulary or hand-kept registration lists, unless a
  person on the project has approved it.
- Use the ecosystem's standard tools. If a rule cannot be expressed in them, enforce it with an
  automated test or in code review. Never add a custom check that fails on whitespace, line
  endings or a missing entry in a hand-kept list.

### Static manifests and checksum registries

- Do not hard-code file hashes, checksum lists or hand-kept release registries in source code.
- Do not copy a directory to experiment, such as `prompts/experiments/exp_1/`. Use a git branch.

### Speculative abstraction

- Do not add abstract base classes, generic repository layers, protocol adapters or plugin systems
  for something that has only one concrete implementation.
- Write concrete, straightforward code. Abstract on the third real case, never in anticipation.

### Aphorisms and self-important prose

- Do not write documents, decision records or pull request descriptions in cryptic aphorisms, such
  as "The graph must never know its creator" or "An outbox is not a shelf but an obligation".
- State what the component does, why this approach was chosen, what the trade-offs are, and how it
  fails.

### Comments that repeat the code, carry history or make unchecked claims

- A comment says why the code is as it is now, or states a constraint that someone has shown to
  hold, such as "the vendor's API rejects a batch over 100 items".
- A comment or docstring says what a reader cannot see from the code, and never restates the code.
  "Return the total." on a function named `total` tells the reader nothing; leave it out. A
  docstring earns its place with what the signature does not show, such as a unit, a constraint
  or an error the caller must handle. A project convention that asks for docstrings asks for
  this kind; it never asks for one that restates the code.
- History goes in the commit message: what changed, what it replaced, and which review or task
  asked for it. A changelog in the code, or a note such as "added for task 12", does not belong
  there.
- Past context is fine when it explains a constraint that still applies, such as "accepts the
  old wire format because version 2 clients still send it". Judge what the comment tells the next
  reader, not which words it uses.
- A comment that states a fact about the system, such as an import cycle, an ordering rule or a
  thread-safety rule, is a claim. It must be true today, and a reviewer checks it before relying on
  it.
- Remove a suppression comment, such as `# noqa` or `// eslint-disable`, once the code no longer
  needs it. The language's standard linter reports a stale one where it can (the language's
  clean-code bindings name the rule).

### Drive-by changes and tests made of mocks

- Do not reformat unrelated files, rename conventions or change existing patterns while working on
  a scoped task.
- Do not write tests that mock every internal collaborator until they assert nothing real.
  Integration tests exercise real boundaries: a real database, a real file parser.

## 3. The 3 AM test

Before you propose an architecture, a pattern or a constraint, answer three questions:

1. **The on-call question.** If a tired engineer must fix a typo in this file at 3 AM on a Friday,
   will an obscure custom tool or a hash mismatch block them?
2. **The deletion question.** If this component breaks, can the team replace it with a few lines of
   standard code, or is the project locked into something only its author understands?
3. **The standard-library question.** Does a battle-tested library already do this in one line?

## How reviewers use this standard

The code reviewer and the architect reviewer check the work against this standard, or against the
project's own document when it has one. Each breach is a finding. The finding names the rule it
breaks by its field card number or its section heading, quotes the file and line that shows the
breach, and says what to change. Workers are given this standard too, so they build to the rules
their reviewers apply.
