# AI Workflow

## The one AI-shaped feature

**A plain-English dispatch-note summary**, generated after a ticket is created,
turning the structured incident (type, span, confidence, reasons, affected counts)
into 2–3 sentences a control-room operator can read to a lineman crew. Implementation
in `backend/app/ai_briefing.py`.

**Why this one.** `01-problem-context.md` is pointed about not using an LLM for the
actual fault-location decision — deterministic graph traversal is faster, free, and
explainable in exactly the way an operator needs to trust a ticket, and nothing
about that should be handed to a model whose reasoning can't be audited the same
way. What's left as a genuinely good fit is a translation task: structured data to
natural language, where a wrong answer costs almost nothing (a clunky sentence,
not a wrong truck roll) because the ticket's actual location, confidence, and
status were already decided by `localization.py` before the model ever sees it. The
call is fully decoupled from the critical path — it runs async, after the ticket
already exists, and if it fails, times out, or `ANTHROPIC_API_KEY` isn't set at all,
the system falls back to a deterministic templated sentence built from the same
fields. Ticket creation never blocks on it and the reviewer needs no API key for
anything, including this, to work.

**Considered and rejected**: an operator chatbot over live incident data (more
moving parts, more prompt-injection/hallucination surface, for a use case a sortable
table already serves fine); LLM-assisted matching of complaint-call free text to
poles (no call-intake data source exists in the brief — would have been inventing
scope rather than solving the stated problem).

## How AI was used to build this

This system was built by Claude (Anthropic), working directly in an agentic coding
environment with a real shell, filesystem, and Python/Node toolchains — not by a
human prompting for snippets and assembling them by hand. Worth describing plainly
since it's unusual enough to matter for how you should read the rest of this
document:

**The algorithm was designed, then implemented, then actually tested against real
inputs** — 21 pytest cases covering known/inferred topology, sensor-only false
positives, branch points, multiple simultaneous faults, and the no-device edge case
below, all run and passing, not just written and assumed correct.

**Four real bugs were found and fixed by running the system, not by inspection**:

1. A foreign-key insert-ordering bug in the synthetic data generator (SQLite checks
   FKs immediately, not at commit — parent rows needed explicit flushes before
   dependent rows), caught when the app failed to boot.
2. A naive/aware-datetime mismatch (SQLite doesn't preserve `tzinfo` across a
   round-trip even with a timezone-aware column type), caught when the background
   detection loop threw on every tick after boot.
3. **The most important one**: end-to-end testing (inject a fault, watch the API)
   revealed that poles with no telemetry device fitted (~9% of the network) were
   being treated as "presumed dark" by default, producing a permanent phantom
   outage ticket for every no-device leaf pole in the network the moment the system
   booted. The fix — no-device poles inherit their parent's state and can never
   independently trigger an incident — is now both a code comment and a named
   regression test (`test_no_device_pole_never_triggers_its_own_frontier`). The same
   bug existed a second time in restoration verification (a ticket could never
   auto-verify if its affected set included a no-device pole, since it could never
   prove liveness) and was found and fixed the same way, immediately after.
4. An escalation/supersession gap: because ambiguous silent poles confirm dark at
   different times, a fault can start as several span-level tickets and coarsen into
   one DT-level ticket as more evidence arrives. The narrower tickets were being left
   open and orphaned instead of being closed out — found via an end-to-end scheduled-
   outage test, fixed by adding explicit supersession handling.

All four are described in more detail, with the actual reasoning at the time, in
`ARCHITECTURE.md` and in the git history — the commit messages for these fixes
explain what was found and how, not just what changed.

**Where this workflow's limits showed up**: the orchestration layer (`background.py`,
`tickets.py`, `simulator.py`) is verified by hand-run end-to-end scenarios captured
in commit messages and this document, not by an automated pytest suite with a DB
fixture — that conversion didn't happen inside the time available. That's a real gap,
stated rather than hidden: the pure algorithmic core (`localization.py`,
`topology.py`) has automated regression coverage; the stateful orchestration around
it has been exercised, not locked in.

**What I'd do differently with more time**: build the DB-backed integration tests
that were manually run instead of just running them once; add the historical
outage-correlation topology refinement noted as future work in DECISIONS.md; extend
the concurrent load test (`scripts/loadtest.py`, now covers both single-connection
and 40-way-concurrent scenarios — see ARCHITECTURE.md) to a genuinely distributed
load generator rather than one process's worker pool, to see whether the numbers
hold up beyond what a single machine's event loop can drive.

