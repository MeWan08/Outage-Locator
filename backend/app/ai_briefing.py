"""
THE ONE AI-SHAPED FEATURE, AND WHY IT'S THIS ONE (see AI-WORKFLOW.md for the
fuller version of this argument):

01-problem-context.md is pointed about not using an LLM to do the actual
localization — graph traversal over a known/inferred tree is deterministic,
instant, free, and (crucially) explainable in exactly the way an operator
needs when they're deciding whether to trust a ticket. Nothing about that
should be handed to a model.

What IS a good fit: turning an already-correct structured ticket into a
short, plain-English dispatch note for a control-room operator and the crew
they send out ("likely a snapped span between P-24431 and P-24432, ~28
households, medium confidence because the topology here isn't surveyed").
That's a genuine translation task — structured data to natural language —
where an LLM is a good tool and a wrong answer costs nothing: it's a
readability aid layered on top of a ticket whose location, confidence, and
status were all already decided by localization.py. If this call fails,
times out, or is disabled, the system falls back to a deterministic
templated sentence built from the same fields — never blocks ticket
creation, never changes what the ticket says, never runs on the critical
detection path (it's generated after the ticket already exists).
"""
import datetime as dt

import httpx

from app.config import settings


def template_briefing(incident) -> str:
    if incident.type == "span":
        where = f"between {incident.span_from_pole_id or 'the transformer'} and {incident.span_to_pole_id}"
    elif incident.type == "dt":
        where = f"at transformer {incident.dt_id}"
    else:
        where = f"on feeder {incident.feeder_id}"
    reason = incident.confidence_reasons[0] if incident.confidence_reasons else ""
    return (
        f"Likely {incident.type} fault {where}. "
        f"~{incident.poles_affected} poles (~{incident.households_affected_estimate} households) affected. "
        f"Confidence: {incident.confidence_label} ({incident.confidence:.2f}). {reason}"
    ).strip()


async def generate_briefing(incident) -> tuple[str, str]:
    """Returns (text, source) where source is 'model' or 'template-fallback'.
    Never raises — any failure degrades to the template."""
    fallback = template_briefing(incident)
    if not settings.AI_BRIEFING_ENABLED or not settings.ANTHROPIC_API_KEY:
        return fallback, "template-fallback"

    prompt = (
        "You write short dispatch notes for electricity-board control room operators. "
        "Given this structured fault ticket, write 2-3 plain-English sentences a "
        "dispatcher can read aloud to a lineman crew. State the type of fault, "
        "roughly where it is, how many households are affected, and be explicit "
        "about the confidence level and why it isn't 100% if it isn't. No preamble, "
        "no markdown, just the sentences.\n\n"
        f"type: {incident.type}\n"
        f"transformer: {incident.dt_id}\n"
        f"feeder: {incident.feeder_id}\n"
        f"span: {incident.span_from_pole_id} -> {incident.span_to_pole_id}\n"
        f"pincode: {incident.pincode}\n"
        f"poles_affected: {incident.poles_affected}\n"
        f"households_affected_estimate: {incident.households_affected_estimate}\n"
        f"confidence: {incident.confidence:.2f} ({incident.confidence_label})\n"
        f"confidence_reasons: {'; '.join(incident.confidence_reasons or [])}\n"
        f"topology_source: {incident.topology_source}\n"
    )

    try:
        async with httpx.AsyncClient(timeout=settings.AI_BRIEFING_TIMEOUT_SECONDS) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": settings.ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": settings.AI_BRIEFING_MODEL,
                    "max_tokens": 200,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
        if resp.status_code != 200:
            return fallback, "template-fallback"
        data = resp.json()
        text = "".join(
            block.get("text", "") for block in data.get("content", []) if block.get("type") == "text"
        ).strip()
        if not text:
            return fallback, "template-fallback"
        return text, "model"
    except Exception:  # noqa: BLE001 — briefing is best-effort, never fatal
        return fallback, "template-fallback"
