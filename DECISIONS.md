# Decisions

Specific judgment calls, the alternative considered, and why. ARCHITECTURE.md
covers *how* the system works; this covers *why it's shaped this way*.

## SQLite over Postgres

Considered Postgres (the "obviously more serious" choice) and rejected it for this
submission. At this scale (a few thousand poles, one subdivision, the scope
05-faq.md explicitly says is right for the exercise) SQLite in WAL mode is more than
sufficient, and it removes an entire service — no `depends_on: db, condition:
service_healthy` race, no connection-string misconfiguration, no "migrations ran
before Postgres was accepting connections," all real ways a `docker compose up`
demo fails on a reviewer's machine. `docker compose up` brings up exactly one
container. The write-batching in `ingestion.py` (queue + single writer, one
transaction per batch) exists specifically to work around SQLite's single-writer
model — the same design would carry over cleanly to Postgres with connection
pooling if this had to serve 30 subdivisions concurrently. Documented, not hidden,
in ARCHITECTURE.md's scaling section.

## One container, not frontend/backend split

FastAPI serves the built React app as static files (`app/main.py`) instead of a
separate nginx/node service. A free-tier deployment target typically gets one web
service; a single image that serves both API and UI is the version of this that
actually survives contact with a real free-hosting deploy, at the cost of looking
less "properly separated" than two services. Given `03-deliverables-and-
submission.md` weighs "does it actually run" heavily, this seemed like the right
trade.

## Polling, not WebSockets

The console polls (~4s for incidents, ~15s for the map) instead of pushing over a
WebSocket. `05-faq.md` explicitly allows this ("polling is fine if you justify it")
and flags WebSockets-behind-a-proxy as a classic free-tier deployment failure. I
can't test a real deployed reverse proxy from this environment, so I chose the
option I could be confident about rather than the one that looks more sophisticated
in a demo. At a few thousand poles and a handful of concurrent operators, the
payload sizes involved are trivial either way.

## Confidence as an additive, explainable score — not a model

Every term in the confidence score (inferred topology, silence-only evidence, no-
device coverage gaps, stale reference point, multi-pole corroboration) is named and
shown to the operator as a plain-English reason. Considered training or prompting a
model to produce a confidence number instead; rejected because "how confident, and
why" is the actual product requirement, and a hand-built score can be audited and
retuned by changing one named constant in `config.py`, where a model's number would
be another thing to trust blindly — precisely what this system exists to avoid
doing with the underlying fault data itself.

## Geometric MST for the missing 60% — not ML, not "wait for a survey"

Covered in depth in ARCHITECTURE.md. The short version: considered (a) waiting for
manual survey data (fails the "handle it, don't wait for a perfect data source"
instruction), (b) a learned/ML topology model (no historical outage-correlation
data actually exists yet to train on — see below), (c) nearest-neighbour chaining
(produces worse trees than MST on branchy networks). MST rooted at the transformer,
with known poles pre-seeded as attachment points, was the most defensible choice
with the data actually available, and it degrades honestly — inferred spans are
never presented as equally certain as surveyed ones.

**Considered and scoped out**: learning topology from correlated outage history
(poles that go dark together are probably adjacent, use that to refine or up-weight
inferred edges over time). This is a real, better long-term answer, but it needs
weeks of real outage data to be worth anything, which doesn't exist for a from-
scratch system — building it now would be optimizing for a data source that isn't
there yet. Noted as the natural next step, not built.

## Geocoding: no external dependency at all

`pincode` comes from the registry for ~97% of poles by construction. For the
remaining ~3%, `geo.nearest_pincode` uses nearest-known-neighbour within the same
transformer — coordinates we already have, no API key, no rate limit, nothing that
breaks for a reviewer running this with zero configuration. Considered an external
geocoding API and rejected it for the same reason `05-faq.md` warns about: it must
work with no key, and degrading gracefully to "no pincode shown" felt worse than a
simple, always-available fallback that needs no network call at all.

## The one AI feature: a dispatch-note summary, not localization

See AI-WORKFLOW.md for the full argument. Short version: `01-problem-context.md` is
explicit that using an LLM for the actual fault-location decision is the wrong
answer (deterministic graph traversal is faster, free, and explainable in exactly
the way an operator needs to trust it) — so the feature had to be something that
doesn't touch that decision. A structured-ticket-to-plain-English translation for
the crew dispatch note is genuinely useful, cheap, decoupled from the critical path
(generated after the ticket already exists, async, never blocks ticket creation),
and safe to get wrong (a clunky sentence costs nothing; a wrong location costs a
truck roll).

## Scope cuts

Explicitly out of scope, per `05-faq.md`'s own list and time constraints: auth/RBAC,
crew routing/dispatch optimization, predictive maintenance, historical analytics
dashboards, HT/transmission-side modelling above the feeder. Building any of these
would have traded time away from getting the localization algorithm and its edge
cases right, which is where `04-evaluation.md` puts the most weight.

## Debounce (30s) and restoration stability window (configurable, tested at 2–45s)

A brand-new candidate must persist across detection ticks for `DEBOUNCE_SECONDS`
before becoming a ticket, and a restored pole must stay live for
`RESTORATION_STABILITY_SECONDS` before a ticket auto-verifies. Both exist for the
same reason: a single noisy reading shouldn't flip system state. 30s/45s defaults
leave enormous headroom against the 120s detection target while still meaningfully
filtering flapping; both are plain config values, not hardcoded, specifically so
they can be retuned without touching the algorithm.

## Silence is reported, not suppressed

A pole that's silent with no corroborating evidence either way (no live descendant,
no confirmed-dark descendant) still becomes a low-confidence incident rather than
being dropped. Considered suppressing it until stronger evidence arrives; rejected
because that would silently miss real faults where the boundary device happens to
be one of the ~30% that never got its dying message out — the honest answer is to
surface it, clearly labelled as low-confidence and why, not to hide the uncertainty.
