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
    if not settings.AI_BRIEFING_ENABLED:
        return fallback, "template-fallback"

    # Build a structured context block for the LLM
    conf_reasons = "\n".join(f"  - {r}" for r in (incident.confidence_reasons or []))

    prompt = (
        "You are the AI assistant for a power utility control room. Your job is to "
        "write a clear, actionable DISPATCH NOTE that a control-room operator can "
        "read aloud over the radio to a lineman crew heading to the site.\n\n"
        "RULES:\n"
        "- Write 3-4 concise sentences maximum.\n"
        "- Start with WHAT happened (type of fault) and WHERE (pole IDs, area).\n"
        "- State HOW MANY households are impacted — this determines crew urgency.\n"
        "- Be explicit about confidence: if it's not 'high', explain WHY in plain "
        "  language (e.g. 'topology is estimated, not surveyed' or 'some poles in "
        "  the area have no sensors').\n"
        "- End with a practical suggestion for the crew (e.g. 'start inspection "
        "  from pole X heading toward Y').\n"
        "- No markdown, no bullet points, no preamble — just the sentences.\n"
        "- Use natural, professional English a field technician would understand.\n\n"
        "INCIDENT DATA:\n"
        f"  Fault type: {incident.type}\n"
        f"  Transformer: {incident.dt_id}\n"
        f"  Feeder: {incident.feeder_id}\n"
        f"  Span: {incident.span_from_pole_id} → {incident.span_to_pole_id}\n"
        f"  PIN code area: {incident.pincode or 'unknown'}\n"
        f"  Poles affected: {incident.poles_affected}\n"
        f"  Households impacted (est.): ~{incident.households_affected_estimate}\n"
        f"  Confidence: {incident.confidence:.0%} ({incident.confidence_label})\n"
        f"  Topology basis: {incident.topology_source}\n"
        f"  Confidence factors:\n{conf_reasons or '    (none)'}\n"
    )

    try:
        async with httpx.AsyncClient(timeout=settings.AI_BRIEFING_TIMEOUT_SECONDS) as client:
            # 1. Groq (free tier, ultra-fast inference)
            if settings.GROQ_API_KEY:
                model = settings.AI_BRIEFING_MODEL or "llama-3.3-70b-versatile"
                resp = await client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {settings.GROQ_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": 250,
                        "temperature": 0.2,
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    text = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                    if text:
                        return text, "model"

            # 2. Anthropic (paid)
            if settings.ANTHROPIC_API_KEY:
                model = settings.AI_BRIEFING_MODEL or "claude-sonnet-5"
                resp = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": settings.ANTHROPIC_API_KEY,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": model,
                        "max_tokens": 250,
                        "messages": [{"role": "user", "content": prompt}],
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    text = "".join(
                        block.get("text", "") for block in data.get("content", []) if block.get("type") == "text"
                    ).strip()
                    if text:
                        return text, "model"

        return fallback, "template-fallback"
    except Exception:  # noqa: BLE001 — briefing is best-effort, never fatal
        return fallback, "template-fallback"
